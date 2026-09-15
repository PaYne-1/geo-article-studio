"""Durable state machine. All permissions and publication gates live here."""
import copy
import hashlib
import json
import re
import shutil
import sys
import uuid
from pathlib import Path
from datetime import datetime
from .storage import atomic_json, read_json, file_hash, task_lock, safe_name, publish_article
from .learning import RuleStore, require_user, now
from .host_bridge import SCHEMAS, validate_result
from .review import check_text, validate_review
from .hosts import PROTOCOL, assess_host, require_declared_capabilities, visual_available, producer_identity
from .text_api import TextProvider, uses_text_api
from . import editorial
from .config import api_resolution_ready

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def execution_config_digest(value):
    """Ignore retry timing/policy fields that do not change requested content or providers."""
    stable=copy.deepcopy(value)
    stable.pop('text_retry_policy',None)
    if isinstance(stable.get('text_provider'),dict):
        stable['text_provider'].pop('timeout_seconds',None)
    return digest(stable)

def action_source_ids(task,article,stage):
    """Keep whole-library evidence local once a human has selected a topic."""
    if article is None or stage in ('PREFLIGHT','ANALYZING'):
        return set(task['sources'])
    topic=next((row for row in task.get('topics',[]) if row.get('topic_id')==article.get('topic_id')),None)
    selected=set(topic.get('source_ids',[]) if topic else [])
    for fact in task.get('facts',[]):
        selected.update(fact.get('source_ids') or ([fact['source_id']] if fact.get('source_id') else []))
    if stage in ('IMAGE_PLANNING','IMAGE_REVIEW','FINAL_REVIEW'):
        selected.update(sid for sid,row in task['sources'].items()
                        if row.get('library_type') in ('reference_images','product_images'))
    return selected & set(task['sources'])

def validate_selection(topics,selection):
    lookup={t['topic_id']:t for t in topics}; seen=set(); articles=[]
    if not isinstance(selection,list) or not selection: raise ValueError('请人工多选主题并填写数量')
    for row in selection:
        tid=row.get('topic_id'); count=row.get('article_count'); counts=row.get('image_counts')
        if tid not in lookup or tid in seen: raise ValueError('主题未知或重复')
        seen.add(tid)
        if type(count) is not int or count<=0: raise ValueError('文章数量必须为正整数')
        if not isinstance(counts,list) or len(counts)!=count or any(type(n) is not int or n<0 for n in counts): raise ValueError('逐篇图片数必须明确填写非负整数，长度与篇数相等')
        if count>len(set(lookup[tid]['distinct_angles'])): raise ValueError('不同文章角度不足，需补资料或由用户减少篇数')
        for i,n in enumerate(counts):
            articles.append({'article_id':f'A{len(articles)+1:03d}','topic_id':tid,'angle':lookup[tid]['distinct_angles'][i],'image_count':n,'revision':1,'results':{},'images':{},'text_attempts':0,'status':'pending'})
    return articles

class Engine:
    def __init__(self,settings,*,index=None,products=None,simulation=False):
        if settings.get('simulation') and not simulation: raise ValueError('模拟配置只能用于显式离线demo')
        self.settings=copy.deepcopy(settings)
        self.root=Path(settings['workspace_root']).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.output=Path(settings['output_root']).resolve() if settings.get('output_root') else None
        if index is None:
            from .libraries import LibraryIndex
            index=LibraryIndex(settings)
        if products is None:
            from .products import ProductRegistry
            products=ProductRegistry(settings,index)
        self.index=index;self.products=products;self.rules=RuleStore(self.root,simulation=simulation);self.simulation=simulation

    def _path(self,tid):
        if not re.fullmatch(r'[a-f0-9]{16}',tid): raise ValueError('任务编号无效')
        p=self.root/'tasks'/tid
        if p.is_symlink() or p.parent.is_symlink() or not p.resolve().is_relative_to(self.root) or p.resolve().parent!=(self.root/'tasks').resolve(): raise ValueError('任务路径越界')
        return p

    def _load(self,tid): return read_json(self._path(tid)/'state.json')
    def _lock(self,tid): return task_lock(self._path(tid)/'task.lock')

    def _save(self,t):
        t['revision']+=1;t['action_id']=uuid.uuid4().hex;t['updated_at']=now()
        atomic_json(self._path(t['task_id'])/'state.json',t)
        return copy.deepcopy(t)

    def status(self,tid):
        with self._lock(tid): return self._load(tid)

    def _article(self,t):
        return t['articles'][t['current_article']] if t['articles'] and t['current_article']<len(t['articles']) else None

    def _reflection(self,t,a):
        return next((f for f in t['feedback'] if f['status']=='revised_waiting_approval' and not f.get('reflection') and (not a or f['object_id']==a['article_id'])),None)

    def _sources(self,product,scope):
        rows=[]
        for lib in ('chat','product_info'):
            filters={k:v for k,v in scope.items() if k!='query'}
            if lib=='chat':
                filters={**filters,'role':'customer'}
                rows.extend(self.index.search(scope.get('query',''),library_type=lib,product_id=product['product_id'],limit=200,**filters))
                rows.extend(self.index.search(scope.get('query',''),library_type=lib,product_id='general',limit=200,**filters))
            else:rows.extend(self.index.search('',library_type=lib,product_id=product['product_id'],limit=30,**filters))
        return {r['source_id']:r for r in rows}

    def start(self,product_id,mode,*,user_ref,actor='user',chat_scope=None,extra_requirements='',text_source=None,geo_brief=None):
        require_user(actor,user_ref)
        require_declared_capabilities(self.settings,mode=mode)
        if mode not in ('automatic','learning'): raise ValueError('模式必须为learning或automatic')
        if text_source not in ('host','api'):raise ValueError('请选择当前宿主或第三方文字API')
        if text_source=='api' and not api_resolution_ready(self.settings,'text'):raise ValueError('第三方文字模型的接口协议尚未由Agent核对完成，请先完成技术配置')
        if text_source=='api' and not TextProvider(self.settings.get('text_provider')).check()['ok']:raise ValueError('第三方文字API未配置完整或凭据未接入，请先配置任务')
        if geo_brief is not None:geo_brief=editorial.validate_brief(geo_brief)
        product=self.products.get(product_id);report=self.index.update();scope=chat_scope or {}
        sources=self._sources(product,scope);facts=self.products.facts(product_id,approved_only=True)
        for fact in facts:
            for sid in fact.get('source_ids', [fact['source_id']] if fact.get('source_id') else []): sources[sid]=self.index.get(sid)
        tid=uuid.uuid4().hex[:16]
        t={'task_id':tid,'product':product,'mode':mode,'state':'PREFLIGHT','stage':'PREFLIGHT','revision':0,'current_article':0,'articles':[],'topics':[],
           'sources':sources,'facts':facts,'coverage':report,'chat_scope':scope,'extra_requirements':extra_requirements,'results':{},'history':[],'approvals':[],'feedback':[],
           'requests':[],'editorial_version':editorial.VERSION,'geo_brief':geo_brief,'text_source':text_source,'text_requests':[],'rules_snapshot':None,'authorization':{'start_user_ref':user_ref,'text_source':text_source},'created_at':now(),'config_snapshot':copy.deepcopy(self.settings),'error':None,'simulation':self.simulation}
        with self._lock(tid): return self._save(t)

    def _check_action(self,t,aid,revision):
        if t['action_id']!=aid or type(revision) is not int or t['revision']!=revision: raise ValueError('action_id或版本过期；请重新展示当前对象')
        if t['state'] in ('PAUSED','PARTIAL','COMPLETED'): raise ValueError('任务已暂停或结束')

    def _source_path(self,row):
        if row.get('path'): return Path(row['path'])
        if row.get('file_path'): return Path(row['file_path'])
        return Path(self.settings['libraries'][row['library_type']])/row['location']['relative_path']

    def _check_snapshot(self,t):
        if execution_config_digest(t['config_snapshot'])!=execution_config_digest(self.settings): raise ValueError('运行配置已变化；请明确迁移任务或恢复原配置，不能混用快照')
        current_facts={f['fact_id']:f for f in self.products.facts(t['product']['product_id'],approved_only=True)}
        if any(f['fact_id'] not in current_facts or digest(f)!=digest(current_facts[f['fact_id']]) for f in t['facts']):raise ValueError('产品事实批准状态/内容变化或发现冲突；请refresh复审')
        for s in t['sources'].values():
            p=self._source_path(s)
            if not p.is_file() or file_hash(p)!=s['hash']: raise ValueError('本轮来源变更/丢失：'+s['source_id']+'；请刷新资料并复审')
        if t.get('rules_snapshot'):
            current=self.rules.snapshot(t['product']['product_id'])
            if current['version']!=t['rules_snapshot']['version']: raise ValueError('规则版本变化；请refresh使已有稿件重新审核')

    def next_action(self,tid):
        with self._lock(tid):
            t=self._load(tid);a=self._article(t);stage=t['stage'];state=t['state']
            self._verify_files(t)
            reflection=self._reflection(t,a) if state=='WAITING_APPROVAL' else None
            if reflection: stage='LEARNING_REVIEW'
            if state=='COMPLETED': kind='FINISHED'
            elif state in ('PAUSED','PARTIAL','WAITING_APPROVAL','WAITING_SELECTION','WAITING_COUNTS','NEEDS_CONFIG'): kind='NEEDS_USER'
            elif stage in ('GENERATING_IMAGES','EXPORT'): kind='NEEDS_TOOL'
            elif stage in ('IMAGE_REVIEW','FINAL_REVIEW') and a and a['image_count'] and not visual_available(self.settings):
                kind='NEEDS_USER' if t['mode']=='learning' else 'BLOCKED'
            else: kind='NEEDS_MODEL'
            if reflection: kind='NEEDS_MODEL'
            host_contract=assess_host(self.settings,stage=stage,mode=t['mode'],has_images=bool(a and a['image_count']))
            if state not in ('COMPLETED','PAUSED','PARTIAL') and host_contract['verification']=='declared_only' and not host_contract['ready']:kind='BLOCKED'
            api_action=kind=='NEEDS_MODEL' and uses_text_api(t,stage,a)
            if api_action:kind='NEEDS_TOOL'
            prompt_name={'PREFLIGHT':'preflight','ANALYZING':'analyze_chats','PLANNING':'plan_articles','WRITING':'write_article','TEXT_REVIEW':'review_text','IMAGE_PLANNING':'plan_images','IMAGE_REVIEW':'review_images','FINAL_REVIEW':'review_final'}.get(stage)
            if stage in editorial.REVIEW_STAGES:prompt_name={'FACT_REVIEW':'review_facts','GEO_REVIEW':'review_geo','CONTENT_REVIEW':'review_content'}[stage]
            if stage=='LEARNING_REVIEW':prompt_name='learn_from_feedback'
            prompt_path=Path(__file__).resolve().parents[2]/'prompts'/f'{prompt_name}.md'
            if prompt_name and not prompt_path.exists():prompt_path=Path(sys.prefix)/'share'/'geo-article-studio'/'prompts'/f'{prompt_name}.md'
            prompt=prompt_path.read_text(encoding='utf-8') if prompt_name and prompt_path.exists() else ''
            sources=[]
            selected_source_ids=action_source_ids(t,a,stage)
            for sid,s in t['sources'].items():
                if sid not in selected_source_ids:continue
                row={k:v for k,v in s.items() if k not in ('path','file_path','raw','text')}
                row['snippet']=row.get('snippet','')[:800]
                row['context_truncated']=len(s.get('snippet',''))>800;sources.append(row)
            # Only minimum redacted snippets leave the local retrieval layer.
            context={'product':t['product'],'facts':t['facts'],'sources':sources,'coverage':t['coverage'],'topics':t['topics'],
                     'article':a,'specifications':self.settings.get('defaults',{}),'extra_requirements':t['extra_requirements'],'rules':self._applicable(t,a),'feedback':[f for f in t['feedback'] if not a or f['object_id']==a['article_id']],
                     'other_articles':[{'angle':x['angle'],'body':x['results'].get('WRITING',{}).get('body','')} for x in t['articles'] if x!=a]}
            if t.get('editorial_version'):
                context['editorial_standards']=editorial.STANDARDS
                context['geo_brief']=a.get('geo_brief') if a else t.get('geo_brief')
            if stage in ('IMAGE_PLANNING','IMAGE_REVIEW','FINAL_REVIEW') and a and a['image_count']:
                refs={sid for p in a['results'].get('IMAGE_PLANNING',{}).get('images',[]) for sid in p['reference_image_ids']+p['product_image_ids']}
                context['visual_inputs']={'generated':a['images'],'references':[{'source_id':sid,'path':str(self._source_path(t['sources'][sid])),'hash':t['sources'][sid]['hash']} for sid in refs],'capability_verification_ref':self.settings.get('host',{}).get('visual_verification_ref')}
                context['image_authorizations']=self.settings.get('image_authorizations',{})
                context['reference_fallback']=self.settings.get('reference_fallback')
            return {'protocol':PROTOCOL,'host_contract':host_contract,'task_id':tid,'action_id':t['action_id'],'expected_revision':t['revision'],'kind':kind,'stage':state if state in ('PAUSED','PARTIAL','WAITING_SELECTION','WAITING_COUNTS','NEEDS_CONFIG') else stage,
                    'object_id':a['article_id'] if a else tid,'prompt_template':prompt,'input_refs':sources,'context':context,'result_schema':editorial.action_schema(SCHEMAS.get(stage),stage,bool(t.get('editorial_version'))),
                    'approval_required':state=='WAITING_APPROVAL' and not reflection,'content_hash':digest(a['results'] if a else t['results']),'error':t.get('error'),
                    'text_source':t.get('text_source','host'),'output_path':t.get('output_path') if state=='COMPLETED' else None,'tool': 'run-text' if api_action else 'export' if stage=='EXPORT' else 'run-image' if stage=='GENERATING_IMAGES' else None}

    def _applicable(self,t,a):
        rules=t['rules_snapshot']['rules'] if t.get('rules_snapshot') else []
        targets={'product':t['product']['product_id'],'article':a['article_id'] if a else None,'topic':a['topic_id'] if a else None,'style':self.settings.get('style_id')}
        return [r for r in rules if r['status']=='active' and (r['scope']=='global' or (targets.get(r['scope']) is not None and r.get('target_id')==targets[r['scope']] and (r['scope'] not in ('article','topic') or r.get('task_id')==t['task_id'])))]

    def select(self,tid,selection,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        with self._lock(tid):
            t=self._load(tid)
            if t['state'] not in ('WAITING_SELECTION','WAITING_COUNTS','NEEDS_CONFIG'): raise ValueError('当前不等待主题和数量')
            if isinstance(selection,list) and selection and all(isinstance(x,str) for x in selection):
                if any(x not in {r['topic_id'] for r in t['topics']} for x in selection): raise ValueError('未知主题')
                t['selected_topics']=selection;t['state']='WAITING_COUNTS';return self._save(t)
            articles=validate_selection(t['topics'],selection)
            if t.get('editorial_version'):
                for article in articles:
                    row=next(r for r in selection if r['topic_id']==article['topic_id'])
                    topic=next(x for x in t['topics'] if x['topic_id']==article['topic_id'])
                    candidate=copy.deepcopy(row.get('brief') or t.get('geo_brief') or {})
                    supplied_title=candidate.get('original_title')
                    user_confirmed_title=row.get('user_confirmed_title')
                    if user_confirmed_title is not None:
                        if not isinstance(user_confirmed_title,str) or not editorial.question_title(user_confirmed_title):
                            raise ValueError('人工确认标题必须是以问号结尾的问题型标题')
                        if supplied_title is not None and supplied_title.strip()!=user_confirmed_title.strip():
                            raise ValueError('文章简报标题与人工确认标题不一致')
                        candidate['original_title']=user_confirmed_title.strip()
                        article['geo_brief_title_source']='explicit_user_selection'
                    elif supplied_title is not None and supplied_title.strip()!=topic['question_summary'].strip():
                        raise ValueError('文章标题必须使用人工选中的聊天分析候选标题；如需改题请重新生成并选择候选标题')
                    else:
                        candidate['original_title']=topic['question_summary']
                        article['geo_brief_title_source']='current_topic_candidate'
                    article['geo_brief']=editorial.validate_brief(candidate)
                    article['geo_brief_user_ref']=user_ref
            if any(next(x for x in t['topics'] if x['topic_id']==a['topic_id'])['status']!='ready' for a in articles): raise ValueError('所选主题依据不足')
            missing=[];d=self.settings.get('defaults',{});num=sum(a['image_count'] for a in articles)
            if not t.get('editorial_version'):
                if not isinstance(d.get('article_length'),dict) or any(type(d['article_length'].get(k)) is not int or d['article_length'][k]<1 for k in ('min','max')): missing.append('defaults.article_length {min,max}')
                elif d['article_length']['max']<d['article_length']['min']: missing.append('article_length范围')
            if not self.output: missing.append('output_root')
            if num:
                if not api_resolution_ready(self.settings,'image'):missing.append('图片模型接口协议尚未由Agent核对完成')
                dims=d.get('image_dimensions');ratio=d.get('image_ratio')
                if not isinstance(dims,list) or len(dims)!=2 or any(type(n) is not int or n<1 for n in dims): missing.append('image_dimensions必须是两个正整数')
                if isinstance(ratio,str) and re.fullmatch(r'\d+:\d+',ratio) and isinstance(dims,list) and len(dims)==2:
                    rw,rh=map(int,ratio.split(':'))
                    if rw<1 or rh<1 or dims[0]*rh!=dims[1]*rw: missing.append('比例和像素尺寸不一致')
                else: missing.append('image_ratio须为宽:高')
                if d.get('image_format') not in ('png','jpeg','jpg','webp'): missing.append('image_format不支持')
                if d.get('image_text_policy') not in ('none','specified','auto'): missing.append('image_text_policy须为none、specified或auto')
                for k in ('image_ratio','image_dimensions','image_format','image_text_policy'):
                    if d.get(k) is None: missing.append('defaults.'+k)
                cap=self.settings.get('limits',{}).get('max_image_requests_per_task')
                if cap is not None and (type(cap) is not int or cap<num): missing.append('limits.max_image_requests_per_task（已填写时必须覆盖本轮图片数）')
                if not self.settings.get('image_provider'): missing.append('image_provider')
                if t['mode']=='automatic' and (not visual_available(self.settings) or not self.settings.get('host',{}).get('visual_verification_ref')): missing.append('host.visual_capability及真实视觉能力证明')
            if missing: raise ValueError('仅需补齐：'+', '.join(missing))
            t['rules_snapshot']=self.rules.snapshot(t['product']['product_id']);self._check_snapshot(t)
            if num:
                for lib in ('reference_images','product_images'):
                    for row in self.index.search('',library_type=lib,product_id=t['product']['product_id'],limit=30,is_image=True): t['sources'][row['source_id']]=row
                    if lib=='reference_images':
                        for row in self.index.search('',library_type=lib,product_id='general',limit=20,is_image=True): t['sources'][row['source_id']]=row
            t['articles']=articles;t['selection']=selection;t['authorization'].update(selection_user_ref=user_ref,total_images=num,total_articles=len(articles),limits=copy.deepcopy(self.settings.get('limits',{})))
            t['stage']=t['state']='PLANNING';return self._save(t)

    def _validate_sources(self,t,result):
        facts={f['fact_id'] for f in t['facts']};sources=set(t['sources'])
        def walk(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k in ('source_ids','reference_image_ids','product_image_ids') and any(x not in sources for x in v): raise ValueError('模型引用不存在的来源ID')
                    if k in ('fact_ids','supporting_fact_ids') and any(x not in facts for x in v): raise ValueError('引用未批准事实')
                    walk(v)
            elif isinstance(value,list):
                for item in value: walk(item)
        walk(result)

    def submit(self,tid,action_id,revision,result,*,actor='model',user_ref=None,producer=None,_text_request_id=None):
        producer=producer_identity(producer)
        if producer and actor!='model':raise ValueError('人工结果不能附带模型身份冒充模型审核')
        with self._lock(tid):
            t=self._load(tid);self._check_action(t,action_id,revision);stage=t['stage'];a=self._article(t)
            reflection=self._reflection(t,a) if t['state']=='WAITING_APPROVAL' else None
            actual_stage='LEARNING_REVIEW' if reflection else stage
            if uses_text_api(t,actual_stage,a):
                receipt=next((r for r in t.get('text_requests',[]) if r['request_id']==_text_request_id),None)
                if not receipt or receipt['status']!='RECEIVED' or receipt['action_id']!=action_id or receipt['revision']!=revision or receipt.get('result')!=result:raise ValueError('本任务选择文字API；必须由run-text取得结果，不能由宿主替代')
                receipt['status']='APPLIED'
            require_declared_capabilities(self.settings,stage=actual_stage,mode=t['mode'],has_images=bool(a and a['image_count']))
            if producer:t.setdefault('model_submissions',[]).append({'action_id':action_id,'revision':revision,'stage':actual_stage,'producer':producer,'identity_verification':'self_reported','at':now()})
            if reflection:
                if actor!='model': raise ValueError('复盘由当前宿主模型整理，不能伪造人工批准')
                validate_result('LEARNING_REVIEW',result)
                if result['feedback_id']!=reflection['feedback_id']:raise ValueError('复盘目标不符')
                reflection.update(reason=result['reason'],reason_uncertain=result['reason_uncertain'],corrective_action=result['corrective_action'],check_method=result['check_method'],reflection=copy.deepcopy(result))
                return self._save(t)
            if t['state']=='WAITING_APPROVAL': raise ValueError('当前等待人工批准，不接受重复模型提交')
            self._check_snapshot(t);self._verify_files(t);validate_result(stage,result);self._validate_sources(t,result)
            if stage in ('IMAGE_REVIEW','FINAL_REVIEW') and result.get('reviewer')=='human': require_user(actor,user_ref)
            elif actor!='model': raise ValueError('此动作应由当前宿主模型提交')
            if stage=='ANALYZING':
                topic_ids=[x['topic_id'] for x in result['topics']]
                if len(topic_ids)!=len(set(topic_ids)): raise ValueError('主题ID重复')
                for topic in result['topics']:
                    if t.get('editorial_version') and not editorial.question_title(topic['question_summary']):
                        raise ValueError('聊天分析候选必须是问题型钩子标题，并以问号结尾')
                    rows=[t['sources'][s] for s in topic['source_ids']]
                    if not rows or any(x['library_type']!='chat' or x['metadata'].get('role') not in ('customer','客户','user') for x in rows): raise ValueError('主题必须来自明确客户发问，客服或未知角色不得算客户诉求')
                    if topic['scope']=='product_specific' and any(x['product_id']!=t['product']['product_id'] for x in rows): raise ValueError('通用来源不得冒称产品专属反馈')
                    if topic['count_basis']=='conversation':
                        conv={(x['location']['relative_path'],x['metadata'].get('conversation_id')) for x in rows}
                        if any(c[1] in (None,'') for c in conv) or topic['verified_count']!=len(conv): raise ValueError('会话统计依据不可靠')
                    elif topic['count_basis']=='fragment' and topic['verified_count']!=len({(x['hash'],digest(x['location'])) for x in rows}): raise ValueError('片段统计不正确')
                    elif topic['count_basis']=='reported_aggregate':
                        if any(x['metadata'].get('evidence_type')!='customer_aggregate' or type(x['metadata'].get('reported_count')) is not int for x in rows):raise ValueError('汇总次数只能引用明确的客户关注统计行')
                        if topic['verified_count']!=sum(x['metadata']['reported_count'] for x in rows):raise ValueError('客户关注汇总次数不正确')
                    elif topic['count_basis']=='unknown' and topic['verified_count'] is not None: raise ValueError('未知统计不能填数字')
            if stage=='PLANNING' and result['angle']!=a['angle']: raise ValueError('策划角度必须与所选独立角度一致；更换需人工修改')
            if t.get('editorial_version') and stage=='PLANNING':editorial.validate_plan(result,a['geo_brief'])
            if stage=='WRITING':
                issues=check_text(result,t['facts'],self._applicable(t,a),[t['product']['name']])
                if t.get('editorial_version'):editorial.validate_draft(result,a['results']['PLANNING'],a['geo_brief'])
                else:
                    length=self.settings['defaults']['article_length']
                    if not length['min']<=len(result['body'])<=length['max']: issues.append('正文长度超出已配置范围')
                if issues: raise ValueError('文本确定性检查失败：'+'；'.join(issues))
            if stage=='IMAGE_PLANNING': self._validate_image_plan(t,a,result)
            if stage in ('TEXT_REVIEW','IMAGE_REVIEW','FINAL_REVIEW',*editorial.REVIEW_STAGES):
                if stage in ('TEXT_REVIEW',*editorial.REVIEW_STAGES):
                    issues=check_text(a['results']['WRITING'],t['facts'],self._applicable(t,a),[t['product']['name']])
                    if issues: raise ValueError('正式文本校验失败')
                passed=validate_review(stage,result,visual_capable=visual_available(self.settings),has_images=bool(a['image_count']),mode=t['mode'])
                if stage in ('IMAGE_REVIEW','FINAL_REVIEW') and a['image_count']:
                    if set(result['viewed_image_ids'])!=set(a['images']): raise ValueError('视觉审核未覆盖当前实际图片')
                if not passed:
                    t['history'].append({'stage':stage,'object_id':a['article_id'],'revision':t['revision'],'result':result})
                    if stage in ('TEXT_REVIEW',*editorial.REVIEW_STAGES) and a['text_attempts']<self.settings.get('limits',{}).get('max_text_revision_attempts',3):
                        a['text_attempts']+=1;a['review_feedback']=result
                        if t.get('editorial_version') and stage in editorial.REVIEW_STAGES:
                            for invalidated in ('PLANNING','WRITING',*editorial.REVIEW_STAGES,'IMAGE_PLANNING','IMAGE_REVIEW','FINAL_REVIEW'):
                                a['results'].pop(invalidated,None)
                            a['images']={};t['stage']=t['state']='PLANNING'
                        else:t['stage']=t['state']='WRITING'
                    else: t['resume_state']=stage;t['state']='PAUSED';t['error']='审核未通过或存在不确定项；请处理后继续'
                    return self._save(t)
            target=a['results'] if a else t['results']
            if stage in target: t['history'].append({'stage':stage,'object_id':a['article_id'] if a else tid,'result':copy.deepcopy(target[stage]),'revision':t['revision']})
            target[stage]=copy.deepcopy(result)
            for f in t['feedback']:
                if f['stage']==stage and f['status']=='pending_revision': f.update(new_revision=t['revision']+1,status='revised_waiting_approval',corrective_action='按当前反馈重新生成并交由独立审核',reason='用户反馈；具体语义原因由宿主复盘')
            if stage=='ANALYZING': t['topics']=result['topics'];t['state']='WAITING_SELECTION'
            elif t['mode']=='learning' and stage in ('PREFLIGHT','PLANNING','TEXT_REVIEW','IMAGE_PLANNING','IMAGE_REVIEW','FINAL_REVIEW',*editorial.REVIEW_STAGES):
                t['state']='WAITING_APPROVAL'
            else: self._advance(t)
            return self._save(t)

    def _advance(self,t):
        stage=t['stage'];a=self._article(t)
        next_stage={'PREFLIGHT':'ANALYZING','PLANNING':'WRITING','WRITING':'FACT_REVIEW' if t.get('editorial_version') else 'TEXT_REVIEW','FACT_REVIEW':'GEO_REVIEW','GEO_REVIEW':'CONTENT_REVIEW','CONTENT_REVIEW':'IMAGE_PLANNING' if a and a['image_count'] else 'FINAL_REVIEW','TEXT_REVIEW':'IMAGE_PLANNING' if a and a['image_count'] else 'FINAL_REVIEW',
                    'IMAGE_PLANNING':'GENERATING_IMAGES','GENERATING_IMAGES':'IMAGE_REVIEW','IMAGE_REVIEW':'FINAL_REVIEW','FINAL_REVIEW':'EXPORT'}[stage]
        t['stage']=t['state']=next_stage

    def approve(self,tid,action_id,revision,*,user_ref,actor='user',rule_ids=None):
        require_user(actor,user_ref)
        with self._lock(tid):
            t=self._load(tid);self._check_action(t,action_id,revision)
            if t['state']!='WAITING_APPROVAL': raise ValueError('当前步骤没有可批准版本')
            self._check_snapshot(t);a=self._article(t)
            if self._reflection(t,a): raise ValueError('修改后须先完成结构化复盘，再展示并确认')
            t['approvals'].append({'action_id':action_id,'revision':revision,'stage':t['stage'],'object_id':a['article_id'] if a else tid,'content_hash':digest(a['results'] if a else t['results']),'user_ref':user_ref,'at':now()})
            if rule_ids:
                allowed={f.get('proposed_rule_id') for f in t['feedback'] if not a or f['object_id']==a['article_id']}
                if not set(rule_ids).issubset(allowed): raise ValueError('只能确认当前对象明确展示的学习规则')
                self.rules.activate(rule_ids,user_ref);t['rules_snapshot']=self.rules.snapshot(t['product']['product_id'])
            for f in t['feedback']:
                if f['status']=='revised_waiting_approval' and (not a or f['object_id']==a['article_id']): f.update(status='confirmed',confirmed_at=now())
            self._advance(t);return self._save(t)

    def revise(self,tid,action_id,revision,feedback,*,user_ref,actor='user',scope='article',target_id=None,image_id=None):
        require_user(actor,user_ref)
        if not isinstance(feedback,str) or not feedback.strip(): raise ValueError('请说明当前对象的修改要求')
        with self._lock(tid):
            t=self._load(tid)
            if t['state']=='COMPLETED': raise ValueError('已交付任务不能覆盖；请fork-revision创建保留历史的新任务')
            if t['action_id']!=action_id or t['revision']!=revision: raise ValueError('版本已过期')
            a=self._article(t);stage=t['stage'];target=a['results'] if a else t['results']
            if image_id and (not a or image_id not in a['images'] or stage not in ('IMAGE_REVIEW','FINAL_REVIEW','EXPORT')): raise ValueError('只能修改当前已生成图片ID')
            revise_stage={'TEXT_REVIEW':'WRITING','IMAGE_REVIEW':'IMAGE_PLANNING','FINAL_REVIEW':'WRITING','EXPORT':'WRITING'}.get(stage,stage)
            if t.get('editorial_version') and stage in ('WRITING','TEXT_REVIEW','FINAL_REVIEW','EXPORT',*editorial.REVIEW_STAGES):revise_stage='PLANNING'
            if image_id: revise_stage='IMAGE_PLANNING'
            # Replanning is a prerequisite; body feedback is resolved only after
            # a new draft has passed all three editorial review rounds.
            feedback_stage='CONTENT_REVIEW' if t.get('editorial_version') and revise_stage=='PLANNING' and stage!='PLANNING' else revise_stage
            if revise_stage not in SCHEMAS: raise ValueError('当前对象需先完成配置/选题')
            t['history'].append({'revision':revision,'object_id':a['article_id'] if a else tid,'results':copy.deepcopy(target)})
            if a:
                if revise_stage=='IMAGE_PLANNING':a['previous_image_plan']=copy.deepcopy(a['results'].get('IMAGE_PLANNING'))
                order=['PLANNING','WRITING','TEXT_REVIEW',*editorial.REVIEW_STAGES,'IMAGE_PLANNING','IMAGE_REVIEW','FINAL_REVIEW']
                if revise_stage in order:
                    invalidated=order[order.index(revise_stage):]
                    for s in invalidated:a['results'].pop(s,None)
                    if t.get('editorial_version'):
                        for prior in t['feedback']:
                            if prior['object_id']==a['article_id'] and prior['stage'] in invalidated and prior['status']=='revised_waiting_approval':
                                t['history'].append({'reason':'feedback_revision_invalidated','revision':revision,'feedback':copy.deepcopy(prior)})
                                prior.update(status='pending_revision',new_revision=None,reason='待当前修订稿重新验证',confirmed_at=None)
                                prior.pop('reflection',None)
                if image_id:a['images'].pop(image_id)
                else:a['images']={}
                a['revision']+=1
            fid='F'+uuid.uuid4().hex[:12]
            if scope=='global': target_id=None
            elif target_id is None: target_id={'article':a['article_id'] if a else tid,'product':t['product']['product_id'],'topic':a['topic_id'] if a else None}.get(scope)
            rule=self.rules.propose({'scope':scope,'target_id':target_id,'task_id':tid if scope in ('article','topic') else None,'type':'writing_preference' if revise_stage in ('WRITING','PLANNING') else 'image_preference','content':feedback,'severity':'warning','check_method':'对照反馈进行语义/视觉检查'},fid)
            t['feedback'].append({'feedback_id':fid,'task_id':tid,'object_id':a['article_id'] if a else tid,'image_id':image_id,'stage':feedback_stage,'old_revision':revision,'new_revision':None,'problem':feedback,'feedback':feedback,'reason':'待验证','corrective_action':'重新生成受影响对象并复审','proposed_rule_id':rule['rule_id'],'scope':scope,'target_id':target_id,'status':'pending_revision','user_ref':user_ref,'confirmed_at':None})
            # A proposal must not invalidate active snapshots, but is available as current-object feedback.
            if t.get('rules_snapshot'): t['rules_snapshot']=self.rules.snapshot(t['product']['product_id'])
            t['stage']=t['state']=revise_stage;t['error']=None
            t['mode']='learning'  # Explicit feedback requires this revision to be shown and approved.
            return self._save(t)

    def pause(self,tid,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        # Separate atomic marker can be written while a provider call holds the task lock.
        atomic_json(self._path(tid)/'pause.json',{'user_ref':user_ref,'at':now()})
        with self._lock(tid):
            t=self._load(tid)
            if t['state']=='COMPLETED': return t
            if t['state']!='PAUSED': t['resume_state']=t['state']
            t['state']='PAUSED';return self._save(t)

    def resume(self,tid,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        with self._lock(tid):
            t=self._load(tid)
            if t['state'] not in ('PAUSED','PARTIAL'): raise ValueError('任务未暂停')
            self._check_snapshot(t);self._verify_files(t)
            if any(r['status'] in ('UNKNOWN','IN_FLIGHT') for r in t['requests']): raise ValueError('收费状态不明，禁止重发；请核对服务商账单并resolve-request')
            (self._path(tid)/'pause.json').unlink(missing_ok=True)
            t['state']=t.get('resume_state',t['stage']);t['error']=None;return self._save(t)

    def _validate_image_plan(self,t,a,result):
        images=result['images'];d=self.settings['defaults']
        if t.get('editorial_version'):editorial.validate_images(result,a['image_count'])
        if len(images)!=a['image_count'] or len({x['image_id'] for x in images})!=len(images): raise ValueError('图片计划数量或ID不正确')
        paragraphs=a['results']['WRITING']['body'].split('\n\n')
        for i,p in enumerate(images,1):
            if p['article_id']!=a['article_id'] or p['image_id']!=f'{a["article_id"]}_I{i:02d}': raise ValueError('图像ID必须绑定当前文章与顺序')
            if p['paragraph']>len(paragraphs): raise ValueError('图片未绑定真实正文段落')
            if p['show_product'] and not p['product_image_ids']: raise ValueError('展示产品必须有已批准基准图')
            if not p['reference_image_ids'] and not self.settings.get('reference_fallback',{}).get('user_ref'): raise ValueError('缺少合适参考图及已批准替代策略')
            if d['image_text_policy']=='none' and p['allowed_text']: raise ValueError('当前图中文字策略禁止文字')
            from .review import normalized
            from .libraries import redact
            affirmative=' '.join(p.get(k,'') for k in ('scene','people_actions','allowed_text','purpose'))
            if redact(p.get('prompt',''))!=p.get('prompt',''):raise ValueError('图片描述包含应本地脱敏的个人信息')
            for r in self._applicable(t,a):
                if r.get('type')=='hard_ban' and any(normalized(term) in normalized(affirmative) for term in r.get('terms',[]) if normalized(term)): raise ValueError('配图计划肯定表达命中硬性禁用')
            for key,lib in [('product_image_ids','product_images'),('reference_image_ids','reference_images')]:
                for sid in p[key]:
                    s=t['sources'][sid];meta=s['metadata']
                    if s['library_type']!=lib: raise ValueError('产品图与参考库用途不能混用')
                    authorization=self.settings.get('image_authorizations',{}).get(sid,{})
                    if not authorization.get('user_ref'): raise ValueError('所选图片尚未有当前配置的人工批准；源说明不是授权')
                    if authorization.get('hash')!=s['hash']: raise ValueError('图片授权与文件哈希不符，请人工核对新版本')
                    if key=='product_image_ids' and s['product_id']!=t['product']['product_id']: raise ValueError('产品基准图串用')
                    if meta.get('conflict'): raise ValueError('产品图与事实有冲突')
                    if not authorization.get('external_use_approved'): raise ValueError('图片尚未批准传给第三方服务')
                    if key=='product_image_ids' and (authorization.get('product_id')!=t['product']['product_id'] or authorization.get('version')!=t['product']['version']): raise ValueError('产品图授权版本与当前产品不符')
                    if key=='reference_image_ids' and not set(p.get('borrow',[])).issubset(set(authorization.get('allow_borrow',[]))): raise ValueError('参考借鉴因素超出已批准范围')
                    if key=='product_image_ids' and not set(authorization.get('immutable',[])).issubset(set(p.get('immutable',[]))): raise ValueError('产品不可改变项未完整纳入图片计划')
            if p['image_id'] in a['images'] and a['images'][p['image_id']]['plan_hash']!=digest(p):a['images'].pop(p['image_id'])

    def run_image(self,tid):
        from .images import validate_image
        from .images import ImageProvider, ProviderError
        with self._lock(tid):
            t=self._load(tid)
            if t['state']!='GENERATING_IMAGES': raise ValueError('当前不允许生成图片')
            self._check_snapshot(t);self._verify_files(t);a=self._article(t);d=self.settings['defaults'];limits=t['authorization']['limits']
            marker=self._path(tid)/'pause.json'
            if marker.exists(): t['resume_state']=t['state'];t['state']='PAUSED';return self._save(t)
            if any(r['status'] in ('UNKNOWN','IN_FLIGHT') for r in t['requests']):
                t['resume_state']=t['state'];t['state']='PAUSED';t['error']='外部请求状态不明，需核对收费';return self._save(t)
            plans=a['results']['IMAGE_PLANNING']['images'];pending=[x for x in plans if x['image_id'] not in a['images']]
            if not pending: self._advance(t);return self._save(t)
            p=pending[0]
            counted=[r for r in t['requests'] if not (r.get('status')=='FAILED' and r.get('error_code')=='output_exists')]
            attempts=[r for r in counted if r['image_id']==p['image_id']]
            request_cap=limits.get('max_image_requests_per_task')
            if len(attempts)>=limits.get('max_generation_attempts_per_image',3) or (request_cap is not None and len(counted)>=request_cap):
                t['resume_state']=t['state'];t['state']='PAUSED';t['error']='已达到含首次的尝试/调用上限';return self._save(t)
            config=self.settings['image_provider'];pricing=self.settings.get('image_pricing',{});price=pricing.get('price_per_request');max_cost=limits.get('max_cost')
            if max_cost is not None and (not pricing.get('verified_source') or not isinstance(price,(int,float)) or price<0 or pricing.get('currency')!=limits.get('currency') or (len(counted)+1)*price>max_cost):
                t['resume_state']=t['state'];t['state']='PAUSED';t['error']='金额硬上限缺少可靠计价或将超限';return self._save(t)
            provider=ImageProvider(config)
            if not provider.check().get('ok'):
                t['resume_state']=t['state'];t['state']='PAUSED';t['error']='图片服务配置/凭据缺失，未发出请求';return self._save(t)
            paths=[self._source_path(t['sources'][sid]) for sid in p['product_image_ids']+p['reference_image_ids']]
            rid=uuid.uuid4().hex;dest=self._path(tid)/'images'/a['article_id']/f'v{a["revision"]}'/f'{p["image_id"]}.{d["image_format"]}'
            dest.parent.mkdir(parents=True,exist_ok=True)
            req={'request_id':rid,'article_id':a['article_id'],'image_id':p['image_id'],'attempt':len(attempts)+1,'status':'IN_FLIGHT','cost':None,'estimated_cost':price,'started_at':now(),'references':p['product_image_ids']+p['reference_image_ids']}
            t['requests'].append(req);self._save(t)
            try:
                result=provider.generate(p['prompt'],paths,dest,dimensions=d['image_dimensions'],image_format=d['image_format'],request_id=rid)
                verified=validate_image(dest,d['image_dimensions'],d['image_format'])
                req.update(status='SUCCEEDED',cost=result.get('cost'),finished_at=now())
                a['images'][p['image_id']]={'path':str(dest),'hash':file_hash(dest),'validation':verified,'request_id':rid,'body_hash':digest(a['results']['WRITING']),'plan_hash':digest(p)}
            except ProviderError as e:
                req['status']='UNKNOWN' if e.status_unknown else 'FAILED';req['error_code']=e.code
                if e.status_unknown or not e.retryable:
                    t['resume_state']=t['state'];t['state']='PAUSED';t['error']='图片接口阻断：'+str(e.code)
            except (ValueError,OSError):
                req['status']='UNKNOWN';t['resume_state']=t['state'];t['state']='PAUSED';t['error']='图片落盘/校验异常；核对外部请求后恢复'
            if marker.exists() and t['state']!='PAUSED': t['resume_state']=t['state'];t['state']='PAUSED'
            if t['state']=='GENERATING_IMAGES' and len(a['images'])==a['image_count']: self._advance(t)
            return self._save(t)

    def resolve_request(self,tid,request_id,resolution,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        if resolution not in ('confirmed_not_charged','confirmed_failed_charged'): raise ValueError('仅接受已核实的失败状态；成功结果使用recover-image导入')
        with self._lock(tid):
            t=self._load(tid);r=next((x for x in t['requests'] if x['request_id']==request_id),None)
            if not r or r['status'] not in ('UNKNOWN','IN_FLIGHT'): raise ValueError('请求不存在或无需人工核对')
            r.update(status='FAILED',resolution=resolution,resolution_user_ref=user_ref);return self._save(t)

    def recover_image(self,tid,request_id,path,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        from .images import validate_image
        with self._lock(tid):
            t=self._load(tid);a=self._article(t);r=next((x for x in t['requests'] if x['request_id']==request_id),None)
            if not r or r['status'] not in ('UNKNOWN','IN_FLIGHT') or r['article_id']!=a['article_id']: raise ValueError('恢复请求与当前文章不匹配')
            p=Path(path).resolve(strict=True)
            if not p.is_relative_to(self._path(tid).resolve()): raise ValueError('人工下载结果必须先放到当前任务内部目录')
            d=self.settings['defaults'];v=validate_image(p,d['image_dimensions'],d['image_format']);plan=next(x for x in a['results']['IMAGE_PLANNING']['images'] if x['image_id']==r['image_id'])
            a['images'][r['image_id']]={'path':str(p),'hash':file_hash(p),'validation':v,'request_id':request_id,'body_hash':digest(a['results']['WRITING']),'plan_hash':digest(plan)}
            r.update(status='SUCCEEDED',resolution_user_ref=user_ref);return self._save(t)

    def _verify_files(self,t):
        for a in t['articles']:
            for im in a['images'].values():
                if not Path(im['path']).is_file() or file_hash(Path(im['path']))!=im['hash']: raise ValueError('已有图片丢失或哈希变化')
            if a.get('published_files'):
                for p,h in a['published_files'].items():
                    if not Path(p).is_file() or file_hash(Path(p))!=h: raise ValueError('已交付文件缺失或被修改')

    def export(self,tid):
        with self._lock(tid):
            t=self._load(tid);self._verify_files(t)
            if t['state']=='COMPLETED': return t['output_path']
            if t['state']!='EXPORT': raise ValueError('尚未通过当前文章终审')
            self._check_snapshot(t);a=self._article(t)
            if len(a['images'])!=a['image_count']: raise ValueError('图片文件数与任务不符')
            if t.get('editorial_version'):
                editorial.validate_draft(a['results']['WRITING'],a['results']['PLANNING'],a['geo_brief'])
                for review_stage in editorial.REVIEW_STAGES:
                    review=a['results'].get(review_stage)
                    if not review or not validate_review(review_stage,review):raise ValueError('GEO三轮独立审核尚未全部通过')
            if not t.get('output_path'):
                stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f');t['output_path']=str(self.output/f'{stamp}_{safe_name(t["product"]["name"])}_{tid}')
            staging=self._path(tid)/'staging'/a['article_id']/f'v{a["revision"]}';staging.mkdir(parents=True,exist_ok=True)
            text=a['results']['WRITING'];(staging/'标题.txt').write_text(text['title'],encoding='utf-8');(staging/'正文.txt').write_text(text['body'],encoding='utf-8')
            for i,plan in enumerate(a['results'].get('IMAGE_PLANNING',{}).get('images',[]),1):
                im=a['images'][plan['image_id']]
                if im['body_hash']!=digest(text) or im['plan_hash']!=digest(plan): raise ValueError('正文或图像计划已变化，图片失效')
                shutil.copyfile(im['path'],staging/f'配图_{i:02d}.{self.settings["defaults"]["image_format"]}')
            topic=next(x for x in t['topics'] if x['topic_id']==a['topic_id'])
            destination=Path(t['output_path'])/f'{t["current_article"]+1:03d}_{safe_name(topic["direction"])[:24]}_{safe_name(text["title"])[:32]}'
            publish_article(staging,destination,a['image_count'])
            a['published_files']={str(p):file_hash(p) for p in destination.iterdir() if p.is_file()};a['output_path']=str(destination);a['status']='published'
            t['current_article']+=1
            if t['current_article']<len(t['articles']): t['stage']=t['state']='PLANNING';self._save(t);return None
            if not all(x['status']=='published' for x in t['articles']): raise ValueError('仍有未完成计划项')
            mapping=self.settings.get('user_path_mapping')
            if mapping:
                if not self.settings.get('delivery_access',{}).get('verification_ref'): raise ValueError('用户访问映射未验证')
                # The real runtime path remains canonical; verified remote display path is explicit metadata only.
                t['user_access_mapping']=mapping
            t['state']=t['stage']='COMPLETED';self._save(t);return t['output_path']

    def retrieve(self,tid,query,library_type,limit=10):
        """Extend bounded context without changing the sources already snapshotted."""
        if type(limit) is not int or not 1<=limit<=30: raise ValueError('单次检索上限1至30')
        with self._lock(tid):
            t=self._load(tid)
            if t['state'] in ('COMPLETED','PAUSED','PARTIAL'): raise ValueError('此状态不能扩展上下文')
            rows=self.index.search(query,library_type=library_type,product_id=t['product']['product_id'],limit=limit)
            for r in rows:
                if r['source_id'] in t['sources'] and r['hash']!=t['sources'][r['source_id']]['hash']: raise ValueError('检索来源与快照冲突')
                t['sources'][r['source_id']]=r
            self._save(t);return rows

    def refresh(self,tid,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        with self._lock(tid):
            t=self._load(tid)
            if t['state']=='COMPLETED': raise ValueError('成品历史不可覆盖，请fork-revision')
            if any(r['status'] in ('UNKNOWN','IN_FLIGHT') for r in t['requests']): raise ValueError('先解决未知收费请求')
            if any(r['status'] not in ('APPLIED','RESOLVED') for r in t.get('text_requests',[])):raise ValueError('先核对并处理待决文字API请求')
            # Reanalysis is explicit; never reuse changed product evidence silently.
            self.index.update();t['history'].append({'reason':'explicit_refresh','user_ref':user_ref,'articles':copy.deepcopy(t['articles']),'sources':t['sources'],'rules_snapshot':t['rules_snapshot']})
            t['sources']=self._sources(t['product'],t['chat_scope']);t['facts']=self.products.facts(t['product']['product_id'],approved_only=True)
            t['rules_snapshot']=None;t['articles']=[];t['topics']=[];t['current_article']=0;t['results']={};t['stage']=t['state']='PREFLIGHT';t['config_snapshot']=copy.deepcopy(self.settings);t['error']=None
            t['editorial_version']=editorial.VERSION
            # A new delivery root prevents collisions with articles published before refresh.
            t.pop('output_path',None);(self._path(tid)/'pause.json').unlink(missing_ok=True)
            return self._save(t)

    def fork_revision(self,tid,feedback,*,user_ref,actor='user',text_source=None):
        require_user(actor,user_ref)
        original=self.status(tid)
        t=self.start(original['product']['product_id'],'learning',user_ref=user_ref,chat_scope=original['chat_scope'],extra_requirements=feedback,text_source=text_source)
        with self._lock(t['task_id']):
            t['parent_task_id']=tid;t['parent_output_path']=original.get('output_path');return self._save(t)

    def run_text(self,tid):
        from .text_api import run_text
        return run_text(self,tid)

    def resolve_text_request(self,tid,request_id,*,user_ref,actor='user'):
        from .text_api import resolve_text_request
        return resolve_text_request(self,tid,request_id,user_ref=user_ref,actor=actor)

    def switch_text_source(self,tid,text_source,*,user_ref,actor='user'):
        require_user(actor,user_ref)
        if text_source not in ('host','api'):raise ValueError('文字来源必须为host或api')
        with self._lock(tid):
            t=self._load(tid)
            if t['state']=='COMPLETED':raise ValueError('已交付任务请创建修订任务')
            if any(r['status'] in ('UNKNOWN','IN_FLIGHT') for r in t.get('text_requests',[])):
                raise ValueError('仍有收费状态未知的文字请求，需先处理')
            if text_source=='api' and not TextProvider(self.settings.get('text_provider')).check()['ok']:
                raise ValueError('第三方文字API未配置完整或凭据未接入')
            old=t.get('text_source','host')
            for request in t.get('text_requests',[]):
                if request['status'] not in ('APPLIED','RESOLVED'):
                    request.update(status='RESOLVED',previous_status=request['status'],
                                   automatic_resolution='abandoned_after_user_source_switch',resolution_user_ref=user_ref,resolved_at=now())
            t['text_source']=text_source
            t.setdefault('authorization',{}).setdefault('text_source_changes',[]).append(
                {'from':old,'to':text_source,'user_ref':user_ref,'at':now()})
            return self._save(t)

    def authorize_image_retry(self,tid,image_id,new_cap,*,user_ref,actor='user'):
        """Authorize one extra paid call after an actually failed visual review."""
        require_user(actor,user_ref)
        if type(new_cap) is not int or new_cap<1:raise ValueError('新图片调用上限必须为正整数')
        with self._lock(tid):
            t=self._load(tid);a=self._article(t)
            if t['state']!='PAUSED' or t['stage']!='IMAGE_REVIEW' or not a:
                raise ValueError('只能为视觉审核失败后暂停的当前文章授权重试')
            if image_id not in a.get('images',{}):raise ValueError('重试图片ID不属于当前文章')
            if any(r['status'] in ('UNKNOWN','IN_FLIGHT') for r in t.get('requests',[])):
                raise ValueError('仍有收费状态未知的图片请求，禁止授权重发')
            failed=any(row.get('stage')=='IMAGE_REVIEW' and row.get('object_id')==a['article_id']
                       and row.get('result',{}).get('verdict')=='failed' for row in t.get('history',[]))
            if not failed:raise ValueError('没有可核验的失败视觉审核记录')
            limits=t.setdefault('authorization',{}).setdefault('limits',{})
            old_cap=limits.get('max_image_requests_per_task')
            if type(old_cap) is not int or new_cap!=old_cap+1 or new_cap<len(t.get('requests',[]))+1:
                raise ValueError('本操作只允许把当前任务图片上限增加一次调用')
            old_image=copy.deepcopy(a['images'][image_id])
            old_path=Path(old_image['path']).resolve()
            if not old_path.is_relative_to(self._path(tid).resolve()):raise ValueError('失败图片路径越界')
            old_path.unlink(missing_ok=True)
            a['images'].pop(image_id)
            a['previous_image_plan']=copy.deepcopy(a['results'].get('IMAGE_PLANNING'))
            for stage in ('IMAGE_REVIEW','FINAL_REVIEW'):a['results'].pop(stage,None)
            limits['max_image_requests_per_task']=new_cap
            change={'from':old_cap,'to':new_cap,'image_id':image_id,'user_ref':user_ref,'at':now()}
            t['authorization'].setdefault('image_cap_changes',[]).append(change)
            t['history'].append({'reason':'authorized_image_retry','object_id':a['article_id'],
                                 'failed_image':old_image,'authorization':copy.deepcopy(change)})
            t['stage']=t['state']='IMAGE_PLANNING';t.pop('resume_state',None);t['error']=None
            return self._save(t)
