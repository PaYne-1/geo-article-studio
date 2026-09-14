import copy
import pytest
from pathlib import Path

class Index:
    def __init__(self,root):
        p=root/'source.txt';p.write_text('虚构测试问题：能否收纳',encoding='utf-8')
        import hashlib
        self.row={'source_id':'S1','library_type':'chat','product_id':'test-product','hash':hashlib.sha256(p.read_bytes()).hexdigest(),'path':str(p),'location':{'relative_path':'source.txt','line_start':1,'line_end':1},'snippet':'客户：能否收纳','metadata':{'role':'customer','conversation_id':'C1','date':None,'trust':'untrusted'}}
    def update(self): return {'parsed':1,'failed':0,'excluded':0}
    def search(self,*args,**kw): return [copy.deepcopy(self.row)] if kw.get('library_type') in (None,'chat') else []
    def get(self,sid):
        if sid!='S1': raise ValueError('source不存在')
        return copy.deepcopy(self.row)

class Products:
    def get(self,pid):
        if pid!='test-product': raise ValueError('产品不存在')
        return {'product_id':pid,'name':'虚构测试产品','version':'test'}
    def facts(self,pid,approved_only=True): return []

@pytest.fixture
def engine(tmp_path):
    from geo_article_studio.workflow import Engine
    from geo_article_studio.learning import RuleStore
    import json
    settings={'workspace_root':str(tmp_path/'work'),'output_root':str(tmp_path/'out'),'defaults':{'article_length':{'min':1,'max':1000}},'limits':{'max_text_revision_attempts':3,'max_generation_attempts_per_image':3},'host':{'visual_capability':False},'partial_policy':'pause_all'}
    r=tmp_path/'rules.json';r.write_text(json.dumps({'formal':True,'version':'1','rules':[{'rule_id':'R1','scope':'global','target_id':None,'type':'hard_ban','content':'禁止虚构','terms':['测试违禁词'],'check_method':'语义','severity':'hard'}]}),encoding='utf-8')
    RuleStore(tmp_path/'work').import_file(r,user_ref='user:rules')
    return Engine(settings,index=Index(tmp_path),products=Products())

def submit(e,tid,result,actor='model'):
    a=e.next_action(tid)
    return e.submit(tid,a['action_id'],a['expected_revision'],result,actor=actor,user_ref='user:test' if actor=='user' else None)

def analyze(e,mode='automatic'):
    t=e.start('test-product',mode,user_ref='user:start'); tid=t['task_id']
    submit(e,tid,{'understanding':'虚构测试','source_ids':['S1'],'gaps':[]})
    if mode=='learning':
        a=e.next_action(tid);e.approve(tid,a['action_id'],a['expected_revision'],user_ref='user:approve')
    submit(e,tid,{'topics':[{'topic_id':'T1','direction':'收纳','question_summary':'能否收纳','source_ids':['S1'],'scope':'product_specific','count_basis':'conversation','verified_count':1,'supporting_fact_ids':[],'distinct_angles':['收纳准备','空间整理'],'gaps':[],'status':'ready','priority_reason':'实际咨询'}],'coverage_note':'一个测试会话'})
    return tid

def good_review(stage):
    from geo_article_studio.review import REVIEW_CHECKS
    return {'verdict':'passed','reviewer':'qwen','viewed_image_ids':[],'checks':[{'check_id':x,'verdict':'passed','severity':'info','evidence':'测试中性内容已核对','suggestion':''} for x in REVIEW_CHECKS[stage]]}

def reflect(e,tid):
    action=e.next_action(tid)
    assert action['stage']=='LEARNING_REVIEW'
    f=e.status(tid)['feedback'][-1]
    return submit(e,tid,{'feedback_id':f['feedback_id'],'reason':'测试反馈要求表达简洁','reason_uncertain':False,'corrective_action':'删除重复内容并重审','check_method':'逐条对照当前用户反馈'})

def test_auto_zero_images_full_delivery_and_resume(engine):
    e=engine; tid=analyze(e)
    assert e.next_action(tid)['stage']=='WAITING_SELECTION'
    e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:select')
    submit(e,tid,{'angle':'收纳准备','question':'如何准备收纳空间','outline':['先核对空间'],'fact_ids':[],'source_ids':['S1']})
    submit(e,tid,{'title':'收纳前的准备','body':'先清理空间，再核对实际可用位置。','claims':[]})
    submit(e,tid,good_review('TEXT_REVIEW'))
    submit(e,tid,good_review('FINAL_REVIEW'))
    path=e.export(tid)
    assert Path(path).is_dir()
    assert e.status(tid)['state']=='COMPLETED'
    files=list(Path(path).rglob('*'))
    assert len([x for x in files if x.is_file()])==2
    assert e.export(tid)==path
    assert e.status(tid)['requests']==[]

def test_learning_revise_keeps_stage_stale_approval_and_restart(engine):
    e=engine;tid=analyze(e,'learning')
    e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selection')
    submit(e,tid,{'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']})
    old=e.next_action(tid)
    e.revise(tid,old['action_id'],old['expected_revision'],'这篇更简洁',user_ref='user:feedback')
    with pytest.raises(ValueError): e.approve(tid,old['action_id'],old['expected_revision'],user_ref='user:old')
    assert e.next_action(tid)['stage']=='PLANNING'
    submit(e,tid,{'angle':'收纳准备','question':'如何准备','outline':['整理'],'fact_ids':[],'source_ids':['S1']})
    pending=e.next_action(tid)
    with pytest.raises(ValueError):e.approve(tid,pending['action_id'],pending['expected_revision'],user_ref='user:too-early')
    reflect(e,tid)
    current=e.next_action(tid)
    assert current['kind']=='NEEDS_USER'
    assert e.status(tid)['feedback'][0]['status']=='revised_waiting_approval'
    e.approve(tid,current['action_id'],current['expected_revision'],user_ref='user:new')
    assert e.next_action(tid)['stage']=='WRITING'

def test_reject_wrong_action_model_approval_and_source(engine):
    e=engine;t=e.start('test-product','learning',user_ref='user:start');tid=t['task_id'];a=e.next_action(tid)
    with pytest.raises(ValueError): e.submit(tid,'wrong',a['expected_revision'],{'understanding':'x','source_ids':['S1'],'gaps':[]})
    with pytest.raises(ValueError): submit(e,tid,{'understanding':'x','source_ids':['invented'],'gaps':[]})
    submit(e,tid,{'understanding':'x','source_ids':['S1'],'gaps':[]});a=e.next_action(tid)
    with pytest.raises(ValueError): e.approve(tid,a['action_id'],a['expected_revision'],actor='model',user_ref='model:fake')

def test_pause_prevents_advancing(engine):
    e=engine;tid=analyze(e)
    e.pause(tid,user_ref='user:pause')
    assert e.next_action(tid)['stage']=='PAUSED'
    with pytest.raises(ValueError): e.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selection')
    e.resume(tid,user_ref='user:resume')
    assert e.next_action(tid)['stage']=='WAITING_SELECTION'
