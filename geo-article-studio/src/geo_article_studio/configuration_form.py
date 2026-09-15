"""Progressive configuration form; local checks only, no provider discovery calls."""
import copy
import json
import os
from .config import DEFAULT_SETTINGS, _check_secrets

# UI key -> settings path, default, Chinese label. Protocol details remain agent-owned.
FIELDS={
    'product':('default_product_name',DEFAULT_SETTINGS['default_product_name'],'产品名称'),
    **{key:('libraries.'+key,None,label) for key,label in [('chat','聊天库路径'),('product_info','产品信息库路径'),('reference_images','参考图库路径'),('product_images','产品图库路径')]},
    'output_root':('output_root',None,'成品保存目录'),
    'image_service':('service_labels.image',None,'图片服务商名称（可选）'),
    'base_url':('image_provider.base_url',None,'图片API地址'),
    'model':('image_provider.model',None,'图片模型'),
    'protocol_document':('image_protocol_verification',None,'接口文档链接或本地文件（有则提供）'),
    'provider':('image_provider.adapter',None,'图片适配器'),
    'supports_references':('image_provider.supports_references',None,'参考图能力'),
    'max_reference_images':('image_provider.max_reference_images',None,'参考图数量上限'),
    'output_formats':('image_provider.output_formats',None,'接口支持的格式'),
    'api_key_env':('image_provider.api_key_env','GEO_IMAGE_API_KEY','图片凭据变量名'),
    'dimensions':('defaults.image_dimensions',None,'已确认图片尺寸'),
    'image_ratio':('defaults.image_ratio',DEFAULT_SETTINGS['defaults']['image_ratio'],'已确认图片比例'),
    'image_format':('defaults.image_format','png','图片格式'),
    'image_text_policy':('defaults.image_text_policy','auto','图中文字自动策略'),
    'max_attempts':('limits.max_generation_attempts_per_image',3,'单图尝试上限（含首次）'),
    'max_requests':('limits.max_image_requests_per_task',None,'每任务图片调用上限（含重试，可稍后确认）'),
    'text_service':('service_labels.text',None,'文字服务商名称（可选）'),
    **{'text_'+key:('text_provider.'+key,default,label) for key,default,label in [
        ('adapter',None,'文字适配器'),('base_url',None,'文字API地址'),
        ('endpoint',None,'文字接口路径'),('model',None,'文字模型'),
        ('api_key_env','GEO_TEXT_API_KEY','文字凭据变量名'),
        ('protocol_document',None,'接口文档链接或本地文件（有则提供）'),
        ('max_requests_per_task',None,'每任务文字调用上限（含重试，可稍后确认）')]},
}
BASE=['product','chat','product_info','reference_images','product_images','output_root']
IMAGE=['model']
TEXT=['text_model']
AGENT=['provider','supports_references','max_reference_images','output_formats','text_adapter','text_endpoint']
VIRTUAL_LABELS={'image_api_key':'API Key','text_api_key':'API Key'}

def empty(value):
    return value is None or value==[] or (isinstance(value,str) and not value.strip())

def saved_value(settings,path):
    current=settings
    for key in path.split('.'):
        if not isinstance(current,dict) or key not in current:return None
        current=current[key]
    return current

def local_checks(settings):
    from .images import ImageProvider, ProviderError
    from .text_api import TextProvider
    def check(factory,value):
        if not value:return {'ok':False,'errors':['not_configured'],'network_verified':False}
        try:return factory(value).check()
        except (TypeError,ValueError,ProviderError):return {'ok':False,'errors':['invalid_config'],'network_verified':False}
    credentials={}
    for label,key,default in [('image_api','image_provider','GEO_IMAGE_API_KEY'),('text_api','text_provider','GEO_TEXT_API_KEY')]:
        config=settings.get(key) or {}
        name=config.get('api_key_env',default) if isinstance(config,dict) else default
        credentials[label]={'environment':name,'connected':bool(os.environ.get(name)) if isinstance(name,str) else False}
    return {'image_api':check(ImageProvider,settings.get('image_provider')),
            'text_api':check(TextProvider,settings.get('text_provider')),
            'credentials':credentials,'paid_request_sent':False,'basis':'saved_configuration'}

def configuration_form(settings,provided=None,*,config_path=None,persisted=None):
    provided={} if provided is None else provided
    if not isinstance(provided,dict):raise ValueError('预填内容必须为对象')
    _check_secrets(provided)
    if set(provided)-set(FIELDS):raise ValueError('预填含未知表单字段；文章篇幅在开始任务选择short/long')
    values={};states={}
    loaded=bool(settings) if persisted is None else persisted
    for key,(path,default,_) in FIELDS.items():
        saved=saved_value(settings,path)
        value=provided[key] if key in provided else saved if not empty(saved) else default
        values[key]=copy.deepcopy(value)
        states[key]='missing' if empty(value) else 'provided' if key in provided else 'saved' if loaded and not empty(saved) else 'default'
    image_key=not result_key_missing(settings,'image_provider','GEO_IMAGE_API_KEY')
    text_key=not result_key_missing(settings,'text_provider','GEO_TEXT_API_KEY')
    sections=[
        {'id':'product','title':'产品','fields':['product']},
        {'id':'libraries','title':'四库与保存位置（基础配置，可分次保存）','fields':BASE[1:]},
        {'id':'image_api','title':'图片API（有图任务才需完成）','fields':['model','image_api_key','max_requests']},
        {'id':'text_api','title':'第三方文字API（可选；选择第三方模型时才需完成）','fields':['text_model','text_api_key','text_max_requests_per_task']},
    ]
    result={'action':'configure_task','values':values,'field_states':states,
            'missing':[k for k in BASE if empty(values[k])],
            'conditional_missing':{'with_images':[k for k in IMAGE if empty(values[k])]+([] if image_key else ['image_api_key']),
                                   'text_api':[k for k in TEXT if empty(values[k])]+([] if text_key else ['text_api_key'])},
            'sections':sections,'agent_fields':AGENT.copy(),'choices':{},
            'persistence':{'saved_config_loaded':loaded,'config_path':config_path,'can_save_partial':True,'merge_updates':True},
            'recommendations':{'orientation':'portrait','ratio':'3:4','dimensions':'宽:高固定3:4竖版；Agent只能从接口实际支持的3:4尺寸中选择，不能改成近似比例'},
            'checks':local_checks(settings),
            'credential_notice':'可直接在聊天中提供API Key，并注明图片或文字用途及模型名称；Agent接收后在本地持久配置，不回显Key、不写入普通JSON。也可选择本地隐藏输入。聊天中发送的Key可能保留在会话记录中。',
            'technical_notice':'Agent根据模型名称查找官方文档并自动补齐地址、适配器、接口路径、参考图能力、格式和尺寸；无法唯一识别或协议不受支持时明确报告，不能猜测或发收费探测请求。',
            'text_notice':'配置跨任务保存；每次开始任务仍由用户选择当前Agent默认模型或第三方文字API。'}
    result['message']=render_configuration(result)
    return result

def result_key_missing(settings,key,default):
    config=settings.get(key) or {}
    name=config.get('api_key_env',default) if isinstance(config,dict) else default
    return not (isinstance(name,str) and os.environ.get(name))

def render_configuration(form):
    values=form['values'];states=form['field_states'];p=form['persistence']
    status={'saved':'已保存','provided':'本次填写，尚未保存','default':'默认，待保存','missing':'待补充'}
    lines=['## 配置任务','',('已加载保存的配置：'+(p['config_path'] or '当前运行配置')) if p['saved_config_loaded'] else '尚未保存配置，可分次填写并保存。',
           '已保存项直接复用；只需回复要补充或修改的内容。保存配置不代表接口已联网验证。']
    for section in form['sections']:
        lines+=['','### '+section['title'],'']
        for key in section['fields']:
            if key in VIRTUAL_LABELS:
                kind='image_api' if key=='image_api_key' else 'text_api'
                credential=form['checks']['credentials'][kind]
                lines.append('- API Key：'+('已接入当前进程（不显示值）' if credential['connected'] else '未配置；可在这里发送并注明模型，也可本地隐藏输入'))
                continue
            value=values[key]
            rendered='未填写' if empty(value) else json.dumps(value,ensure_ascii=False) if isinstance(value,(list,dict)) else str(value)
            state_label=status[states[key]]
            if empty(value) and key in ('image_service','text_service'):state_label='可选，无需补填'
            if empty(value) and key in ('protocol_document','text_protocol_document'):state_label='Agent根据服务信息查找核对'
            if empty(value) and key in ('max_requests','text_max_requests_per_task'):state_label='可选，可留空'
            lines.append('- '+FIELDS[key][2]+'：'+rendered+'（'+state_label+'）')
    specs=[]
    for key in ('dimensions','image_ratio','image_format','max_attempts'):
        if not empty(values[key]):specs.append(FIELDS[key][2]+'：'+str(values[key])+'（'+status[states[key]]+'）')
    lines+=['','所有配图宽:高固定3:4竖版；每张必须使用当前版本已批准产品图，并在成图中清楚展示产品。']
    if specs:lines.append('；'.join(specs)+'。')
    lines+=['',form['credential_notice'],form['technical_notice'],
            '图片中的少量文字由Agent根据文章标题和正文决定；所有图片必须使用已批准产品图并展示当前产品。',
            '图片和文字任务调用上限均可留空；确定任务规模后再估算和确认。零图任务不要求图片API齐备；用当前Agent默认模型无需第三方文字API。篇幅在“开始任务”中选择短篇600–800字或普通长文至少1000字。',
            '本表只做本地检查，不发送API请求，不产生调用费用。']
    if p['saved_config_loaded']:
        lines+=['','本地检查：']
        for key,label in [('image_api','图片API'),('text_api','文字API')]:
            check=form['checks'][key]
            lines.append('- '+label+'：'+('本地配置检查通过，尚未联网验证' if check['ok'] else '尚未通过本地配置检查；仅在使用该服务前补齐或修正'))
            credential=form['checks']['credentials'][key]
            lines.append('  凭据变量'+str(credential['environment'])+'：'+('已接入当前进程' if credential['connected'] else '未接入当前进程')+'（仅报告状态，不显示值）。')
    return '\n'.join(lines)
