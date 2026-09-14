#!/usr/bin/env python3
"""Explicit, whole-bundle installation; standard-library only; never installs dependencies."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile

NAME = "geo-article-studio"
HOSTS = ("generic", "hermes", "codex", "claude-code")
PROTOCOL = "geo.host.v1"
EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules",
            "data", "runtime", "outputs", "output", "cache", "dist", "build", "logs", ".env"}
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", *("COM" + str(n) for n in range(1, 10)),
                   *("LPT" + str(n) for n in range(1, 10))}


class InstallError(ValueError):
    """User-facing errors containing only installer-controlled messages."""


def emit(value, *, error=False):
    stream = sys.stderr if error else sys.stdout
    print(json.dumps(value, ensure_ascii=False, indent=2), file=stream)


def inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def checked_path(value: str | Path) -> Path:
    raw = Path(value).expanduser().absolute()
    for item in (raw, *raw.parents):
        if item.exists() and linked(item):
            raise InstallError("路径含符号链接或目录联接，拒绝安装")
    return raw.resolve()


def excluded(path: Path) -> bool:
    return any(p in EXCLUDED for p in path.parts) or path.name.endswith((".pyc", ".pyo")) or (
        path.name.startswith(".env.") and path.name != ".env.example")


@contextmanager
def bundle(source: Path):
    if source.is_dir():
        yield source
        return
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise InstallError("源必须是含 SKILL.md 的完整目录或 ZIP")
    with tempfile.TemporaryDirectory(prefix="geo-install-unpack-") as temporary:
        root = Path(temporary).resolve()
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(x.file_size for x in entries) > 250 * 1024 * 1024:
                raise InstallError("ZIP 超过 10000 项或 250 MiB 解压上限")
            seen = set()
            # Validate every entry BEFORE extracting anything, including files later excluded.
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                p = PurePosixPath(name)
                if (p.is_absolute() or ".." in p.parts or any(":" in part for part in p.parts)
                        or not p.parts or stat.S_ISLNK(entry.external_attr >> 16)
                        or any(part.endswith((".", " ")) or part.split(".")[0].upper() in WINDOWS_DEVICES
                               for part in p.parts)):
                    raise InstallError("ZIP 含不安全路径或符号链接")
                key = str(p).casefold()
                if key in seen:
                    raise InstallError("ZIP 含重复路径")
                seen.add(key)
                target = root.joinpath(*p.parts).resolve()
                if not inside(target, root):
                    raise InstallError("ZIP 路径越界")
            for entry in entries:
                target = root.joinpath(*PurePosixPath(entry.filename.replace("\\", "/")).parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as src, target.open("wb") as dest:
                        shutil.copyfileobj(src, dest)
        candidates = [root] if (root / "SKILL.md").is_file() else [p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()]
        if len(candidates) != 1:
            raise InstallError("ZIP 必须包含唯一技能根目录")
        yield candidates[0]


def copy_bundle(source: Path, target: Path):
    for entry in source.rglob("*"):
        relative = entry.relative_to(source)
        if excluded(relative):
            continue
        if linked(entry):
            raise InstallError("技能包含符号链接或目录联接，拒绝复制")
        dest = target / relative
        if entry.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif entry.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, dest)


def install(source: Path, skills: Path, data: Path, upgrade=False, host="generic"):
    if host not in HOSTS:
        raise InstallError("不支持的宿主；请选择 generic、hermes、codex 或 claude-code")
    target = skills / NAME
    if data.exists() and not data.is_dir():
        raise InstallError("运行数据路径已存在且不是目录")
    if inside(data, skills) or inside(skills, data) or inside(data, source) or inside(source, data):
        raise InstallError("运行数据必须与技能目录、源代码目录完全分离")
    if source.is_dir() and (inside(skills, source) or inside(source, target)):
        raise InstallError("安装源与目标不能互相包含")
    backup = None
    if target.exists():
        checked_path(target)
        if not target.is_dir():
            raise InstallError("目标已存在且不是目录")
        if not upgrade:
            raise InstallError("技能已存在；仅显式 --upgrade 才备份升级")
        marker = target / "installation.json"
        if marker.exists():
            old = json.loads(marker.read_text(encoding="utf-8"))
            if Path(old["data_dir"]).resolve() != data:
                raise InstallError("升级不得改变既有运行数据目录")
            # Releases before host metadata targeted Hermes. Do not silently relabel them.
            if old.get("host", "hermes") != host:
                raise InstallError("升级不得改变既有宿主；旧版无 host 记录按 hermes 处理。请沿用原宿主，或显式选择新的技能目录。")
        for name in ("data", "runtime", "workspace", "outputs", "tasks", "learned_rules"):
            if (target / name).exists():
                raise InstallError("旧技能含运行数据；请先明确迁出并配置独立目录，安装器不会删除这些数据")
    with bundle(source) as root:
        if not (root / "SKILL.md").is_file():
            raise InstallError("源目录缺少 SKILL.md")
        skills.mkdir(parents=True, exist_ok=True)
        # Staging is inside the target volume, so final rename is atomic.
        with tempfile.TemporaryDirectory(prefix=".geo-install-", dir=skills) as temporary:
            stage = Path(temporary) / NAME
            stage.mkdir()
            copy_bundle(root, stage)
            (stage / "installation.json").write_text(json.dumps({
                "skill": NAME, "host": host, "protocol": PROTOCOL,
                "data_dir": str(data), "installed_at": datetime.now(timezone.utc).isoformat(),
                "note": "运行配置、任务、规则、索引必须保存在 data_dir；卸载仅移除技能代码。"
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            if target.exists():
                backup_root = checked_path(skills.parent / (NAME + "-backups"))
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = backup_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
                target.rename(backup)
            try:
                stage.rename(target)
            except OSError:
                if backup is not None and not target.exists():
                    backup.rename(target)
                raise
    data.mkdir(parents=True, exist_ok=True)
    return {"installed": str(target), "data_dir": str(data), "backup": str(backup) if backup else None,
            "host": host, "protocol": PROTOCOL, "dependencies_installed": False}


def probe(host="hermes", *, skills=None, data=None):
    """Read-only discovery; the no-argument Python API retains legacy Hermes behavior."""
    if host not in HOSTS:
        raise InstallError("不支持的宿主；请选择 generic、hermes、codex 或 claude-code")
    result = {"host": host, "protocol": PROTOCOL, "read_only": True,
              "platform": sys.platform, "installer_python": sys.executable,
              "installer_python_version": sys.version.split()[0],
              "skill_loading_verified": False, "model_capabilities_verified": False,
              "explicit_targets": {"skills_dir": str(skills) if skills is not None else None,
                                   "data_dir": str(data) if data is not None else None},
              "discovery_status": "unverified"}
    if host != "hermes":
        command = {"codex": "codex", "claude-code": "claude"}.get(host)
        result.update({"host_executable": shutil.which(command) if command else None,
                       "note": "仅报告 PATH 中的 CLI、当前 Python 和显式目标；不调用宿主接口、不读取配置、不安装。CLI 可用不证明宿主已加载技能或模型具备所需能力。"})
        return result
    hermes = shutil.which("hermes")
    explicit_home = os.environ.get("HERMES_HOME")
    observed_home = Path(explicit_home).expanduser() if explicit_home else None
    interpreter = None
    # These are candidates derived from the observed executable/home, never WSL mappings.
    roots = [observed_home] if observed_home else []
    if hermes:
        roots.append(Path(hermes).resolve().parent.parent)
    for root in roots:
        for candidate in (root / "hermes-agent" / "venv" / "Scripts" / "python.exe",
                          root / "hermes-agent" / ".venv" / "bin" / "python",
                          root / "hermes-agent" / "venv" / "bin" / "python"):
            if candidate.is_file():
                interpreter = candidate
                break
        if interpreter:
            break
    result.update({"host_executable": hermes, "hermes_executable": hermes,
              "HERMES_HOME": explicit_home, "HERMES_PROFILE": os.environ.get("HERMES_PROFILE"),
              "hermes_python": str(interpreter) if interpreter else None,
              "note": "以实际 Hermes 会话中探测为准；不自动安装、不读取 .env、不推导 WSL 路径。环境探测不证明宿主已加载技能或模型具备所需能力。"})
    if interpreter:
        code = '''import json,sys
from hermes_constants import get_hermes_home
from hermes_cli.profiles import get_active_profile,get_active_profile_name
home=get_hermes_home()
out={"home":str(home),"profile":get_active_profile_name(),"sticky_profile":get_active_profile(),"python":sys.executable,"python_version":sys.version.split()[0],"skills_dir":str(home/"skills")}
try:
 import yaml
 c=yaml.safe_load((home/"config.yaml").read_text(encoding="utf-8")) or {}
 out["model"]={k:c.get("model",{}).get(k) for k in ("default","provider")}
 out["terminal_backend"]=c.get("terminal",{}).get("backend")
 out["external_skills_dirs"]=c.get("skills",{}).get("external_dirs",[])
except (OSError,ImportError,ValueError,AttributeError):
 out["config_status"]="unreadable"
print(json.dumps(out,ensure_ascii=True))'''
        try:
            proc = subprocess.run([str(interpreter), "-B", "-c", code], capture_output=True, text=True,
                                  encoding="utf-8", timeout=15, cwd=interpreter.parent.parent.parent)
            if proc.returncode == 0:
                result["observed"] = json.loads(proc.stdout)
                result["discovery_status"] = "observed_local_runtime"
            else:
                result["probe_error"] = "Hermes 只读接口探测失败；没有输出潜在敏感诊断内容"
        except (OSError, subprocess.TimeoutExpired, ValueError):
            result["probe_error"] = "Hermes 只读接口不可用或超时"
    return result


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="GEO 完整技能安装器（不修改宿主配置）")
    p.add_argument("--host", choices=HOSTS, default="generic", help="宿主标签，默认 generic；不自动选择安装目录")
    p.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--skills-dir", type=Path, help="明确的宿主技能父目录")
    p.add_argument("--data-dir", type=Path, help="独立的配置、规则、索引和任务目录")
    p.add_argument("--upgrade", action="store_true")
    p.add_argument("--probe", action="store_true", help="只读探测当前环境，不安装")
    args = p.parse_args()
    if args.probe:
        emit(probe(args.host, skills=args.skills_dir, data=args.data_dir))
        return 0
    if args.skills_dir is None or args.data_dir is None:
        p.error("安装必须显式指定 --skills-dir 和 --data-dir")
    try:
        emit(install(checked_path(args.source), checked_path(args.skills_dir), checked_path(args.data_dir), args.upgrade, args.host))
        return 0
    except InstallError as exc:
        emit({"error": str(exc)}, error=True)
        return 2
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        # Do not expose arbitrary exception text, which may contain source secrets.
        emit({"error": "安装未完成：检查路径分离、既有版本、数据目录和 ZIP 安全性；默认不覆盖，请按文档使用 --upgrade。"}, error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
