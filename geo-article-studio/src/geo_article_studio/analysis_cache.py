"""Versioned, local reuse of validated topic analysis; never an authority for facts."""
import hashlib
import json
from pathlib import Path

from .learning import now
from .storage import atomic_json, read_json, task_lock


CACHE_VERSION=1


def _hash(value):
    encoded=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def fingerprint(task,rule_snapshot,config_fingerprint):
    """Every input capable of changing topic selection or its evidence is bound."""
    return _hash({'cache_version':CACHE_VERSION,'product':task['product'],
                  'sources':task['sources'],'facts':task['facts'],
                  'rules':rule_snapshot,'config':config_fingerprint,
                  'chat_scope':task['chat_scope'],'extra_requirements':task['extra_requirements'],
                  'geo_brief':task.get('geo_brief'),'text_source':task['text_source'],
                  'editorial_version':task.get('editorial_version')})


class AnalysisCache:
    def __init__(self,workspace_root):
        self.root=Path(workspace_root)/'analysis-cache'

    def _path(self,key):
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('分析缓存指纹无效')
        return self.root/f'{key}.json'

    def load(self,key,*,strict=False):
        path=self._path(key)
        if self.root.is_symlink() or path.is_symlink():
            if strict:raise ValueError('分析缓存路径无效')
            return None
        if not path.exists():return None
        try:
            record=read_json(path)
            if (record.get('version')!=CACHE_VERSION or record.get('fingerprint')!=key
                or record.get('result_hash')!=_hash(record.get('result'))
                or not isinstance(record.get('source_task_id'),str)):
                raise ValueError('分析缓存校验失败')
            return record
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
            if strict:raise ValueError('分析缓存损坏或已变化，请重新分析') from None
            return None

    def store(self,key,result,source_task_id):
        if self.root.is_symlink() or self._path(key).is_symlink():
            raise ValueError('分析缓存路径无效')
        record={'version':CACHE_VERSION,'fingerprint':key,'result':result,
                'result_hash':_hash(result),'source_task_id':source_task_id,'created_at':now()}
        with task_lock(self.root/'cache.lock'):
            atomic_json(self._path(key),record)
        return record
