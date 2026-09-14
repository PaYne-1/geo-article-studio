#!/usr/bin/env python3
"""Build a source ZIP from an explicit source-file allowlist, never runtime data."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT_FILES={'SKILL.md','README.md','pyproject.toml','.env.example','.gitignore','constraints-tested.txt'}
TREES={'src','scripts','config','prompts','references','tests','docs'}
SUFFIXES={'.py','.md','.json','.toml','.txt','.csv','.jsonl','.html','.png','.jpg','.jpeg','.webp'}

def build(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.is_relative_to(source):raise ValueError('发布包必须位于源码目录之外')
    if destination.exists():raise ValueError('发布包已存在，拒绝覆盖')
    files=[]
    for p in sorted(source.rglob('*')):
        rel=p.relative_to(source)
        if p.is_symlink():raise ValueError('包源含符号链接')
        if not p.is_file():continue
        if any(x in ('__pycache__','.pytest_cache','.venv','build','dist') or x.endswith('.egg-info') for x in rel.parts):continue
        if rel.as_posix() not in ROOT_FILES and (rel.parts[0] not in TREES or p.suffix not in SUFFIXES):continue
        if p.name.startswith('.env') and p.name!='.env.example':continue
        if rel.parts[0]=='config' and '.example.' not in p.name:continue
        files.append((p,rel))
    if not any(rel.as_posix()=='SKILL.md' for _,rel in files):raise ValueError('缺少SKILL.md')
    destination.parent.mkdir(parents=True,exist_ok=True)
    manifest=[]
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p,rel in files:
            data=p.read_bytes();name='geo-article-studio/'+rel.as_posix()
            z.writestr(name,data);manifest.append(hashlib.sha256(data).hexdigest()+'  '+name)
        z.writestr('geo-article-studio/manifest.sha256','\n'.join(manifest)+'\n')
    with zipfile.ZipFile(destination) as z:
        if z.testzip():raise ValueError('ZIP校验失败')
    return {'path':str(destination),'files':len(files)+1,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

if __name__=='__main__':
    import json
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.source,a.output),ensure_ascii=False))
