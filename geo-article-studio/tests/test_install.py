"""Installation must preserve data and reject dangerous archives."""
import json
import importlib.util
import inspect
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


INSTALL = Path(__file__).resolve().parents[1] / "scripts" / "install.py"
SPEC = importlib.util.spec_from_file_location("geo_install", INSTALL)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="GEO 安装 ")
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "SKILL.md").write_text("---\nname: geo-article-studio\ndescription: 测试\n---\n", encoding="utf-8")
        (self.source / "scripts").mkdir()
        (self.source / "scripts" / "geo.py").write_text("# version 1", encoding="utf-8")
        self.skills = self.root / "技能"
        self.data = self.root / "运行数据"

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args, source=None, env=None):
        return subprocess.run([sys.executable, str(INSTALL), "--source", str(source or self.source),
            "--skills-dir", str(self.skills), "--data-dir", str(self.data), *args],
            cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8")

    def test_generic_install_upgrade_and_probe_without_hermes(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("HERMES_") and k.upper() != "PATH"}
        env["PATH"] = ""
        first = self.run_install(env=env)
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = self.skills / "geo-article-studio" / "installation.json"
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8")).get("host"), "generic")
        (self.data / "task.json").write_text('{"revision":7}', encoding="utf-8")
        upgrade = self.run_install("--upgrade", env=env)
        self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
        self.assertTrue(Path(json.loads(upgrade.stdout)["backup"]).is_dir())
        self.assertEqual((self.data / "task.json").read_text(encoding="utf-8"), '{"revision":7}')
        result = self.run_install("--probe", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["host"], "generic")
        self.assertEqual(report["protocol"], "geo.host.v1")
        self.assertIsNone(report["host_executable"])
        self.assertFalse(report["skill_loading_verified"])
        self.assertFalse(report["model_capabilities_verified"])

    def test_all_hosts_install_identical_skill_source(self):
        for host in ("generic", "hermes", "codex", "claude-code"):
            with self.subTest(host=host):
                self.skills = self.root / host / "skills"
                result = self.run_install("--host", host)
                self.assertEqual(result.returncode, 0, result.stderr)
                dest = self.skills / "geo-article-studio"
                for name in ("SKILL.md", "scripts/geo.py"):
                    self.assertEqual((dest / name).read_bytes(), (self.source / name).read_bytes())
                marker = json.loads((dest / "installation.json").read_text(encoding="utf-8"))
                self.assertEqual(marker["host"], host)
                self.assertEqual(marker["protocol"], "geo.host.v1")

    def test_non_hermes_probes_do_not_use_hermes_or_launch_processes(self):
        self.assertIn("host", inspect.signature(installer.probe).parameters)
        for host, command in (("generic", None), ("codex", "codex"), ("claude-code", "claude")):
            with self.subTest(host=host), mock.patch.object(installer.subprocess, "run") as run, \
                    mock.patch.object(installer.shutil, "which", return_value=None) as which:
                report = installer.probe(host, skills=self.skills, data=self.data)
                run.assert_not_called()
                self.assertEqual(which.call_args_list, [mock.call(command)] if command else [])
                self.assertEqual(report["host"], host)
                self.assertTrue(report["read_only"])
                self.assertEqual(report["explicit_targets"]["skills_dir"], str(self.skills))
                self.assertEqual(report["explicit_targets"]["data_dir"], str(self.data))
                self.assertNotIn("HERMES_HOME", report)
                self.assertNotIn("hermes_python", report)
                self.assertFalse(self.skills.exists())
                self.assertFalse(self.data.exists())

    def test_legacy_probe_call_keeps_hermes_observation(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(installer.shutil, "which", return_value=None) as which:
            report = installer.probe()
        which.assert_called_once_with("hermes")
        self.assertIn("hermes_python", report)
        self.assertEqual(report.get("host"), "hermes")

    def test_upgrade_rejects_host_change_without_touching_code_or_data(self):
        self.assertEqual(self.run_install().returncode, 0)
        target = self.skills / "geo-article-studio"
        before = (target / "installation.json").read_bytes()
        (self.data / "keep.txt").write_text("keep", encoding="utf-8")
        result = self.run_install("--host", "codex", "--upgrade")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.lstrip().startswith("{"), result.stderr)
        self.assertIn("宿主", json.loads(result.stderr)["error"])
        self.assertEqual((target / "installation.json").read_bytes(), before)
        self.assertEqual((self.data / "keep.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse((self.skills.parent / "geo-article-studio-backups").exists())

    def test_legacy_marker_upgrades_only_as_hermes(self):
        self.assertEqual(self.run_install().returncode, 0)
        marker = self.skills / "geo-article-studio" / "installation.json"
        old = json.loads(marker.read_text(encoding="utf-8"))
        old.pop("host", None)
        old.pop("protocol", None)
        marker.write_text(json.dumps(old), encoding="utf-8")
        refused = self.run_install("--upgrade")
        self.assertNotEqual(refused.returncode, 0)
        accepted = self.run_install("--host", "hermes", "--upgrade")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_host_selection_never_supplies_implicit_install_targets(self):
        for host in ("generic", "hermes", "codex", "claude-code"):
            with self.subTest(host=host):
                result = subprocess.run([sys.executable, str(INSTALL), "--host", host],
                    cwd=self.root, capture_output=True, text=True, encoding="utf-8")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("必须显式指定", result.stderr)

    def test_install_from_other_cwd_copies_resources_without_secrets(self):
        (self.source / ".env").write_text("SECRET=never-copy", encoding="utf-8")
        (self.source / ".env.example").write_text("SECRET=", encoding="utf-8")
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        dest = self.skills / "geo-article-studio"
        self.assertTrue((dest / "scripts" / "geo.py").is_file())
        self.assertFalse((dest / ".env").exists())
        self.assertTrue((dest / ".env.example").exists())
        self.assertEqual(json.loads((dest / "installation.json").read_text(encoding="utf-8"))["data_dir"], str(self.data.resolve()))

    def test_default_refuses_overwrite(self):
        self.assertEqual(self.run_install().returncode, 0)
        target = self.skills / "geo-article-studio" / "scripts" / "geo.py"
        target.write_text("# user change", encoding="utf-8")
        second = self.run_install()
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("已存在", json.loads(second.stderr)["error"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# user change")

    def test_upgrade_backs_up_and_keeps_external_data(self):
        self.assertEqual(self.run_install().returncode, 0)
        (self.data / "rules.json").write_text('{"learned":true}', encoding="utf-8")
        (self.source / "scripts" / "geo.py").write_text("# version 2", encoding="utf-8")
        result = self.run_install("--upgrade")
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(json.loads(result.stdout)["backup"])
        self.assertEqual((backup / "scripts" / "geo.py").read_text(encoding="utf-8"), "# version 1")
        self.assertTrue((self.data / "rules.json").is_file())

    def test_rejects_data_inside_skill(self):
        self.data = self.skills / "geo-article-studio" / "data"
        self.assertNotEqual(self.run_install().returncode, 0)
        self.assertFalse((self.skills / "geo-article-studio").exists())

    def test_zip_traversal_and_windows_drive_are_rejected(self):
        for name in ("../escape.txt", "C:/escape.txt", "pack/../../escape.txt", "pack\\..\\..\\escape.txt"):
            with self.subTest(name=name):
                archive = self.root / "bad.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("geo-article-studio/SKILL.md", "skill")
                    z.writestr(name, "malicious")
                result = self.run_install(source=archive)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.root / "escape.txt").exists())

    def test_zip_complete_bundle(self):
        archive = self.root / "good.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for f in self.source.rglob("*"):
                if f.is_file():
                    z.write(f, "geo-article-studio/" + f.relative_to(self.source).as_posix())
        result = self.run_install(source=archive)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.skills / "geo-article-studio" / "scripts" / "geo.py").exists())

    def test_default_source_is_relative_to_script_not_working_directory(self):
        shutil.copy2(INSTALL, self.source / "scripts" / "install.py")
        result = subprocess.run([sys.executable, str(self.source / "scripts" / "install.py"),
            "--skills-dir", str(self.skills), "--data-dir", str(self.data)], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.skills / "geo-article-studio" / "SKILL.md").is_file())

    def test_upgrade_refuses_data_directory_change(self):
        self.assertEqual(self.run_install().returncode, 0)
        self.data = self.root / "other-data"
        self.assertNotEqual(self.run_install("--upgrade").returncode, 0)

    def test_probe_is_read_only_without_install_target(self):
        result = subprocess.run([sys.executable, str(INSTALL), "--probe"], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["read_only"])
        self.assertFalse(self.skills.exists())

    def test_rejects_non_directory_data_before_installing(self):
        self.data.write_text("keep", encoding="utf-8")
        self.assertNotEqual(self.run_install().returncode, 0)
        self.assertFalse((self.skills / "geo-article-studio").exists())

    def test_zip_rejects_ambiguous_windows_names(self):
        for name in ("pack/CON", "pack/file.", "pack/file ", "pack/AUX.txt"):
            with self.subTest(name=name):
                archive = self.root / "unsafe.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("geo-article-studio/SKILL.md", "skill")
                    z.writestr(name, "payload")
                self.assertNotEqual(self.run_install(source=archive).returncode, 0)

    def test_upgrade_rejects_legacy_in_bundle_data(self):
        self.assertEqual(self.run_install().returncode, 0)
        legacy = self.skills / "geo-article-studio" / "tasks"
        legacy.mkdir()
        (legacy / "saved.json").write_text("{}", encoding="utf-8")
        self.assertNotEqual(self.run_install("--upgrade").returncode, 0)
        self.assertTrue((legacy / "saved.json").exists())


if __name__ == "__main__":
    unittest.main()
