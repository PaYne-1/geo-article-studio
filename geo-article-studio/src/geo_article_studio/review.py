"""Deterministic gates complement, never substitute for, semantic/visual review."""
import re
import unicodedata

def normalized(text):
    return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',text)).lower()

def check_text(article,facts,rules):
    issues=[]; title=article.get('title',''); body=article.get('body',''); text=title+'\n'+body
    if not title.strip() or '\n' in title or not body.strip(): issues.append('标题/正文为空或标题不止一行')
    if re.search(r'\[待补充\]|TODO|待确认参数|候选标题|生图提示词',text): issues.append('成稿含占位或过程内容')
    if re.search(r'(?<!\d)1[3-9]\d{9}(?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text): issues.append('成稿可能含个人联系方式')
    for r in rules:
        if r.get('type')=='hard_ban':
            for term in r.get('terms',[]):
                if normalized(term) and normalized(term) in normalized(text): issues.append('硬性禁用命中：'+r.get('rule_id','未编号'))
    factmap={f['fact_id']:f for f in facts if f.get('status')=='approved'}
    def fact_text(fact):
        return '\n'.join(str(fact.get(key,'')) for key in ('text','claim','value','quote'))
    def numbers(value):
        return set(re.findall(r'\d+(?:\.\d+)?(?:%)?',unicodedata.normalize('NFKC',value)))
    claims=article.get('claims',[])
    for c in claims:
        if not c.get('text') or c['text'] not in text or not c.get('fact_ids') or any(x not in factmap for x in c.get('fact_ids',[])):
            issues.append('主张缺少有效批准事实映射')
    for match in re.finditer(r'\d+(?:\.\d+)?(?:%|％)?',text):
        value=match.group()
        token=unicodedata.normalize('NFKC',value)
        if not any(token in numbers(c.get('text','')) and any(token in numbers(fact_text(factmap.get(fid,{}))) for fid in c.get('fact_ids',[])) for c in claims):
            issues.append('数字没有来源映射：'+value)
    return issues

REVIEW_CHECKS={
    'FACT_REVIEW':['claims','parameters','sources','data_policy_medical_safety','real_cases'],
    'GEO_REVIEW':['title_intent','direct_answer','subquestion_coverage','heading_extractability','conclusion','length_structure'],
    'CONTENT_REVIEW':['semantic_rules','privacy','distinctness','natural_language','paragraph_method','brand_natural','readability','spelling','copyright'],
    'TEXT_REVIEW':['claims','semantic_rules','privacy','distinctness','title_body'],
    'IMAGE_REVIEW':['visible_text','product_structure','people_actions','visual_rules','body_alignment'],
    'FINAL_REVIEW':['claims','semantic_rules','privacy','title_body','files','image_alignment'],
}

def validate_review(stage,result,*,visual_capable=False,has_images=False,mode='automatic'):
    checks={x['check_id']:x for x in result['checks']}
    if not set(REVIEW_CHECKS[stage]).issubset(checks): raise ValueError('独立审核缺少必需检查项')
    if any(not c.get('evidence') for c in result['checks']): raise ValueError('审核必须记录简短证据/位置')
    if stage=='IMAGE_REVIEW' or (stage=='FINAL_REVIEW' and has_images):
        if result.get('reviewer')=='human':
            if mode!='learning': raise ValueError('自动模式需要实际视觉能力')
        elif not visual_capable: raise ValueError('没有实际视觉能力，不能标记AI视觉审核通过')
        if not result.get('viewed_image_ids'): raise ValueError('必须实际查看图片并提交对应ID')
    return result['verdict']=='passed' and all(c['verdict']=='passed' for c in result['checks'])
