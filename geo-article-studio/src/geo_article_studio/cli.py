"""Structured CLI for any capable agent host; optional persistent third-party text API."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
from .config import DEFAULT_SETTINGS, load_settings, validate_settings
from .storage import atomic_json, read_json
from .host_bridge import form_for
from .learning import RuleStore
from .images import ImageProvider, ProviderError
from .hosts import PROTOCOL, HOST_STAGES, assess_host, visual_available
from .text_api import TextProvider

def parser():
    p=argparse.ArgumentParser(description='GEO图文生产助手：通用Agent执行层')
    p.add_argument('--config',type=Path,default=Path(os.environ.get('GEO_CONFIG_PATH',str(Path.home()/'.geo-article-studio'/'settings.json'))))
    sub=p.add_subparsers(dest='command',required=True)
    def command(name,task=False,file=False,user=False):
        c=sub.add_parser(name)
        if task:c.add_argument('task_id')
        if file:c.add_argument('--file',type=Path,required=True)
        if user:c.add_argument('--user-ref',required=True)
        return c
    c=command('form');c.add_argument('trigger');c.add_argument('--file',type=Path)
    c=command('host-check');c.add_argument('--file',type=Path);c.add_argument('--stage',choices=HOST_STAGES,default='PREFLIGHT');c.add_argument('--mode',choices=['automatic','learning'],default='automatic');c.add_argument('--with-images',action='store_true')
    command('configure',file=True);command('doctor');command('index')
    c=command('search');c.add_argument('query');c.add_argument('--library',choices=list(DEFAULT_SETTINGS['libraries']));c.add_argument('--product-id');c.add_argument('--limit',type=int,default=10)
    c=command('start',user=True);c.add_argument('--product-id');c.add_argument('--mode',choices=['automatic','learning'],required=True);c.add_argument('--text-source',choices=['host','api'],required=True);c.add_argument('--brief-file',type=Path);c.add_argument('--scope-file',type=Path);c.add_argument('--requirements-file',type=Path)
    for name in ('status','next-action','run-image','run-text','export'):command(name,task=True)
    c=command('resolve-text-request',task=True,user=True);c.add_argument('request_id')
    for name in ('select','submit-result'):command(name,task=True,file=True,user=name=='select')
    for name in ('approve','revise'):
        c=command(name,task=True,user=True);c.add_argument('--action-id',required=True);c.add_argument('--revision',type=int,required=True)
        if name=='approve':c.add_argument('--rule-ids',nargs='*',default=[])
        else:
            c.add_argument('--feedback-file',type=Path,required=True);c.add_argument('--scope',default='article',choices=['article','topic','product','style','global']);c.add_argument('--target-id');c.add_argument('--image-id')
    for name in ('pause','resume','refresh'):command(name,task=True,user=True)
    c=command('fork-revision',task=True,user=True);c.add_argument('--feedback-file',type=Path,required=True);c.add_argument('--text-source',choices=['host','api'],required=True)
    c=command('retrieve',task=True);c.add_argument('query');c.add_argument('--library',required=True);c.add_argument('--limit',type=int,default=10)
    c=command('resolve-request',task=True,user=True);c.add_argument('request_id');c.add_argument('--resolution',required=True,choices=['confirmed_not_charged','confirmed_failed_charged'])
    c=command('recover-image',task=True,user=True);c.add_argument('request_id');c.add_argument('--file',type=Path,required=True)
    c=command('rules');c.add_argument('operation',choices=['show','import','activate','rollback']);c.add_argument('--file',type=Path);c.add_argument('--ids',nargs='*');c.add_argument('--version',type=int);c.add_argument('--user-ref')
    c=command('products');c.add_argument('operation',choices=['list','extract','candidates','facts','approve','resolve-conflict']);c.add_argument('--product-id');c.add_argument('--fact-id');c.add_argument('--file',type=Path);c.add_argument('--user-input');c.add_argument('--reject-ids',nargs='*')
    c=command('demo');c.add_argument('--root',type=Path,required=True);c.add_argument('--mode',choices=['learning','automatic','both'],default='both')
    return p

def doctor(settings):
    missing=[k for k,v in settings['libraries'].items() if not v]
    report={'python':sys.version.split()[0],'python_supported':sys.version_info>=(3,11),'libraries_missing':missing,'parsers':{x:bool(importlib.util.find_spec(m)) for x,m in [('docx','docx'),('xlsx','openpyxl'),('pdf','pypdf'),('images','PIL')]},
            'rules':{'ready':False},'image_provider':{'configured':bool(settings.get('image_provider')),'paid_request_sent':False},'host_contract':assess_host(settings),'visual_capability':visual_available(settings),'limits':settings['limits'],'note':'视觉标记是宿主声明，需实际查看图片验证；零图任务不需要图片凭据。'}
    if settings.get('workspace_root'):
        try: report['rules']={'ready':True,'version':RuleStore(settings['workspace_root']).snapshot('doctor')['version']}
        except ValueError as e:report['rules']['reason']=str(e)
    report['text_provider']=TextProvider(settings.get('text_provider')).check()
    if settings.get('image_provider'):
        try:report['image_provider']=ImageProvider(settings['image_provider']).check()
        except (ValueError,ProviderError):report['image_provider']['reason']='图片接口尚未完成非付费配置检查'
    report['ready_for_analysis']=not missing and bool(settings.get('workspace_root'))
    report['production_ready']=report['ready_for_analysis'] and report['rules']['ready']
    return report

def run(args):
    if args.command=='host-check':
        config=read_json(args.file) if args.file else load_settings(args.config) if args.config.is_file() else {}
        result=assess_host(config,stage=args.stage,mode=args.mode,has_images=args.with_images)
        return result,0 if result['ready'] else 2
    if args.command=='demo':
        from .demo import run_demo
        return run_demo(args.root,args.mode),0
    if args.command=='form':
        settings=load_settings(args.config) if args.config.is_file() else copy.deepcopy(DEFAULT_SETTINGS)
        return form_for(args.trigger,settings,read_json(args.file) if args.file else None),0
    if args.command=='configure':
        incoming=read_json(args.file)
        if args.config.is_file():
            from .config import _merge
            incoming=_merge(load_settings(args.config),incoming)
        if incoming.get('workspace_root') is None:incoming['workspace_root']=str(args.config.resolve().parent/'work')
        config=validate_settings(incoming)
        # Reject placing settings within any source library before writing.
        for root in config['libraries'].values():
            if root and args.config.resolve().is_relative_to(Path(root).resolve()):raise ValueError('普通配置不能写入源资料库')
        atomic_json(args.config,config)
        load_settings(args.config)
        return {'saved':str(args.config.resolve()),'missing_libraries':[k for k,v in config['libraries'].items() if v is None]},0
    if not args.config.is_file():raise ValueError('尚未配置；先运行form 配置任务，再configure --file本地配置文件')
    settings=load_settings(args.config)
    if args.command=='doctor':
        result=doctor(settings);return result,0 if result['production_ready'] else 2
    if not settings.get('workspace_root'):raise ValueError('缺少workspace_root；先完成首次配置')
    if args.command=='rules':
        r=RuleStore(settings['workspace_root'])
        if args.operation=='show':return r._load(),0
        if args.operation=='import':
            if not args.file:raise ValueError('缺少规则文件')
            return r.import_file(args.file,user_ref=args.user_ref),0
        if args.operation=='activate':return r.activate(args.ids or [],args.user_ref),0
        return r.rollback(args.version,args.user_ref),0
    from .libraries import LibraryIndex
    from .products import ProductRegistry
    index=LibraryIndex(settings)
    if args.command=='index':return index.update(),0
    if args.command=='search':return index.search(args.query,library_type=args.library,product_id=args.product_id,limit=args.limit),0
    products=ProductRegistry(settings,index)
    if args.command=='products':
        if args.operation=='list':return products.list_products(),0
        if args.operation=='extract':return products.extract_candidates(args.product_id),0
        if args.operation=='candidates':return products.add_candidates(args.product_id,read_json(args.file)),0
        if args.operation=='facts':return products.facts(args.product_id),0
        if args.operation=='approve':return products.approve(args.fact_id,args.user_input),0
        return products.resolve_conflict(args.fact_id,args.user_input,args.reject_ids or []),0
    from .workflow import Engine
    e=Engine(settings,index=index,products=products);cmd=args.command
    if cmd=='start':
        pid=args.product_id
        if not pid:
            found=[x for x in products.list_products() if x['name']==settings['default_product_name']]
            if len(found)!=1:raise ValueError('默认产品'+settings['default_product_name']+'尚未注册或版本不唯一；请选择实际产品，禁止替换为其他产品')
            pid=found[0]['product_id']
        result=e.start(pid,args.mode,user_ref=args.user_ref,text_source=args.text_source,geo_brief=read_json(args.brief_file) if args.brief_file else None,chat_scope=read_json(args.scope_file) if args.scope_file else None,extra_requirements=args.requirements_file.read_text(encoding='utf-8') if args.requirements_file else '')
    elif cmd in ('status','next-action','run-image','run-text','export'):
        result=getattr(e,cmd.replace('-','_'))(args.task_id)
        if cmd=='export':return result if result else {'state':'PLANNING','note':'当前篇已交付；继续next-action完成剩余文章'},0
        if cmd=='next-action' and result['kind']=='FINISHED':return result['output_path'],0
    elif cmd=='select':result=e.select(args.task_id,read_json(args.file),user_ref=args.user_ref)
    elif cmd=='submit-result':
        envelope=read_json(args.file)
        if set(envelope)-{'action_id','expected_revision','result','actor','user_ref','protocol','producer'}:raise ValueError('提交信封含未知字段')
        if envelope.get('protocol',PROTOCOL)!=PROTOCOL:raise ValueError('不支持的宿主桥接协议版本')
        result=e.submit(args.task_id,envelope['action_id'],envelope['expected_revision'],envelope['result'],actor=envelope.get('actor','model'),user_ref=envelope.get('user_ref'),producer=envelope.get('producer'))
    elif cmd=='approve':result=e.approve(args.task_id,args.action_id,args.revision,user_ref=args.user_ref,rule_ids=args.rule_ids)
    elif cmd=='revise':result=e.revise(args.task_id,args.action_id,args.revision,args.feedback_file.read_text(encoding='utf-8'),user_ref=args.user_ref,scope=args.scope,target_id=args.target_id,image_id=args.image_id)
    elif cmd in ('pause','resume','refresh'):result=getattr(e,cmd)(args.task_id,user_ref=args.user_ref)
    elif cmd=='retrieve':result=e.retrieve(args.task_id,args.query,args.library,args.limit)
    elif cmd=='resolve-request':result=e.resolve_request(args.task_id,args.request_id,args.resolution,user_ref=args.user_ref)
    elif cmd=='resolve-text-request':result=e.resolve_text_request(args.task_id,args.request_id,user_ref=args.user_ref)
    elif cmd=='recover-image':result=e.recover_image(args.task_id,args.request_id,args.file,user_ref=args.user_ref)
    elif cmd=='fork-revision':result=e.fork_revision(args.task_id,args.feedback_file.read_text(encoding='utf-8'),user_ref=args.user_ref,text_source=args.text_source)
    else:raise ValueError('未知命令')
    code=3 if isinstance(result,dict) and (result.get('state') in ('PAUSED','PARTIAL','NEEDS_CONFIG') or result.get('kind')=='BLOCKED') else 0
    # Mutation acknowledgements expose no raw config/snapshots; next-action is the deliberate model context boundary.
    if cmd not in ('status','next-action') and isinstance(result,dict) and 'task_id' in result:
        result={k:result.get(k) for k in ('task_id','state','stage','revision','action_id','error')}
    return result,code

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    try:
        args=parser().parse_args(argv);result,code=run(args)
        print(result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,indent=2))
        return code
    except ProviderError as e:
        print(json.dumps({'ok':False,'error':'模型或图片服务检查或执行失败','code':e.code},ensure_ascii=False));return 3
    except (ValueError,OSError,KeyError,TypeError) as e:
        from .libraries import redact
        message=redact(str(e)) if isinstance(e,ValueError) else '输入文件、字段或环境无效；请使用doctor和--help核查'
        # Never echo a server exception body or environment values.
        print(json.dumps({'ok':False,'error':message},ensure_ascii=False));return 2
