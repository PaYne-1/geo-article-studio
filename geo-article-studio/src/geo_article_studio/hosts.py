"""Portable host-mediated contract. Declared capability is not live verification."""
PROTOCOL='geo.host.v1'
BASE_CAPABILITIES=('file_io','terminal','structured_results','human_confirmation')
HOST_STAGES=('PREFLIGHT','ANALYZING','WAITING_SELECTION','PLANNING','WRITING','TEXT_REVIEW','FACT_REVIEW','GEO_REVIEW','CONTENT_REVIEW','IMAGE_PLANNING','GENERATING_IMAGES','IMAGE_REVIEW','FINAL_REVIEW','LEARNING_REVIEW','EXPORT','COMPLETED','PAUSED')

def visual_available(settings):
    host=settings.get('host') or {}
    capabilities=host.get('capabilities') or {}
    if 'visual_review' in capabilities:
        return capabilities['visual_review'] is True
    return host.get('visual_capability') is True

def assess_host(settings,stage='PREFLIGHT',mode='automatic',has_images=False):
    if stage not in HOST_STAGES:raise ValueError('未知宿主检查阶段')
    if mode not in ('automatic','learning'):raise ValueError('未知宿主检查模式')
    host=settings.get('host') or {}
    if not isinstance(host,dict):raise ValueError('host必须为宿主配置对象')
    declared=host.get('capabilities')
    if declared is not None and not isinstance(declared,dict):raise ValueError('host.capabilities必须为对象')
    capabilities={key:None for key in (*BASE_CAPABILITIES,'visual_review')}
    for key,value in (declared or {}).items():
        if key not in capabilities or (value is not None and type(value) is not bool):raise ValueError('未知宿主能力或能力值不是true/false/null')
        capabilities[key]=value
    if 'visual_review' not in (declared or {}) and 'visual_capability' in host:
        capabilities['visual_review']=visual_available(settings)
    required=list(BASE_CAPABILITIES)
    if has_images and mode=='automatic' and stage in ('IMAGE_REVIEW','FINAL_REVIEW'):
        required.append('visual_review')
    missing=[key for key in required if capabilities[key] is not True]
    if 'visual_review' in required and capabilities['visual_review'] is True and not host.get('visual_verification_ref'):missing.append('visual_verification_ref')
    return {'protocol':PROTOCOL,'agent':host.get('agent','generic'),'model':host.get('model'),'preferred_model':host.get('preferred_model','Qwen'),
            'capabilities':capabilities,'required':required,'missing':missing,'ready':not missing,
            'verification':'declared_only' if declared is not None else 'undeclared',
            'note':'能力是当前宿主声明，不证明平台加载、工具使用或真实视觉审核已联调；旧配置允许继续但不标为兼容性验证通过。'}

def require_declared_capabilities(settings,**kwargs):
    report=assess_host(settings,**kwargs)
    if report['verification']=='declared_only' and not report['ready']:raise ValueError('宿主能力不足：'+', '.join(report['missing']))
    return report

def producer_identity(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!={'agent','model'}:raise ValueError('producer须仅包含实际agent和model标识')
    for text in value.values():
        if not isinstance(text,str) or not text.strip() or len(text)>160 or any(ord(c)<32 for c in text):raise ValueError('producer标识无效')
    return dict(value)
