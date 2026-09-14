"""Host-neutral contracts; fake host names do not imply real provider integration."""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from test_engine import engine, analyze, submit, good_review

def test_neutral_model_reviewer_and_legacy_qwen_both_accepted():
    from geo_article_studio.host_bridge import validate_result
    for reviewer in ('model','qwen'):
        review=good_review('TEXT_REVIEW');review['reviewer']=reviewer
        validate_result('TEXT_REVIEW',review)

def test_host_contract_reports_unknown_and_declared_capabilities():
    from geo_article_studio.hosts import assess_host
    unknown=assess_host({})
    assert unknown['agent']=='generic' and unknown['verification']=='undeclared'
    assert unknown['ready'] is False
    configured={'host':{'agent':'custom-local-agent','model':'host-selected-model','capabilities':{'file_io':True,'terminal':True,'structured_results':True,'human_confirmation':True}}}
    assert assess_host(configured)['ready'] is True
    image=assess_host(configured,stage='IMAGE_REVIEW',mode='automatic',has_images=True)
    assert image['ready'] is False and 'visual_review' in image['missing']
    assert assess_host(configured,stage='IMAGE_REVIEW',mode='learning',has_images=True)['ready'] is True

def test_explicit_unknown_visual_does_not_inherit_legacy_true():
    from geo_article_studio.hosts import assess_host, visual_available
    settings={'host':{'visual_capability':True,'visual_verification_ref':'old-host-only','capabilities':{'file_io':True,'terminal':True,'structured_results':True,'human_confirmation':True,'visual_review':None}}}
    assert visual_available(settings) is False
    report=assess_host(settings,stage='IMAGE_REVIEW',has_images=True)
    assert report['ready'] is False and report['capabilities']['visual_review'] is None
    assert visual_available({'host':{'visual_capability':True}}) is True

def test_host_check_rejects_unknown_stage():
    from geo_article_studio.hosts import assess_host
    with pytest.raises(ValueError,match='阶段'):
        assess_host({},stage='IMAGE_REVEIW',has_images=True)

def test_reflection_producer_records_actual_action_stage(engine):
    tid=analyze(engine,'learning')
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selected')
    action=engine.next_action(tid)
    engine.revise(tid,action['action_id'],action['expected_revision'],'更简洁',user_ref='user:feedback')
    submit(engine,tid,{'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']})
    action=engine.next_action(tid)
    feedback=engine.status(tid)['feedback'][-1]
    engine.submit(tid,action['action_id'],action['expected_revision'],{'feedback_id':feedback['feedback_id'],'reason':'用户要求简洁','reason_uncertain':False,'corrective_action':'精简大纲','check_method':'对照反馈'},producer={'agent':'generic','model':'test'})
    assert engine.status(tid)['model_submissions'][-1]['stage']=='LEARNING_REVIEW'

def test_generic_agent_full_zero_image_flow_records_model_provenance(engine):
    engine.settings['host']={'agent':'other-agent','model':'other-model','capabilities':{'file_io':True,'terminal':True,'structured_results':True,'human_confirmation':True}}
    tid=analyze(engine)
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selected')
    submit(engine,tid,{'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']})
    submit(engine,tid,{'title':'通用宿主测试','body':'这是一篇不声明产品性能的测试说明。','claims':[]})
    for stage in ('TEXT_REVIEW','FINAL_REVIEW'):
        action=engine.next_action(tid)
        assert action['host_contract']['protocol']=='geo.host.v1'
        result=good_review(stage);result['reviewer']='model'
        engine.submit(tid,action['action_id'],action['expected_revision'],result,producer={'agent':'other-agent','model':'other-model'})
    assert Path(engine.export(tid)).is_dir()
    audit=engine.status(tid)['model_submissions']
    assert audit[-1]['producer']['model']=='other-model'
    assert audit[-1]['identity_verification']=='self_reported'

def test_declared_incompatible_host_is_blocked_before_task_creation(engine):
    engine.settings['host']={'agent':'chat-only','capabilities':{'file_io':False,'terminal':False,'structured_results':True,'human_confirmation':True}}
    with pytest.raises(ValueError,match='宿主|能力'):
        engine.start('test-product','automatic',user_ref='user:start')
    assert not (engine.root/'tasks').exists()

def test_host_check_available_without_production_configuration(tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts'/'geo.py'
    profile=tmp_path/'profile.json'
    profile.write_text(json.dumps({'host':{'agent':'custom','capabilities':{'file_io':True,'terminal':True,'structured_results':True,'human_confirmation':True}}}),encoding='utf-8')
    result=subprocess.run([sys.executable,str(script),'host-check','--file',str(profile)],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['protocol']=='geo.host.v1'

@pytest.mark.parametrize('prefix',['/geo-article-studio','$geo-article-studio'])
def test_explicit_host_invocation_prefixes(prefix):
    from geo_article_studio.host_bridge import route
    assert route(prefix+' 开始任务')=='start'
    assert route(prefix+' 确认',origin='source') is None
