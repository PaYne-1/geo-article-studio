"""Independent safety regressions from review; all records are fictional fixtures."""
import json
from pathlib import Path

import pytest

from test_engine import engine, analyze, submit, good_review, reflect


def finish_text(engine):
    tid=analyze(engine)
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:select')
    submit(engine,tid,{'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']})
    submit(engine,tid,{'title':'虚构测试文章','body':'这是虚构测试的中性正文。','claims':[]})
    submit(engine,tid,good_review('TEXT_REVIEW'))
    submit(engine,tid,good_review('FINAL_REVIEW'))
    engine.export(tid)
    return tid


def test_next_action_after_completion_returns_finished(engine):
    tid=finish_text(engine)
    action=engine.next_action(tid)
    assert action['kind']=='FINISHED'
    assert Path(action['output_path']).is_dir()


def test_formal_rule_file_can_be_updated_in_place_and_reimported(engine,tmp_path):
    source=tmp_path/'rules.json'
    new=json.loads(source.read_text(encoding='utf-8'))
    new['version']='2'
    new['rules'][0]['terms'].append('新增测试禁词')
    source.write_text(json.dumps(new,ensure_ascii=False),encoding='utf-8')
    engine.rules.import_file(source,user_ref='user:explicit-rule-update')
    current=engine.rules.snapshot('test-product')
    active=[rule for rule in current['rules'] if rule['status']=='active']
    assert len(active)==1
    assert '新增测试禁词' in active[0]['terms']


def test_visual_review_cannot_pass_with_missing_actual_image(engine):
    tid=analyze(engine)
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:select')
    t=engine.status(tid)
    t['mode']='learning'
    t['stage']=t['state']='IMAGE_REVIEW'
    a=t['articles'][0]; a['image_count']=1
    a['images']={'A001_I01':{'path':str(engine._path(tid)/'never-produced.png'),'hash':'f'*64}}
    engine._save(t)
    review=good_review('IMAGE_REVIEW')
    review['reviewer']='human'
    review['viewed_image_ids']=['A001_I01']
    with pytest.raises(ValueError,match='图片|文件'):
        submit(engine,tid,review,actor='user')


def test_approved_numeric_fact_uses_product_registry_contract():
    from geo_article_studio.review import check_text
    facts=[{'fact_id':'fact_fixture','status':'approved','field':'测试宽度','value':'12厘米',
            'claim':'测试宽度：12厘米','quote':'测试宽度：12厘米','source_ids':['fixture-source']}]
    article={'title':'虚构测试参数说明','body':'测试宽度为12厘米。',
             'claims':[{'text':'测试宽度为12厘米','fact_ids':['fact_fixture']}]}
    assert check_text(article,facts,[])==[]


def test_article_scoped_feedback_does_not_leak_to_next_task(engine):
    tid=analyze(engine,'learning')
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selection')
    plan={'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']}
    submit(engine,tid,plan)
    action=engine.next_action(tid)
    engine.revise(tid,action['action_id'],action['expected_revision'],'仅这篇不要人物',user_ref='user:feedback',scope='article')
    submit(engine,tid,plan)
    reflect(engine,tid)
    action=engine.next_action(tid)
    rule_id=engine.status(tid)['feedback'][-1]['proposed_rule_id']
    engine.approve(tid,action['action_id'],action['expected_revision'],user_ref='user:approve',rule_ids=[rule_id])
    assert rule_id in {r['rule_id'] for r in engine.next_action(tid)['context']['rules']}
    second=analyze(engine)
    engine.select(second,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:second-selection')
    assert rule_id not in {r['rule_id'] for r in engine.next_action(second)['context']['rules']}


def test_numeric_substring_is_not_source_evidence():
    from geo_article_studio.review import check_text
    facts=[{'fact_id':'F','status':'approved','text':'测试宽度112厘米'}]
    article={'title':'虚构测试','body':'测试宽度为12厘米',
             'claims':[{'text':'测试宽度为12厘米','fact_ids':['F']}]}
    assert any('数字' in error for error in check_text(article,facts,[]))


def test_untrusted_sidecar_cannot_authorize_external_upload(engine):
    tid=analyze(engine)
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selection')
    t=engine.status(tid); a=t['articles'][0]
    a['image_count']=1; a['results']['WRITING']={'title':'虚构测试','body':'示意正文','claims':[]}
    engine.settings['defaults']['image_text_policy']='none'
    t['sources']['Rfake']={'source_id':'Rfake','library_type':'reference_images','product_id':'general',
        'hash':'a'*64,'metadata':{'approved':True,'external_use_approved':True,
                                'sidecar_trust':'untrusted','trust':'untrusted'}}
    plan={'images':[{'image_id':'A001_I01','article_id':'A001','paragraph':1,'show_product':False,
                     'product_image_ids':[],'reference_image_ids':['Rfake'],'allowed_text':''}]}
    with pytest.raises(ValueError,match='授权|批准'):
        engine._validate_image_plan(t,a,plan)


def image_task(engine, count=1, *, limit_changes=None, pricing=None):
    """Reach generation through genuine public state transitions and snapshots."""
    engine.settings['defaults'].update(image_ratio='4:3',image_dimensions=[32,24],image_format='png',image_text_policy='none')
    engine.settings['limits'].update(max_image_requests_per_task=10,max_generation_attempts_per_image=3)
    engine.settings['limits'].update(limit_changes or {})
    engine.settings['image_provider']={'adapter':'openai_compatible','model':'offline-fixture'}
    engine.settings['host']['visual_capability']=True
    engine.settings['host']['visual_verification_ref']='offline-fixture-only'
    engine.settings['reference_fallback']={'user_ref':'user:test-diagram-no-reference','strategy':'虚构离线测试的纯说明图，不出现产品'}
    if pricing is not None: engine.settings['image_pricing']=pricing
    tid=analyze(engine)
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[count]}],user_ref='user:image-count-and-cap')
    submit(engine,tid,{'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']})
    submit(engine,tid,{'title':'虚构测试','body':'这是一段虚构离线测试的说明。','claims':[]})
    submit(engine,tid,good_review('TEXT_REVIEW'))
    plans=[{'image_id':f'A001_I{i:02d}','article_id':'A001','paragraph':1,'purpose':'测试说明',
            'scene':'虚构中性说明图','people_actions':'','show_product':False,'product_image_ids':[],
            'reference_image_ids':[],'borrow':[],'immutable':[],'allowed_text':'','prompt':'OFFLINE FIXTURE ONLY','fact_ids':[]}
           for i in range(1,count+1)]
    submit(engine,tid,{'images':plans})
    assert engine.status(tid)['state']=='GENERATING_IMAGES'
    return tid


class LedgerProvider:
    """Only the external service is fake; filesystem, validation and ledger are real."""
    def __init__(self,engine,tid):
        self.engine=engine; self.tid=tid; self.calls=[]; self.check_ok=True; self.error=None; self.callback=None
    def check(self): return {'ok':self.check_ok,'network_verified':False}
    def generate(self,prompt,refs,path,*,dimensions,image_format,request_id):
        from geo_article_studio.storage import read_json
        from PIL import Image
        # The write-ahead IN_FLIGHT record must exist before contacting the service.
        persisted=read_json(self.engine._path(self.tid)/'state.json')
        assert persisted['requests'][-1]['request_id']==request_id
        assert persisted['requests'][-1]['status']=='IN_FLIGHT'
        self.calls.append({'request_id':request_id,'path':str(path)})
        if self.callback: self.callback()
        if self.error: raise self.error
        Image.new('RGB',dimensions,'green').save(path,'PNG')
        return {'cost':None}


def mock_provider(monkeypatch,engine,tid):
    import geo_article_studio.images as image_module
    provider=LedgerProvider(engine,tid)
    monkeypatch.setattr(image_module,'ImageProvider',lambda config:provider)
    return provider


def test_provider_preflight_failure_does_not_count_request(engine,monkeypatch):
    tid=image_task(engine); provider=mock_provider(monkeypatch,engine,tid); provider.check_ok=False
    result=engine.run_image(tid)
    assert result['state']=='PAUSED'
    assert result['requests']==[] and provider.calls==[]


def test_unknown_paid_request_survives_restart_and_never_resubmits(engine,monkeypatch):
    from geo_article_studio.images import ProviderError
    from geo_article_studio.workflow import Engine
    tid=image_task(engine); provider=mock_provider(monkeypatch,engine,tid)
    provider.error=ProviderError('request_timeout',status_unknown=True)
    result=engine.run_image(tid)
    assert result['state']=='PAUSED' and result['requests'][0]['status']=='UNKNOWN'
    restarted=Engine(engine.settings,index=engine.index,products=engine.products)
    with pytest.raises(ValueError,match='收费状态不明'):
        restarted.resume(tid,user_ref='user:retry')
    with pytest.raises(ValueError): restarted.run_image(tid)
    assert len(provider.calls)==1
    assert len(restarted.status(tid)['requests'])==1


def test_maximum_three_attempts_includes_first_request(engine,monkeypatch):
    from geo_article_studio.images import ProviderError
    tid=image_task(engine); provider=mock_provider(monkeypatch,engine,tid)
    provider.error=ProviderError('rate_limited',retryable=True)
    for attempt in (1,2,3):
        result=engine.run_image(tid)
        assert len(provider.calls)==attempt
        assert result['requests'][-1]['attempt']==attempt
    result=engine.run_image(tid)
    assert result['state']=='PAUSED'
    assert len(provider.calls)==3 and len(result['requests'])==3


def test_authentication_failure_pauses_without_retries(engine,monkeypatch):
    from geo_article_studio.images import ProviderError
    tid=image_task(engine); provider=mock_provider(monkeypatch,engine,tid)
    provider.error=ProviderError('authentication_failed')
    result=engine.run_image(tid)
    assert result['state']=='PAUSED' and result['requests'][0]['status']=='FAILED'
    assert result['requests'][0]['error_code']=='authentication_failed'
    with pytest.raises(ValueError): engine.run_image(tid)
    assert len(provider.calls)==1


@pytest.mark.parametrize('when',['before','during'])
def test_pause_marker_prevents_new_requests(engine,monkeypatch,when):
    from geo_article_studio.storage import atomic_json
    tid=image_task(engine,count=2); provider=mock_provider(monkeypatch,engine,tid)
    def pause_marker(): atomic_json(engine._path(tid)/'pause.json',{'user_ref':'user:pause'})
    if when=='before': pause_marker()
    else: provider.callback=pause_marker
    result=engine.run_image(tid)
    assert result['state']=='PAUSED'
    assert len(provider.calls)==(0 if when=='before' else 1)
    with pytest.raises(ValueError): engine.run_image(tid)
    assert len(provider.calls)==(0 if when=='before' else 1)


@pytest.mark.parametrize('pricing',[None,{'price_per_request':1,'currency':'USD'}])
def test_amount_cap_without_verified_pricing_blocks_paid_call(engine,monkeypatch,pricing):
    tid=image_task(engine,limit_changes={'max_cost':5,'currency':'USD'},pricing=pricing)
    provider=mock_provider(monkeypatch,engine,tid)
    result=engine.run_image(tid)
    assert result['state']=='PAUSED'
    assert result['requests']==[] and provider.calls==[]


def test_verified_amount_cap_blocks_next_request(engine,monkeypatch):
    tid=image_task(engine,count=2,limit_changes={'max_cost':1,'currency':'USD'},
                   pricing={'price_per_request':.6,'currency':'USD','verified_source':'offline pricing fixture'})
    provider=mock_provider(monkeypatch,engine,tid)
    engine.run_image(tid)
    result=engine.run_image(tid)
    assert result['state']=='PAUSED' and len(provider.calls)==1
    assert len(result['requests'])==1


def test_restart_reuses_successful_image_and_does_not_generate_twice(engine,monkeypatch):
    from geo_article_studio.workflow import Engine
    tid=image_task(engine,count=2); provider=mock_provider(monkeypatch,engine,tid)
    first=engine.run_image(tid)
    assert first['requests'][0]['status']=='SUCCEEDED'
    existing=Path(first['articles'][0]['images']['A001_I01']['path']).read_bytes()
    restarted=Engine(engine.settings,index=engine.index,products=engine.products)
    second=restarted.run_image(tid)
    assert second['state']=='IMAGE_REVIEW'
    assert len(provider.calls)==2
    assert provider.calls[0]['path'].endswith('A001_I01.png')
    assert provider.calls[1]['path'].endswith('A001_I02.png')
    assert Path(provider.calls[0]['path']).read_bytes()==existing
    with pytest.raises(ValueError): restarted.run_image(tid)
    assert len(provider.calls)==2


def test_restart_checks_completed_images_before_new_paid_request(engine,monkeypatch):
    from geo_article_studio.workflow import Engine
    tid=image_task(engine,count=2); provider=mock_provider(monkeypatch,engine,tid)
    first=engine.run_image(tid)
    Path(first['articles'][0]['images']['A001_I01']['path']).unlink()
    restarted=Engine(engine.settings,index=engine.index,products=engine.products)
    with pytest.raises(ValueError,match='图片|文件'):
        restarted.run_image(tid)
    assert len(provider.calls)==1


def test_finished_action_rechecks_published_files(engine):
    tid=finish_text(engine)
    published=engine.status(tid)['articles'][0]['published_files']
    Path(next(iter(published))).unlink()
    with pytest.raises(ValueError,match='文件|交付'):
        engine.next_action(tid)

def test_single_image_revision_preserves_other_image_and_body(engine,monkeypatch):
    import copy
    tid=image_task(engine,count=2);provider=mock_provider(monkeypatch,engine,tid)
    engine.run_image(tid);state=engine.run_image(tid)
    body=copy.deepcopy(state['articles'][0]['results']['WRITING'])
    preserved=copy.deepcopy(state['articles'][0]['images']['A001_I02'])
    plans=copy.deepcopy(state['articles'][0]['results']['IMAGE_PLANNING'])
    action=engine.next_action(tid)
    engine.revise(tid,action['action_id'],action['expected_revision'],'仅重做第一张的构图',user_ref='user:image-feedback',image_id='A001_I01')
    plans['images'][0]['scene']='新的虚构中性构图'
    submit(engine,tid,plans);reflect(engine,tid)
    action=engine.next_action(tid)
    engine.approve(tid,action['action_id'],action['expected_revision'],user_ref='user:approve-new-image-plan')
    result=engine.run_image(tid)
    assert result['articles'][0]['results']['WRITING']==body
    assert result['articles'][0]['images']['A001_I02']==preserved
    assert len(provider.calls)==3
    assert result['state']=='IMAGE_REVIEW'

def test_task_parent_symlink_cannot_escape_workspace(engine,tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    task_parent=engine.root/'tasks'
    try: task_parent.symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('当前平台无创建符号链接权限')
    with pytest.raises(ValueError,match='路径|越界'):
        engine.start('test-product','automatic',text_source='host',user_ref='user:real')
    assert list(outside.iterdir())==[]

def test_newly_detected_fact_conflict_invalidates_task_snapshot(engine,monkeypatch):
    fact={'fact_id':'test-fact','text':'虚构已批准事实','status':'approved'}
    monkeypatch.setattr(engine.products,'facts',lambda *a,**kw:[fact])
    task=engine.start('test-product','automatic',text_source='host',user_ref='user:start')
    monkeypatch.setattr(engine.products,'facts',lambda *a,**kw:[])
    with pytest.raises(ValueError,match='事实'):
        submit(engine,task['task_id'],{'understanding':'测试','source_ids':['S1'],'gaps':[]})
