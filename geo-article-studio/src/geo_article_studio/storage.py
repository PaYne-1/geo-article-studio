"""Atomic internal records, OS locks, and verified non-overwriting publication."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink(): raise ValueError('拒绝符号链接写入')
    encoded=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(encoded); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
        if read_json(path)!=data: raise ValueError('写入回读校验失败')
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(path):
    with Path(path).open('r',encoding='utf-8-sig') as f: return json.load(f)


def safe_name(text,max_length=64):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(text)).strip().rstrip('. ')
    name=name[:max_length].rstrip('. ') or '未命名'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',name,re.I): name='_'+name
    return name


@contextmanager
def task_lock(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink(): raise RuntimeError('任务锁不可为符号链接')
    f=path.open('a+b')
    try:
        f.seek(0,2)
        if f.tell()==0: f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError: raise RuntimeError('任务正在执行，不能重复启动') from None
        try: yield
        finally:
            f.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_UN)
    finally: f.close()


def _article_manifest(root,expected_images):
    from .images import validate_image
    root=Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('暂存目录无效')
    files={}; images=[]
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file(): raise ValueError('成品包含非法文件或目录')
        if path.name in {'标题.txt','正文.txt','图片审核状态.txt'}:
            try: content=path.read_text(encoding='utf-8')
            except UnicodeError: raise ValueError('正文和标题必须为 UTF-8') from None
            if not content.strip() or content.startswith('\ufeff'): raise ValueError('标题正文不能为空或包含 BOM')
            if path.name=='标题.txt' and len(content.strip().splitlines())!=1: raise ValueError('只允许一个最终标题')
            if path.name=='图片审核状态.txt' and '未做视觉审核' not in content:raise ValueError('图片审核状态说明无效')
            files[path.name]={'hash':file_hash(path),'bytes':path.stat().st_size}
        elif re.fullmatch(r'配图_[0-9]{2,}\.(png|jpg|jpeg|webp)',path.name):
            info=validate_image(path)
            files[path.name]={k:v for k,v in info.items() if k!='path'}
            images.append(int(path.stem.split('_')[1]))
        else: raise ValueError('内部记录或未知文件不可混入成品')
    if not {'标题.txt','正文.txt'}<=files.keys(): raise ValueError('缺少标题或正文')
    if sorted(images)!=list(range(1,expected_images+1)): raise ValueError('配图数量或顺序不符合计划')
    return {'files':dict(sorted(files.items())),'image_count':expected_images}


def publish_article(staging_dir,final_dir,expected_images):
    if type(expected_images) is not int or expected_images<0: raise ValueError('图数必须为非负整数')
    if Path(staging_dir).is_symlink(): raise ValueError('暂存目录不可为符号链接')
    staging=Path(staging_dir).resolve(); final=Path(final_dir)
    if final.is_symlink(): raise ValueError('最终目录不可为符号链接')
    final=final.resolve()
    if final==staging or final.is_relative_to(staging) or staging.is_relative_to(final): raise ValueError('暂存与成品路径必须隔离')
    manifest=_article_manifest(staging,expected_images)
    identifier=hashlib.sha256(str(final).encode('utf-8')).hexdigest()[:24]
    journal=staging.parent/('.publish-'+identifier+'.json')
    final.parent.mkdir(parents=True,exist_ok=True)
    pending=final.parent/('.pending-'+identifier)
    with task_lock(staging.parent/('.publish-'+identifier+'.lock')):
        if final.exists():
            if _article_manifest(final,expected_images)!=manifest: raise ValueError('历史成品不可覆盖')
            return manifest
        if pending.is_symlink(): raise ValueError('复制暂存目录不可为符号链接')
        if journal.exists():
            previous=read_json(journal)
            if previous.get('manifest')!=manifest or previous.get('final')!=str(final):
                raise ValueError('待恢复发布与本轮内容不一致')
        else:
            if pending.exists(): raise ValueError('目标暂存目录已存在，缺少恢复凭据')
            atomic_json(journal,{'phase':'copying','final':str(final),'manifest':manifest})
        pending.mkdir(exist_ok=True)
        for name,record in manifest['files'].items():
            target=pending/name
            if target.is_symlink(): raise ValueError('复制目标不可为符号链接')
            if target.exists() and file_hash(target)==record['hash']: continue
            with (staging/name).open('rb') as src, target.open('wb') as dst:
                shutil.copyfileobj(src,dst); dst.flush(); os.fsync(dst.fileno())
        if _article_manifest(pending,expected_images)!=manifest: raise ValueError('复制后校验失败')
        atomic_json(journal,{'phase':'verified','final':str(final),'manifest':manifest})
        # Pending and final share a parent/filesystem even when input staging is on another volume.
        if final.exists(): raise ValueError('目标目录已存在')
        pending.rename(final)
        if _article_manifest(final,expected_images)!=manifest: raise ValueError('发布后校验失败')
        atomic_json(journal,{'phase':'published','final':str(final),'manifest':manifest})
        return manifest
