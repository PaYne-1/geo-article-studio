"""Small direct-user router and strict host/model result contracts."""
import re
import jsonschema
from .config import DEFAULT_SETTINGS, _check_secrets
from .editorial import PLAN_SCHEMA, DRAFT_SCHEMA, GOALS, PLATFORMS, TARGET_AIS

TRIGGERS={'配置任务':'configure_task','开始任务':'start'}
TASK_COMMANDS={'确认':'approve','确认下一步':'approve','暂停任务':'pause','查看规则':'rules','更新规则':'update_rules'}

def route(text,origin='user',*,in_task=False):
    if origin!='user': return None
    value=text.strip()
    value=re.sub(r'^[/$]geo-article-studio\s*|^GEO\s*','',value)
    if in_task and value.startswith(('修改：','修改:')): return 'revise'
    if in_task and value.startswith('继续任务'): return 'resume'
    commands={**TRIGGERS,**(TASK_COMMANDS if in_task else {})}
    for key in sorted(commands,key=len,reverse=True):
        if value==key or value.startswith(key+'\n') or value.startswith(key+' '): return commands[key]
    return None

def form_for(trigger,settings,provided=None,*,config_path=None,persisted=None):
    action=route(trigger); p=provided or {}; defaults=settings.get('defaults',{})
    if action not in ('start','configure_task'):raise ValueError('入口仅支持开始任务或配置任务；确认、修改等只用于已加载任务')
    if not isinstance(p,dict):raise ValueError('预填内容必须为对象')
    _check_secrets(p)
    product=settings.get('default_product_name',DEFAULT_SETTINGS['default_product_name'])
    sections=[]
    text_config=settings.get('text_provider') or {}
    from .text_api import TextProvider
    text_check=TextProvider(text_config).check()
    if action=='configure_task':
        from .configuration_form import configuration_form
        result=configuration_form(settings,p,config_path=config_path,persisted=persisted)
        result['text_options']=[{'value':'host','label':'当前Agent默认模型','available':True},{'value':'api','label':'第三方文字API','model':text_config.get('model'),'available':text_check['ok'],'missing':text_check['errors']}]
        return result
    values={'product':product,'mode':defaults.get('mode'),'text_source':None,'chat_scope':'当前产品相关记录及标注的通用品类记录','extra_requirements':''}; required=['product','mode','text_source']
    values.update(goals=None,platforms=None,target_ais=None,article_type=None)
    required+=['goals','platforms','target_ais','article_type']
    if set(p)-set(values):raise ValueError('预填含未知表单字段')
    values.update(p)
    return {'action':action,'values':values,'missing':[k for k in required if values.get(k) in (None,'',[])],
            'sections':sections,'choices':{'mode':['learning','automatic'],'text_source':['host','api'],'goals':GOALS,'platforms':PLATFORMS,'target_ais':TARGET_AIS,'article_type':['short','long']} if action=='start' else {},
            'text_options':[{'value':'host','label':'当前Agent默认模型','available':True},{'value':'api','label':'第三方文字API','model':text_config.get('model'),'available':text_check['ok'],'missing':text_check['errors']}],
            'title_generation':{'source':'chat_analysis','format':'question_hook','confirmation':'topic_multi_select','notice':'标题由Agent分析聊天库中的真实客户关注点后生成问题型钩子候选；用户多选即确认标题，再填写各主题文章数和逐篇图片数。'},
            'text_notice':'文字API配置长期保存；每次任务明确选择来源。选择API将发送有限文字上下文并可能收费，失败不自动改用宿主。图片视觉审核仍由已验证宿主能力完成。',
            'credential_notice':'API Key可由用户在当前聊天中主动提供并注明用途与模型，Agent随后自动接入安全凭据或环境变量；不得回显或写入普通配置、源码、日志和Git。'}

def obj(properties,required=None):
    return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
S={'type':'string','minLength':1}; STRINGS={'type':'array','items':S}; IDS=STRINGS
CLAIM=obj({'text':S,'fact_ids':IDS})
TOPIC=obj({'topic_id':S,'direction':S,'question_summary':S,'source_ids':IDS,'scope':{'enum':['product_specific','general']},'count_basis':{'enum':['conversation','fragment','reported_aggregate','unknown']},'verified_count':{'type':['integer','null'],'minimum':0},'supporting_fact_ids':IDS,'distinct_angles':STRINGS,'gaps':STRINGS,'status':{'enum':['ready','needs_evidence']},'priority_reason':S})
IMAGE=obj({'image_id':S,'article_id':S,'paragraph':{'type':'integer','minimum':1},'purpose':S,'scene':S,'people_actions':{'type':'string'},'show_product':{'type':'boolean'},'product_image_ids':IDS,'reference_image_ids':IDS,'borrow':STRINGS,'immutable':STRINGS,'allowed_text':{'type':'string'},'prompt':S,'fact_ids':IDS})
CHECK=obj({'check_id':S,'verdict':{'enum':['passed','failed','needs_review']},'severity':{'enum':['info','warning','hard']},'evidence':S,'suggestion':{'type':'string'}})
REVIEW=obj({'verdict':{'enum':['passed','failed','needs_review']},'reviewer':{'enum':['model','qwen','human']},'checks':{'type':'array','items':CHECK,'minItems':1},'viewed_image_ids':IDS})
SCHEMAS={
 'LEARNING_REVIEW':obj({'feedback_id':S,'reason':S,'reason_uncertain':{'type':'boolean'},'corrective_action':S,'check_method':S}),
 'PREFLIGHT':obj({'understanding':S,'source_ids':IDS,'gaps':STRINGS}),
 'ANALYZING':obj({'topics':{'type':'array','items':TOPIC,'minItems':1},'coverage_note':S}),
 'PLANNING':obj({'angle':S,'question':S,'outline':STRINGS,'fact_ids':IDS,'source_ids':IDS}),
 'WRITING':obj({'title':S,'body':S,'claims':{'type':'array','items':CLAIM}}),
 'IMAGE_PLANNING':obj({'images':{'type':'array','items':IMAGE}}),
 'TEXT_REVIEW':REVIEW,'IMAGE_REVIEW':REVIEW,'FINAL_REVIEW':REVIEW,
}
SCHEMAS['PLANNING']['properties']['geo']=PLAN_SCHEMA
SCHEMAS['WRITING']['properties']['geo']=DRAFT_SCHEMA
SCHEMAS['IMAGE_PLANNING']['properties']['images']['items']['properties'].update(role={'enum':['cover','content_summary','real_scene','product_summary']},layout={'enum':['single']})
for stage in ('FACT_REVIEW','GEO_REVIEW','CONTENT_REVIEW'):SCHEMAS[stage]=REVIEW

def validate_result(stage,result):
    try: jsonschema.validate(result,SCHEMAS[stage])
    except jsonschema.ValidationError as e: raise ValueError('模型结果结构错误：'+'.'.join(map(str,e.absolute_path))) from None
