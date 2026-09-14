"""Small direct-user router and strict host/model result contracts."""
import re
import jsonschema

TRIGGERS={'配置资料库':'configure_libraries','配置API':'configure_api','开始任务':'start','开始学习任务':'start_learning','开始自动任务':'start_automatic','确认':'approve','确认下一步':'approve','暂停任务':'pause','查看规则':'rules','更新规则':'update_rules'}

def route(text,origin='user'):
    if origin!='user': return None
    value=text.strip()
    value=re.sub(r'^[/$]geo-article-studio\s*|^GEO\s*','',value)
    if value.startswith(('修改：','修改:')): return 'revise'
    if value.startswith('继续任务'): return 'resume'
    for key in sorted(TRIGGERS,key=len,reverse=True):
        if value==key or value.startswith(key+'\n') or value.startswith(key+' '): return TRIGGERS[key]
    return None

def form_for(trigger,settings,provided=None):
    action=route(trigger); p=provided or {}; defaults=settings.get('defaults',{})
    if action=='configure_libraries':
        values={**settings.get('libraries',{}),'output_root':settings.get('output_root'),'rule_import_sources':settings.get('rule_import_sources')}; required=['chat','product_info','reference_images','product_images','output_root','rule_import_sources']
    elif action=='configure_api':
        values={'provider':None,'base_url':None,'protocol_document':None,'model':None,'api_key_env':'GEO_IMAGE_API_KEY','dimensions':defaults.get('image_dimensions'),'image_format':defaults.get('image_format','png'),'image_text_policy':defaults.get('image_text_policy'),'max_attempts':3,'max_requests':settings.get('limits',{}).get('max_image_requests_per_task')}; required=['provider','base_url','protocol_document','model','dimensions','image_text_policy','max_requests']
        configured=settings.get('image_provider') or {}
        for key in ('base_url','model','api_key_env'):
            if configured.get(key) is not None:values[key]=configured[key]
        values['provider']=configured.get('adapter')
        values['protocol_document']=settings.get('image_protocol_verification')
        values['max_attempts']=settings.get('limits',{}).get('max_generation_attempts_per_image',3)
    else:
        values={'product':settings.get('default_product_name','218切面侠'),'mode':'learning' if action=='start_learning' else 'automatic' if action=='start_automatic' else defaults.get('mode'),'chat_scope':'当前产品相关记录及标注的通用品类记录','extra_requirements':''}; required=['product','mode']
    values.update(p)
    return {'action':action,'values':values,'missing':[k for k in required if values.get(k) in (None,'',[])]}

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
