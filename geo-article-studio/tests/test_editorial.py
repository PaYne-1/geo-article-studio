import copy
import pytest
from test_text_api import text_server
from test_images import server

def brief():
    return {'original_title':'出行前如何核对电动轮椅？','goals':['AI引用'],'platforms':['知乎'],'target_ais':['DeepSeek'],'article_type':'short'}

def plan():
    questions=['如何核对尺寸？','怎样了解使用条件？','出行前检查什么？']
    sections=[{'kind':'answer','heading':'先给结论'},*[{'kind':'subquestion','heading':q} for q in questions],{'kind':'scenario','heading':'出行前如何做准备？'},{'kind':'product_case','heading':'产品资料如何帮助判断？'},{'kind':'faq','heading':'还有哪些常见疑问？'},{'kind':'summary','heading':'最终怎样决定？'}]
    return {'angle':'核对准备','question':brief()['original_title'],'outline':[s['heading'] for s in sections],'fact_ids':['F1'],'source_ids':['S1'],
            'geo':{'core_answer':'应先核对产品资料和实际使用条件，再决定是否适合本次出行。','subquestions':questions,'audience':'准备出行的使用者','scenario':'出发前核对资料','sections':sections,'scenario_evidence':{'source_ids':['S1']},'product_evidence':{'fact_ids':['F1']}}}

def draft():
    from geo_article_studio.editorial import render_body
    p=plan();opening=p['geo']['core_answer']+'判断时需要把计划路线、现场空间以及能够核实的产品信息放在一起看。资料没有写明的内容，应向提供方确认后再判断。这样可以把已经知道的条件与尚未解决的问题分开，减少凭印象做决定的情况，也便于出发前逐项检查。'
    texts=[
        '尺寸应以实际资料和现场测量为依据。因为通行空间既受车辆尺寸影响，也与入口和转弯位置有关。核对时可以分别记录设备资料与现场情况，不把目测当作精确测量。对不能确认的位置，建议先向场地管理方询问，再考虑路线。',
        '使用条件需要结合计划路线理解。相同产品在不同环境下的使用要求可能不同，不能根据外观就作出结论。应查阅对应版本的说明资料，区分资料明确支持的情况与仍需核实的情况，再根据实际目的地安排准备事项。',
        '出发前应把需要确认的问题写成清单。提前整理能让沟通更具体，也能减少临时寻找资料的时间。清单可包含路线、场地、资料版本及未解决的问题。建议逐项核对并保留来源，对仍然不清楚的内容先确认，不急于作判断。',
        '本测试资料记录了一次出发前核对资料的讨论。讨论说明使用者关心准备工作，但并不能证明某项性能已经达到要求。这样的场景适合用来整理咨询问题，不能直接写成满意评价。读者可以借鉴核对顺序，并按自己的条件补充问题。',
        '虚构测试产品提供资料核对示例。这里把产品资料作为回答问题的案例，用来说明如何寻找和确认信息，不据此推断未记载的功能。读者应先看资料能否回答自己的需求；仍有空白时应继续询问，不把品牌名称本身当作选择依据。',
        '',
        '建议先确认需求，再核对资料与现场条件。明确信息可列入清单，尚未证实的内容应继续询问。用可核实的条件作判断，比只看名称或外观更有帮助。']
    faqs=[{'question':'资料缺项怎么办？','answer':'列出缺项并向提供方核实。'},{'question':'能凭图片判断性能吗？','answer':'不能，图片不能替代可靠的性能依据。'}]
    sections=[dict(s,text=text) for s,text in zip(p['geo']['sections'][1:],texts)]
    sections[-2]['text']='\n\n'.join(x['question']+'\n'+x['answer'] for x in faqs)
    geo={'opening':opening,'sections':sections,'faqs':faqs}
    return {'title':brief()['original_title'],'body':render_body(geo),'claims':[{'text':'虚构测试产品提供资料核对示例。','fact_ids':['F1']}],'geo':geo}

def test_brief_and_plan_require_human_title_and_supported_cases():
    from geo_article_studio.editorial import validate_brief, validate_plan
    validate_brief(brief());validate_plan(plan(),brief())
    for key in ('original_title','goals','platforms','target_ais','article_type'):
        invalid=brief();invalid.pop(key)
        with pytest.raises(ValueError):validate_brief(invalid)
    invalid=plan();invalid['geo']['subquestions']=['一个问题？']
    with pytest.raises(ValueError):validate_plan(invalid,brief())
    invalid=plan();invalid['geo']['product_evidence']['fact_ids']=[]
    with pytest.raises(ValueError):validate_plan(invalid,brief())

def test_draft_structure_length_and_core_answer_are_enforced():
    from geo_article_studio.editorial import validate_draft, char_count
    article=draft()
    assert 600<=char_count(article['body'])<=800
    validate_draft(article,plan(),brief())
    for change in ('title','body','opening','faqs'):
        invalid=copy.deepcopy(article)
        if change=='title':invalid['title']='产品推荐'
        elif change=='body':invalid['body']='简短正文'
        elif change=='opening':invalid['geo']['opening']='缺少结论'
        else:invalid['geo']['faqs']=invalid['geo']['faqs'][:1]
        with pytest.raises(ValueError):validate_draft(invalid,plan(),brief())

def test_long_article_minimum_and_duplicate_paragraphs():
    from geo_article_studio.editorial import validate_draft
    b=brief();b['article_type']='long'
    with pytest.raises(ValueError):validate_draft(draft(),plan(),b)

def test_four_images_require_independent_ordered_roles():
    from geo_article_studio.editorial import validate_images
    roles=['cover','content_summary','real_scene','product_summary']
    value={'images':[{'role':role,'layout':'single'} for role in roles]}
    validate_images(value,4)
    value['images'][1]['layout']='collage'
    with pytest.raises(ValueError):validate_images(value,4)

@pytest.fixture
def current_engine(tmp_path):
    """New production Engine, actual file/rule persistence and explicit fictional evidence."""
    import hashlib,json
    from test_engine import Index,Products
    from geo_article_studio.workflow import Engine
    from geo_article_studio.learning import RuleStore
    index=Index(tmp_path)
    text='客户讨论出发前如何核对资料。虚构测试产品提供资料核对示例。'
    from pathlib import Path
    Path(index.row['path']).write_text(text,encoding='utf-8');index.row.update(snippet=text,hash=hashlib.sha256(text.encode()).hexdigest())
    class EvidenceProducts(Products):
        def facts(self,pid,approved_only=True):return [{'fact_id':'F1','status':'approved','text':'虚构测试产品提供资料核对示例。','source_ids':['S1']}]
    settings={'workspace_root':str(tmp_path/'work'),'output_root':str(tmp_path/'out'),'defaults':{'article_length':{'min':1,'max':50}},'limits':{'max_text_revision_attempts':3},'host':{'visual_capability':False}}
    rules=tmp_path/'rules.json';rules.write_text(json.dumps({'formal':True,'version':'test','rules':[{'rule_id':'R1','scope':'global','target_id':None,'type':'hard_ban','content':'不虚构','terms':['测试禁用词'],'check_method':'语义','severity':'hard'}]}),encoding='utf-8')
    RuleStore(tmp_path/'work').import_file(rules,user_ref='test:user:rules')
    return Engine(settings,index=index,products=EvidenceProducts())

def prepare(e,mode='automatic',configured_brief=True):
    from test_engine import submit
    tid=e.start('test-product',mode,text_source='host',user_ref='test:user:start',geo_brief=brief() if configured_brief else None)['task_id']
    submit(e,tid,{'understanding':'虚构GEO标准流程测试','source_ids':['S1'],'gaps':[]})
    if mode=='learning':
        a=e.next_action(tid);e.approve(tid,a['action_id'],a['expected_revision'],user_ref='test:user:preflight')
    submit(e,tid,{'topics':[{'topic_id':'T1','direction':'资料核对','question_summary':brief()['original_title'],'source_ids':['S1'],'scope':'product_specific','count_basis':'conversation','verified_count':1,'supporting_fact_ids':['F1'],'distinct_angles':['核对准备'],'gaps':[],'status':'ready','priority_reason':'虚构客户问题'}],'coverage_note':'单个虚构会话'})
    return tid

def test_start_form_generates_titles_from_chat_and_selection_binds_confirmed_title(current_engine):
    from geo_article_studio.host_bridge import form_for
    assert 'article_length' not in form_for('配置任务',{})['missing']
    form=form_for('开始任务',{})
    assert 'original_geo_title' not in form['values']
    assert 'original_geo_title' not in form['missing']
    assert set(('goals','platforms','target_ais','article_type'))<=set(form['missing'])
    assert form['title_generation']['source']=='chat_analysis'
    assert form['title_generation']['confirmation']=='topic_multi_select'
    e=current_engine;tid=prepare(e,configured_brief=False)
    row={'topic_id':'T1','article_count':1,'image_counts':[0]}
    with pytest.raises(ValueError):e.select(tid,[row],user_ref='test:user:select')
    row['brief']={k:v for k,v in brief().items() if k!='original_title'}
    e.select(tid,[row],user_ref='test:user:confirmed-brief')
    action=e.next_action(tid)
    assert 'geo' in action['result_schema']['required']
    assert action['context']['geo_brief']==brief()
    assert action['context']['editorial_standards']['length']['short']==[600,800]

def test_selected_chat_title_must_be_question_and_cannot_be_replaced(current_engine):
    from test_engine import submit
    e=current_engine
    tid=e.start('test-product','automatic',text_source='host',user_ref='test:user:start')['task_id']
    submit(e,tid,{'understanding':'虚构GEO标准流程测试','source_ids':['S1'],'gaps':[]})
    invalid={'topics':[{'topic_id':'T1','direction':'资料核对','question_summary':'出行资料核对','source_ids':['S1'],'scope':'product_specific','count_basis':'conversation','verified_count':1,'supporting_fact_ids':['F1'],'distinct_angles':['核对准备'],'gaps':[],'status':'ready','priority_reason':'虚构客户问题'}],'coverage_note':'单个虚构会话'}
    with pytest.raises(ValueError,match='问题型钩子标题'):submit(e,tid,invalid)

    tid=prepare(e,configured_brief=False)
    supplied=brief();supplied['original_title']='另一个未经选中的问题？'
    row={'topic_id':'T1','article_count':1,'image_counts':[0],'brief':supplied}
    with pytest.raises(ValueError,match='候选标题'):e.select(tid,[row],user_ref='test:user:select')

def test_explicit_user_confirmed_title_survives_topic_refresh(current_engine):
    e=current_engine;tid=prepare(e,configured_brief=False)
    chosen='电动轮椅一次充电实际能跑多远，电池容量和续航怎么选？'
    supplied=brief();supplied['original_title']=chosen
    row={'topic_id':'T1','article_count':1,'image_counts':[0],
         'brief':supplied,'user_confirmed_title':chosen}
    e.select(tid,[row],user_ref='chat:user:selected-T01')
    action=e.next_action(tid)
    assert action['context']['geo_brief']['original_title']==chosen
    task=e.status(tid)
    assert task['articles'][0]['geo_brief_title_source']=='explicit_user_selection'
    assert task['articles'][0]['geo_brief_user_ref']=='chat:user:selected-T01'

def test_article_actions_only_send_selected_topic_and_fact_sources():
    from geo_article_studio.workflow import action_source_ids
    task={
        'sources':{
            'S_SELECTED':{'source_id':'S_SELECTED','library_type':'chat'},
            'S_OTHER':{'source_id':'S_OTHER','library_type':'chat'},
            'S_FACT':{'source_id':'S_FACT','library_type':'product_info'},
            'S_IMAGE':{'source_id':'S_IMAGE','library_type':'reference_images'},
        },
        'topics':[{'topic_id':'T1','source_ids':['S_SELECTED']},{'topic_id':'T2','source_ids':['S_OTHER']}],
        'facts':[{'fact_id':'F1','source_ids':['S_FACT']}],
    }
    article={'topic_id':'T1'}
    assert action_source_ids(task,article,'PLANNING')=={'S_SELECTED','S_FACT'}
    assert action_source_ids(task,article,'IMAGE_PLANNING')=={'S_SELECTED','S_FACT','S_IMAGE'}
    assert action_source_ids(task,None,'ANALYZING')==set(task['sources'])

def test_generation_prompts_apply_rules_before_output():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'prompts'
    writing=(root/'write_article.md').read_text(encoding='utf-8')
    images=(root/'plan_images.md').read_text(encoding='utf-8')
    assert '提交前' in writing and '650-750' in writing
    assert '生成请求发出前' in images and '逐张' in images

def test_reported_customer_aggregate_count_is_checked(current_engine):
    from test_engine import submit
    e=current_engine
    e.index.row['metadata'].update(evidence_type='customer_aggregate',reported_count=7)
    tid=e.start('test-product','automatic',text_source='host',user_ref='test:user:start')['task_id']
    submit(e,tid,{'understanding':'虚构汇总证据测试','source_ids':['S1'],'gaps':[]})
    topic={'topic_id':'T1','direction':'资料核对','question_summary':brief()['original_title'],'source_ids':['S1'],'scope':'product_specific','count_basis':'reported_aggregate','verified_count':6,'supporting_fact_ids':['F1'],'distinct_angles':['核对准备'],'gaps':[],'status':'ready','priority_reason':'日报汇总'}
    with pytest.raises(ValueError,match='汇总次数'):submit(e,tid,{'topics':[topic],'coverage_note':'汇总测试'})
    topic['verified_count']=7
    submit(e,tid,{'topics':[topic],'coverage_note':'汇总测试'})
    assert e.status(tid)['state']=='WAITING_SELECTION'

def test_new_automatic_flow_requires_three_ordered_reviews_and_exports(current_engine):
    from test_engine import submit,good_review
    from pathlib import Path
    e=current_engine;tid=prepare(e)
    e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='test:user:select')
    submit(e,tid,plan());submit(e,tid,draft())
    for stage in ('FACT_REVIEW','GEO_REVIEW','CONTENT_REVIEW'):
        a=e.next_action(tid);assert a['stage']==stage
        with pytest.raises(ValueError):e.export(tid)
        submit(e,tid,good_review(stage))
    assert e.next_action(tid)['stage']=='FINAL_REVIEW'
    submit(e,tid,good_review('FINAL_REVIEW'))
    output=Path(e.export(tid));assert output.is_dir()
    assert next(output.rglob('正文.txt')).read_text(encoding='utf-8')==draft()['body']
    assert len(list(output.rglob('*.txt')))==2

def test_review_failure_cannot_skip_geo_round(current_engine):
    from test_engine import submit,good_review
    e=current_engine;tid=prepare(e)
    e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='test:user:select')
    submit(e,tid,plan());submit(e,tid,draft());submit(e,tid,good_review('FACT_REVIEW'))
    with pytest.raises(ValueError):submit(e,tid,good_review('CONTENT_REVIEW'))
    review=good_review('GEO_REVIEW');review['checks'][0]['verdict']='failed';review['verdict']='failed'
    submit(e,tid,review);assert e.next_action(tid)['stage']=='PLANNING'

def test_learning_confirms_core_answer_and_replans_after_feedback(current_engine):
    from test_engine import submit
    e=current_engine;tid=prepare(e,'learning')
    e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='test:user:select')
    submit(e,tid,plan());a=e.next_action(tid)
    assert a['kind']=='NEEDS_USER' and a['stage']=='PLANNING'
    e.approve(tid,a['action_id'],a['expected_revision'],user_ref='test:user:core-answer')
    submit(e,tid,draft());a=e.next_action(tid)
    e.revise(tid,a['action_id'],a['expected_revision'],'核心答案更明确',user_ref='test:user:feedback')
    assert e.next_action(tid)['stage']=='PLANNING'
    assert 'WRITING' not in e.status(tid)['articles'][0]['results']

def test_body_feedback_waits_for_rewritten_content_review_before_reflection(current_engine):
    from test_engine import submit,good_review,reflect
    e=current_engine;tid=prepare(e,'learning')
    e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='test:user:select')
    def approve():
        action=e.next_action(tid)
        return e.approve(tid,action['action_id'],action['expected_revision'],user_ref='test:user:approve')
    submit(e,tid,plan());approve();submit(e,tid,draft())
    action=e.next_action(tid)
    e.revise(tid,action['action_id'],action['expected_revision'],'请把正文的目测说明写得更具体',user_ref='test:user:feedback')
    submit(e,tid,plan())
    assert e.next_action(tid)['stage']=='PLANNING'
    approve()
    assert e.status(tid)['feedback'][-1]['status']=='pending_revision'
    submit(e,tid,draft())
    for stage in ('FACT_REVIEW','GEO_REVIEW'):
        submit(e,tid,good_review(stage));approve()
        assert e.status(tid)['feedback'][-1]['status']=='pending_revision'
    submit(e,tid,good_review('CONTENT_REVIEW'))
    assert e.next_action(tid)['stage']=='LEARNING_REVIEW'
    # A second edit invalidates the first unapproved fix, including its reflection.
    action=e.next_action(tid)
    e.revise(tid,action['action_id'],action['expected_revision'],'再补充核对建议',user_ref='test:user:second-feedback')
    submit(e,tid,plan())
    assert e.next_action(tid)['stage']=='PLANNING'
    approve();submit(e,tid,draft())
    for stage in ('FACT_REVIEW','GEO_REVIEW'):
        submit(e,tid,good_review(stage));approve()
    submit(e,tid,good_review('CONTENT_REVIEW'))
    first=e.status(tid)['feedback'][0]
    submit(e,tid,{'feedback_id':first['feedback_id'],'reason':'第一条修改须重新核对','reason_uncertain':False,'corrective_action':'新稿已重审','check_method':'对照原意见与当前稿'})
    reflect(e,tid);approve()
    assert all(f['status']=='confirmed' for f in e.status(tid)['feedback'])

def test_third_party_api_runs_all_three_geo_review_rounds(current_engine,text_server):
    from test_engine import good_review
    config,calls,response=text_server;config['max_requests_per_task']=12
    e=current_engine;e.settings['text_provider']=config
    tid=e.start('test-product','automatic',text_source='api',user_ref='test:user:api',geo_brief=brief())['task_id']
    e.run_text(tid)
    response.clear();response.update({'topics':[{'topic_id':'T1','direction':'资料核对','question_summary':brief()['original_title'],'source_ids':['S1'],'scope':'product_specific','count_basis':'conversation','verified_count':1,'supporting_fact_ids':['F1'],'distinct_angles':['核对准备'],'gaps':[],'status':'ready','priority_reason':'虚构问题'}],'coverage_note':'测试'})
    e.run_text(tid);e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='test:user:selection')
    for stage,result in [('PLANNING',plan()),('WRITING',draft()),*[(s,good_review(s)) for s in ('FACT_REVIEW','GEO_REVIEW','CONTENT_REVIEW','FINAL_REVIEW')]]:
        assert e.next_action(tid)['tool']=='run-text' and e.next_action(tid)['stage']==stage
        response.clear();response.update(result);e.run_text(tid)
    assert e.export(tid)
    assert len(calls)==8
    assert [json_message['messages'][0]['content'] for json_message in calls if '第二轮独立GEO' in json_message['messages'][0]['content']]

def test_new_plan_cannot_cite_unknown_case_or_unapproved_product_fact(current_engine):
    from test_engine import submit
    e=current_engine;tid=prepare(e);e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='test:user:select')
    for path in ('scenario_evidence','product_evidence'):
        invalid=plan();key='source_ids' if path=='scenario_evidence' else 'fact_ids'
        invalid['geo'][path][key]=['invented']
        with pytest.raises(ValueError):submit(e,tid,invalid)

def test_long_draft_can_pass_with_substantive_additional_paragraphs():
    from geo_article_studio.editorial import validate_draft,render_body,char_count
    value=draft();b=brief();b['article_type']='long'
    value['geo']['sections'][0]['text']+='\n\n'+''.join(['还应留意资料是否对应正在考虑的版本。','如果不同版本有差异，应分别记录，不混合引用。','向商家提问时可以把原文与具体疑问一起提供。','这样能更清楚地说明需要确认的条件。','对于现场情况，记录时间和测量方式也有助于后续核对。','测量资料不完整时，先补齐必要信息，再比较方案。','路线上的不同位置可能需要分别确认。','通行条件不能只看某一个入口，还应考虑实际经过的其他位置。','交流时使用清楚的描述，有助于对方给出具体回答。','收到回答后，应检查其是否真正回应原问题。','没有明确结论的部分仍应标记待核实。','最终决定应结合完整资料，而不是单独依赖某一句宣传。'])
    value['body']=render_body(value['geo']);assert char_count(value['body'])>=1000
    validate_draft(value,plan(),b)

def test_new_four_image_flow_downloads_and_exports_independent_files(current_engine,server,monkeypatch):
    from test_engine import submit,good_review
    from test_images import config
    from pathlib import Path
    from PIL import Image
    e=current_engine
    monkeypatch.setenv('GEO_TEST_KEY','offline-fixture')
    e.settings.update(image_provider=config(server),reference_fallback={'user_ref':'test:user:no-reference'},host={'visual_capability':True,'visual_verification_ref':'SIMULATED_ONLY'})
    e.settings['defaults'].update(image_dimensions=[32,24],image_ratio='4:3',image_format='png',image_text_policy='none')
    e.settings['limits'].update(max_image_requests_per_task=4,max_generation_attempts_per_image=1)
    tid=prepare(e);e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[4]}],user_ref='test:user:four-images')
    submit(e,tid,plan());submit(e,tid,draft())
    for stage in ('FACT_REVIEW','GEO_REVIEW','CONTENT_REVIEW'):submit(e,tid,good_review(stage))
    aid=e.status(tid)['articles'][0]['article_id']
    roles=['cover','content_summary','real_scene','product_summary']
    images=[{'image_id':f'{aid}_I{i:02d}','article_id':aid,'paragraph':i,'purpose':'虚构流程测试','scene':'中性示意场景','people_actions':'','show_product':False,'product_image_ids':[],'reference_image_ids':[],'borrow':[],'immutable':[],'allowed_text':'','prompt':'独立测试图，无产品无文字','fact_ids':[],'role':role,'layout':'single'} for i,role in enumerate(roles,1)]
    invalid=copy.deepcopy(images);invalid[1]['role']='cover'
    with pytest.raises(ValueError):submit(e,tid,{'images':invalid})
    submit(e,tid,{'images':images})
    for _ in range(4):e.run_image(tid)
    for stage in ('IMAGE_REVIEW','FINAL_REVIEW'):
        assert e.next_action(tid)['stage']==stage
        result=good_review(stage);result['viewed_image_ids']=[p['image_id'] for p in images]
        submit(e,tid,result)  # Scripted verdict, explicitly not real visual review.
    output=Path(e.export(tid));files=list(output.rglob('*.png'))
    assert len(server['requests'])==4 and len(files)==4
    assert len({p.parent for p in files})==1
    for path in files:
        with Image.open(path) as picture:assert picture.size==(32,24)
