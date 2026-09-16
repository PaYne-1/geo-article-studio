"""Versioned built-in GEO editorial standards. No production disable switch."""
import copy
import re
import jsonschema

VERSION='geo-editorial.v2'
IMAGE_POLICY_VERSION='multi-reference.v1'
IMAGE_TEXT_POLICY_VERSION='auto-text.v1'
REQUIRED_IMAGE_RATIO='3:4'
REQUIRED_IMAGE_DIMENSION_RATIO=(3,4)
REVIEW_STAGES=('FACT_REVIEW','GEO_REVIEW','CONTENT_REVIEW')
GOALS=['品牌曝光','型号种草','用户转化','AI引用']
PLATFORMS=['知乎','头条','搜狐','百家号','企鹅号','网易']
TARGET_AIS=['DeepSeek','豆包','文心一言','元宝']
STANDARDS={
    'version':VERSION,'title':'先分析聊天库真实客户关注点并生成问题型钩子候选；人工多选即确认核心搜索意图，平台变体须独立语义审核',
    'core_answer':'写作前确定1-3句明确核心答案，含判断标准；全文围绕它展开',
    'opening':'100-200字，先给结论再讲背景，直接回答标题',
    'structure':'核心答案→3-5个核心子问题→真实场景/案例→品牌产品案例→2-4个FAQ→总结建议',
    'paragraph':'结论→原因→事实/案例→用户建议；段落分开，每个小标题只解决一个问题',
    'length':{'short':[600,800],'long_min':1000,'count_basis':'去除空白后的字符数（含标点及小标题），不得重复凑字数'},
    'evidence':'论点有可核实事实、参数、数据或真实经验支撑；参数对应体验，不虚构数据、客户评价或案例',
    'brand':'用户问题→使用需求→对应功能→产品案例；品牌作为解决问题的案例，避免硬广、夸大和高频重复',
    'language':'减少模板开场、AI套话和机械重复关键词；禁止为凑字数重复表达',
    'images':{'recommended_count':[2,4],'four_roles':['cover','content_summary','real_scene','product_summary'],'layout':'每张独立成图，禁止拼图、套图、长条切图','ratio':'宽:高固定3:4竖版','preference':'3:4竖版，现代、真实、自然、生活化、简洁；每张均展示产品并对应正文；自动文字策略下每篇至少一张图加入直接摘自标题或正文的短文案，优先封面或内容总结图，每张最多16个非空白字符和两行','wheelchair':'每张使用当前版本已批准产品图锁定外观；提示词写明产品图文件名、保持产品不变、符合场景透视及光影融合；匹配主光、色温、环境光和接触阴影，不得简单贴图；产品清楚可见，Logo、型号及参数与批准资料和正文一致'},
    'reviews':['事实：品牌型号、重量尺寸续航刹车、数据政策及医疗/安全表述来源','GEO：直接回答标题、完整子问题、清晰小标题、便于AI提取、明确总结建议','内容合规：AI套话、重复、广告感、错字、夸大、违规词、版权及图文一致性'],
}

S={'type':'string','minLength':1}
def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def strings(minimum=1,maximum=None):
    out={'type':'array','items':S,'minItems':minimum,'uniqueItems':True}
    if maximum is not None:out['maxItems']=maximum
    return out
BRIEF_SCHEMA=obj({'original_title':S,'goals':{'type':'array','items':{'enum':GOALS},'minItems':1,'uniqueItems':True},'platforms':strings(),'target_ais':strings(),'article_type':{'enum':['short','long']}})
KINDS=['answer','subquestion','scenario','product_case','faq','summary']
PLAN_SCHEMA=obj({'core_answer':S,'subquestions':strings(3,5),'audience':S,'scenario':S,'sections':{'type':'array','items':obj({'kind':{'enum':KINDS},'heading':S})},'scenario_evidence':obj({'source_ids':strings()}),'product_evidence':obj({'fact_ids':strings()})})
DRAFT_SCHEMA=obj({'opening':S,'sections':{'type':'array','items':obj({'kind':{'enum':KINDS},'heading':S,'text':S})},'faqs':{'type':'array','minItems':2,'maxItems':4,'items':obj({'question':S,'answer':S})}})

def _validate(value,schema):
    try:jsonschema.validate(value,schema)
    except jsonschema.ValidationError:raise ValueError('GEO标准字段缺失或格式不正确') from None

def char_count(text):return len(re.sub(r'\s','',text))
def question_title(title):return isinstance(title,str) and title.strip().endswith(('？','?')) and '\n' not in title

def validate_brief(brief):
    _validate(brief,BRIEF_SCHEMA)
    if not question_title(brief['original_title']):raise ValueError('请确认问题型原始GEO标题，不能悄悄更改核心问题')
    return copy.deepcopy(brief)

def expected_kinds(count):return ['answer']+['subquestion']*count+['scenario','product_case','faq','summary']

def validate_plan(result,brief):
    validate_brief(brief);geo=result.get('geo');_validate(geo,PLAN_SCHEMA)
    if result['question']!=brief['original_title']:raise ValueError('策划核心问题必须保留已确认原GEO标题')
    sentences=[s for s in re.split(r'[。！？!?]+',geo['core_answer']) if s.strip()]
    if not 1<=len(sentences)<=3 or char_count(geo['core_answer'])>200:raise ValueError('核心答案须为1-3句话且可放入开头')
    sections=geo['sections'];questions=geo['subquestions']
    if [s['kind'] for s in sections]!=expected_kinds(len(questions)):raise ValueError('大纲必须依次覆盖答案、子问题、真实场景、产品案例、FAQ和建议')
    if [s['heading'] for s in sections if s['kind']=='subquestion']!=questions:raise ValueError('每个核心子问题须对应独立小标题')
    if len({s['heading'] for s in sections})!=len(sections):raise ValueError('小标题不能重复')
    if result['outline']!=[s['heading'] for s in sections]:raise ValueError('大纲须与结构化章节一致')

def render_body(geo):
    return geo['opening']+'\n\n'+'\n\n'.join(s['heading']+'\n'+s['text'] for s in geo['sections'])

def validate_draft(result,plan,brief):
    validate_plan(plan,brief);geo=result.get('geo');_validate(geo,DRAFT_SCHEMA)
    if not question_title(result['title']):raise ValueError('成稿标题必须为问题型标题；语义审核另核对核心意图')
    if not 100<=char_count(geo['opening'])<=200:raise ValueError('开头必须为100-200字')
    if not geo['opening'].startswith(plan['geo']['core_answer']):raise ValueError('开头必须先给出已确定核心答案')
    if [{'kind':s['kind'],'heading':s['heading']} for s in geo['sections']]!=plan['geo']['sections'][1:]:raise ValueError('正文结构必须对应已确定大纲')
    faq=next(s for s in geo['sections'] if s['kind']=='faq')
    expected='\n\n'.join(x['question']+'\n'+x['answer'] for x in geo['faqs'])
    if faq['text']!=expected or len({f['question'] for f in geo['faqs']})!=len(geo['faqs']):raise ValueError('FAQ必须实际呈现在正文中且不重复')
    if result['body']!=render_body(geo):raise ValueError('正文必须与结构化段落一致，不能仅声明满足结构')
    length=char_count(result['body'])
    if brief['article_type']=='short' and not 600<=length<=800:raise ValueError('短篇须600-800字')
    if brief['article_type']=='long' and length<1000:raise ValueError('普通长文须至少1000字')
    paragraphs=[p.strip() for p in result['body'].split('\n\n') if char_count(p)>20]
    if len(set(paragraphs))!=len(paragraphs):raise ValueError('禁止重复段落凑字数')

def validate_images(result,count,*,require_product=True):
    images=result['images']
    if len(images)!=count or any(p.get('layout')!='single' for p in images):raise ValueError('每张图片必须独立成图，禁止拼图或长条切图')
    if require_product and any(not p.get('show_product') or not p.get('product_image_ids') for p in images):raise ValueError('每张图片必须展示产品并引用当前版本产品图')
    roles=[p.get('role') for p in images]
    if any(r not in STANDARDS['images']['four_roles'] for r in roles):raise ValueError('配图须明确正文用途')
    if count==4 and roles!=STANDARDS['images']['four_roles']:raise ValueError('四图结构须为封面、内容总结、真实场景、产品或总结')

def validate_image_text_plan(images,policy,title,body):
    texts=[p.get('allowed_text','').strip() for p in images]
    if policy=='none':
        if any(texts):raise ValueError('当前图中文字策略禁止文字')
        return
    if policy=='auto' and images and not any(texts):
        raise ValueError('自动图中文字策略下，每篇至少一张图片应加入少量正文相关文字')
    for plan,text in zip(images,texts):
        if not text:continue
        if len(re.sub(r'\s','',text))>16 or len(text.splitlines())>2:
            raise ValueError('图片文字最多16个字符、两行')
        prompt=plan.get('prompt','')
        canonical=f'只显示文字“{text}”，不要添加其他文字'
        quoted=re.findall(r'[“「『]([^”」』]+)[”」』]',prompt)+re.findall(r'"([^"]+)"',prompt)
        remainder=prompt.replace(canonical,'')
        text_commands=('文字','文案','字体','标语','字幕','显示','添加','增加','写入','写上','印上','配字','加字','呈现','二维码','扫码')
        if any(value!=text for value in quoted) or any(term in remainder for term in text_commands):
            raise ValueError('图片提示词要求了allowed_text以外的额外文字')
        if prompt.count(canonical)!=1:
            raise ValueError('图片提示词必须逐字包含allowed_text并要求只显示该文字')
        normalized=re.sub(r'\s','',text)
        if normalized not in re.sub(r'\s','',title) and normalized not in re.sub(r'\s','',body):
            raise ValueError('图片文字必须直接摘自文章标题或正文')

def render_image_prompt(plan,product_label,reference_label):
    borrow='、'.join(plan.get('borrow',[]))
    immutable='、'.join(plan.get('immutable',[])) or '产品外观、结构、颜色、部件和Logo'
    parts=[f'场景：{plan.get("scene","").strip()}。']
    if plan.get('people_actions','').strip():parts.append(f'人物动作：{plan["people_actions"].strip()}。')
    parts.extend([f'产品图{product_label}只确定产品身份，保持产品不变，不得改变{immutable}。',
                  f'参考图{reference_label}只借鉴{borrow}。',
                  f'产品符合场景透视：{plan.get("perspective_strategy","").strip()}。',
                  f'产品与场景光影融合：{plan.get("lighting_strategy","").strip()}。'])
    text=plan.get('allowed_text','').strip()
    parts.append(f'只显示文字“{text}”，不要添加其他文字。' if text else '画面不得出现任何可读文字、标语或二维码。')
    return ''.join(parts)

def validate_image_prompt(prompt,product_label,reference_label,borrow,perspective_strategy,lighting_strategy):
    if not all(isinstance(x,str) and x.strip() for x in (prompt,product_label,reference_label,perspective_strategy,lighting_strategy)):
        raise ValueError('配图提示词须写明产品图、参考图、场景透视和光影融合策略')
    factors=('构图','机位','人物与产品尺度','自然光线','空间层次','生活化风格')
    if not isinstance(borrow,list) or not borrow or any(x not in factors for x in borrow) or len(set(borrow))!=len(borrow):
        raise ValueError('参考图借鉴范围必须使用非空标准因素列表')
    if product_label not in prompt:raise ValueError('配图提示词必须写明实际采用的产品图文件名')
    if reference_label not in prompt:raise ValueError('配图提示词必须写明实际采用的参考图文件名')
    if '产品图' not in prompt or '只确定产品身份' not in prompt or '参考图' not in prompt or '只借鉴' not in prompt:
        raise ValueError('配图提示词必须区分产品图与参考图的用途边界')
    match=re.search(re.escape(reference_label)+r'([^；。\n]*)',prompt)
    clause=match.group(1) if match else ''
    aliases={'构图':'构图','机位':'机位','尺度':'人物与产品尺度','光线':'自然光线','空间层次':'空间层次','生活化风格':'生活化风格'}
    if any(factor not in clause for factor in borrow) or any(token in clause and factor not in borrow for token,factor in aliases.items()):
        raise ValueError('提示词中的参考图借鉴范围必须与borrow及授权完全一致')
    if '产品不变' not in prompt:raise ValueError('配图提示词必须明确保持产品不变')
    if '透视' not in prompt:raise ValueError('配图提示词必须明确产品符合场景透视')
    if '光影' not in prompt or '融合' not in prompt:raise ValueError('配图提示词必须明确产品与场景光影融合')
    perspective_terms=('统一消失点','相机高度','真实尺度','地面接触','遮挡')
    if any(term not in perspective_strategy for term in perspective_terms):
        raise ValueError('透视策略须包含统一消失点、相机高度、真实尺度、地面接触和遮挡关系')
    lighting_terms=('主光','色温','环境反光','接触阴影','投影','边缘色溢','景深','颗粒')
    if any(term not in lighting_strategy for term in lighting_terms):
        raise ValueError('光影策略须包含主光、色温、环境反光、接触阴影、投影、边缘色溢、景深和颗粒')

def validate_image_spec(ratio,dimensions):
    if ratio!=REQUIRED_IMAGE_RATIO:raise ValueError('所有配图比例必须为宽:高3:4竖版')
    if not isinstance(dimensions,list) or len(dimensions)!=2 or any(type(n) is not int or n<1 for n in dimensions):
        raise ValueError('image_dimensions必须是两个正整数')
    width,height=dimensions;rw,rh=REQUIRED_IMAGE_DIMENSION_RATIO
    if width*rh!=height*rw:raise ValueError('图片像素尺寸必须符合宽:高3:4')

def action_schema(base,stage,enabled):
    schema=copy.deepcopy(base)
    if not schema or not enabled:return schema
    if stage in ('PLANNING','WRITING'):schema['required']=list(dict.fromkeys(schema['required']+['geo']))
    if stage=='IMAGE_PLANNING':schema['properties']['images']['items']['required']+=['role','layout']
    return schema
