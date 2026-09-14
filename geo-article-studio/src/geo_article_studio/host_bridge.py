"""Small direct-user router and strict host/model result contracts."""
import re
import jsonschema
from .config import DEFAULT_SETTINGS, _check_secrets

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

def form_for(trigger,settings,provided=None):
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
        values={**dict.fromkeys(DEFAULT_SETTINGS['libraries']),**settings.get('libraries',{}),
                'product':product,'output_root':settings.get('output_root'),'rule_import_sources':settings.get('rule_import_sources'),
                'article_length':defaults.get('article_length'),'provider':None,'base_url':None,'protocol_document':None,'model':None,
                'api_key_env':'GEO_IMAGE_API_KEY','supports_references':None,'dimensions':defaults.get('image_dimensions'),
                'image_ratio':defaults.get('image_ratio'),'image_format':defaults.get('image_format','png'),
                'image_text_policy':defaults.get('image_text_policy'),'max_attempts':settings.get('limits',{}).get('max_generation_attempts_per_image',3),
                'max_requests':settings.get('limits',{}).get('max_image_requests_per_task')}
        configured=settings.get('image_provider') or {}
        for key in ('base_url','model','api_key_env','supports_references'):
            if configured.get(key) is not None:values[key]=configured[key]
        values['provider']=configured.get('adapter')
        values['protocol_document']=settings.get('image_protocol_verification')
        for key,default in [('adapter','openai_chat_compatible'),('base_url',None),('endpoint','/chat/completions'),('model',None),('api_key_env','GEO_TEXT_API_KEY'),('protocol_document',None),('max_requests_per_task',None)]:
            values['text_'+key]=text_config.get(key,default)
        sections=[{'id':'product','title':'产品与文章','fields':['product','article_length']},
                  {'id':'libraries','title':'四库与保存位置','fields':['chat','product_info','reference_images','product_images','output_root','rule_import_sources']},
                  {'id':'image_api','title':'图片API与规格','fields':['provider','base_url','protocol_document','model','api_key_env','supports_references','dimensions','image_ratio','image_format','image_text_policy','max_attempts','max_requests']}]
        sections.append({'id':'text_api','title':'第三方文字API（可选，提前配置后长期保存）','fields':[key for key in values if key.startswith('text_')]})
        required=['product','article_length','chat','product_info','reference_images','product_images','output_root','rule_import_sources','provider','base_url','protocol_document','model','api_key_env','supports_references','dimensions','image_text_policy','max_requests']
    else:
        values={'product':product,'mode':defaults.get('mode'),'text_source':None,'chat_scope':'当前产品相关记录及标注的通用品类记录','extra_requirements':''}; required=['product','mode','text_source']
    if set(p)-set(values):raise ValueError('预填含未知表单字段')
    values.update(p)
    return {'action':action,'values':values,'missing':[k for k in required if values.get(k) in (None,'',[])],
            'sections':sections,'choices':{'mode':['learning','automatic'],'text_source':['host','api']} if action=='start' else {},
            'text_options':[{'value':'host','label':'当前Agent默认模型','available':True},{'value':'api','label':'第三方文字API','model':text_config.get('model'),'available':text_check['ok'],'missing':text_check['errors']}],
            'text_notice':'文字API配置长期保存；每次任务明确选择来源。选择API将发送有限文字上下文并可能收费，失败不自动改用宿主。图片视觉审核仍由已验证宿主能力完成。',
            'credential_notice':'图片API需要配置；密钥仅通过本地环境变量或宿主安全凭据接入，不发送到聊天。表单只保存环境变量名。'}

def obj(properties,required=None):
    return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
S={'type':'string','minLength':1}; STRINGS={'type':'array','items':S}; IDS=STRINGS
CLAIM=obj({'text':S,'fact_ids':IDS})
TOPIC=obj({'topic_id':S,'direction':S,'question_summary':S,'source_ids':IDS,'scope':{'enum':['product_specific','general']},'count_basis':{'enum':['conversation','fragment','unknown']},'verified_count':{'type':['integer','null'],'minimum':0},'supporting_fact_ids':IDS,'distinct_angles':STRINGS,'gaps':STRINGS,'status':{'enum':['ready','needs_evidence']},'priority_reason':S})
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

def validate_result(stage,result):
    try: jsonschema.validate(result,SCHEMAS[stage])
    except jsonschema.ValidationError as e: raise ValueError('模型结果结构错误：'+'.'.join(map(str,e.absolute_path))) from None
