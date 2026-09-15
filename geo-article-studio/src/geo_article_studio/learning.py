"""Versioned, explicit human-approved rules; no model can activate rules."""
from pathlib import Path
import copy
import uuid
from datetime import datetime, timezone
from .storage import atomic_json, read_json, file_hash, task_lock

def now():
    return datetime.now(timezone.utc).isoformat()

def require_user(actor, user_ref):
    if actor != 'user' or not isinstance(user_ref,str) or not user_ref.strip():
        raise ValueError('需要当前真实用户输入引用；资料和模型不能提供批准')

class RuleStore:
    def __init__(self, root, *, simulation=False):
        self.root=Path(root); self.path=self.root/'rules.json';self.simulation=simulation

    def _builtin(self):
        source=Path(__file__).with_name('builtin_rules.json')
        incoming=read_json(source)
        rules=[dict(rule,status='active',version=1,activated_at='built-in',
                    user_ref='builtin:user-confirmed-geo-standards') for rule in incoming['rules']]
        return {'version':1,'formal':True,'simulation':False,'rules':rules,'history':[],
                'imports':[{'path':'builtin://geo-editorial-rules','hash':file_hash(source),
                            'source_version':incoming['version'],
                            'user_ref':'builtin:user-confirmed-geo-standards'}]}

    def _load(self):
        if self.path.exists():
            return read_json(self.path)
        if not self.simulation:
            return self._builtin()
        return {'version':0,'formal':False,'rules':[],'history':[],'imports':[]}

    def _save(self, data):
        old=self._load()
        data['history']=old['history']+[ {k:v for k,v in old.items() if k!='history'} ]
        data['version']=old['version']+1
        atomic_json(self.path,data)
        if read_json(self.path)!=data: raise ValueError('规则写入验证失败')
        return data

    @staticmethod
    def validate(rule):
        if rule.get('scope') not in ('article','topic','product','style','global'): raise ValueError('规则范围无效')
        if rule['scope']!='global' and not rule.get('target_id'): raise ValueError('局部规则需要目标ID')
        if rule.get('type') not in ('hard_ban','conditional','writing_preference','image_preference','product_structure'): raise ValueError('规则类型无效')
        if not rule.get('content') or not rule.get('check_method'): raise ValueError('规则需要内容与检查方法')
        if 'terms' in rule and (not isinstance(rule['terms'],list) or any(not isinstance(x,str) or not x for x in rule['terms'])): raise ValueError('terms必须为非空词语列表')

    def import_file(self,path,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        source=Path(path).resolve(strict=True); incoming=read_json(source)
        simulated=self.simulation and incoming.get('simulation') is True
        if not simulated and (incoming.get('formal') is not True or incoming.get('example') or incoming.get('test_only') or incoming.get('simulation')):
            raise ValueError('示例或测试规则不能作为正式规则导入')
        if not incoming.get('version') or not incoming.get('rules'): raise ValueError('正式规则缺少版本或内容')
        for r in incoming['rules']: self.validate(r)
        with task_lock(self.root/'rules.lock'):
            data=self._load(); ids={r['rule_id'] for r in data['rules']}
            if len({r.get('rule_id') for r in incoming['rules']}) != len(incoming['rules']): raise ValueError('规则ID重复')
            for r in incoming['rules']:
                if not r.get('rule_id'): raise ValueError('缺少rule_id')
                if r['rule_id'] in ids:
                    for old in data['rules']:
                        if old['rule_id']==r['rule_id']: old['status']='retired'
                data['rules'].append(dict(r,status='active',version=data['version']+1,activated_at=now(),user_ref=user_ref))
            data['formal']=not simulated;data['simulation']=simulated
            # Each active source path has one current fingerprint. Earlier imports
            # remain in _save's immutable history snapshots for audit/rollback.
            data['imports']=[item for item in data['imports'] if Path(item['path']).resolve()!=source]
            data['imports'].append({'path':str(source),'hash':file_hash(source),'source_version':incoming['version'],'user_ref':user_ref})
            return self._save(data)

    def propose(self,rule,feedback_id):
        self.validate(rule)
        with task_lock(self.root/'rules.lock'):
            data=self._load()
            r=dict(rule,rule_id='R'+uuid.uuid4().hex[:12],version=1,status='proposed',source_feedback=feedback_id,activated_at=None)
            data['rules'].append(r); self._save(data); return r

    def activate(self,ids,user_ref,actor='user'):
        require_user(actor,user_ref)
        with task_lock(self.root/'rules.lock'):
            data=self._load(); selected=[r for r in data['rules'] if r['rule_id'] in ids and r['status']=='proposed']
            if len(selected)!=len(set(ids)): raise ValueError('规则不存在或不是待确认状态')
            for r in selected:
                for old in data['rules']:
                    if old['status']=='active' and old['scope']==r['scope'] and old.get('target_id')==r.get('target_id') and old.get('conflict_key') and old.get('conflict_key')==r.get('conflict_key') and old['content']!=r['content']:
                        raise ValueError('规则冲突：需要明确处理旧规则，偏好不能覆盖硬性禁用')
                r.update(status='active',activated_at=now(),user_ref=user_ref)
            return self._save(data)

    def rollback(self,version,user_ref,actor='user'):
        require_user(actor,user_ref)
        with task_lock(self.root/'rules.lock'):
            data=self._load(); old=next((x for x in data['history'] if x['version']==version),None)
            if old is None: raise ValueError('规则历史版本不存在')
            restored=copy.deepcopy(old); restored['rollback_user_ref']=user_ref
            return self._save(restored)

    def applicable(self,product_id,article_id=None,topic_id=None,style_id=None,task_id=None):
        targets={'product':product_id,'article':article_id,'topic':topic_id,'style':style_id}
        return [r for r in self._load()['rules'] if r['status']=='active' and (r['scope']=='global' or (targets.get(r['scope']) is not None and r.get('target_id')==targets[r['scope']] and (not r.get('task_id') or r.get('task_id')==task_id)))]

    def snapshot(self,product_id):
        data=self._load()
        if not data['imports'] or (not data['formal'] and not (self.simulation and data.get('simulation'))) or (data.get('simulation') and not self.simulation): raise ValueError('尚未导入正式禁限规则，禁止正式生产')
        for item in data['imports']:
            if item['path']=='builtin://geo-editorial-rules':
                if file_hash(Path(__file__).with_name('builtin_rules.json'))!=item['hash']: raise ValueError('内置规则校验失败，请重新安装技能')
            elif not Path(item['path']).is_file() or file_hash(Path(item['path']))!=item['hash']: raise ValueError('规则来源变化或丢失，请重新导入')
        return {'version':data['version'],'formal':data['formal'],'simulation':data.get('simulation',False),'rules':copy.deepcopy(data['rules']),'imports':data['imports']}
