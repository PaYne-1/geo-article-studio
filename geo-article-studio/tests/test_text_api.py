import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from test_engine import engine

@pytest.fixture
def text_server():
    calls=[]; response={'understanding':'虚构资料预检，不声明产品性能','source_ids':['S1'],'gaps':[]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            data=json.dumps({'choices':[{'message':{'content':json.dumps(response,ensure_ascii=False)},'finish_reason':'stop'}]}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config={'adapter':'openai_chat_compatible','base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture-model','api_key_env':'TEST_TEXT_KEY','auth_type':'none','allowed_local_hosts':['127.0.0.1'],'protocol_document':'fixture:chat-spec','max_requests_per_task':5}
    yield config,calls,response
    server.shutdown();server.server_close();thread.join()

def test_task_form_always_offers_model_source_and_preserves_config():
    from geo_article_studio.host_bridge import form_for
    form=form_for('开始任务',{})
    assert form['values']['text_source'] is None
    assert form['choices']['text_source']==['host','api']
    assert 'text_source' in form['missing']
    assert form['text_options'][1]['available'] is False
    config=form_for('配置任务',{'text_provider':{'base_url':'https://example.invalid/v1','model':'saved','api_key_env':'SAVED_KEY'}})
    assert config['values']['text_model']=='saved' and config['values']['text_api_key_env']=='SAVED_KEY'

def test_api_selection_missing_config_blocks_before_start(engine):
    with pytest.raises(ValueError,match='文字'):
        engine.start('test-product','learning',user_ref='user:choose-api',text_source='api')

def test_real_local_http_bridge_stops_at_human_gate(engine,text_server):
    config,calls,response=text_server;engine.settings['text_provider']=config
    task=engine.start('test-product','learning',user_ref='user:choose-api',text_source='api');tid=task['task_id']
    assert engine.next_action(tid)['tool']=='run-text'
    result=engine.run_text(tid)
    assert result['state']=='WAITING_APPROVAL'
    assert len(calls)==1 and calls[0]['model']=='fixture-model'
    body=json.dumps(calls[0],ensure_ascii=False)
    assert '虚构测试问题' in body or '客户：能否收纳' in body
    assert str(engine.root) not in body and 'absolute_path' not in body
    assert engine.status(tid)['text_source']=='api'
    assert engine.status(tid)['text_requests'][0]['status']=='APPLIED'
    with pytest.raises(ValueError):engine.run_text(tid)
    assert len(calls)==1

def test_bad_api_result_requires_explicit_retry_without_host_fallback(engine,text_server):
    config,calls,response=text_server;engine.settings['text_provider']=config
    task=engine.start('test-product','learning',user_ref='user:choose-api',text_source='api');tid=task['task_id']
    response['extra']='not allowed'
    with pytest.raises(Exception):engine.run_text(tid)
    assert len(calls)==1 and engine.status(tid)['text_requests'][0]['status']=='REJECTED'
    with pytest.raises(ValueError):engine.run_text(tid)
    assert len(calls)==1
    request=engine.status(tid)['text_requests'][0]
    engine.resolve_text_request(tid,request['request_id'],user_ref='user:checked-cost-and-retry')
    response.pop('extra');engine.run_text(tid)
    assert len(calls)==2

def test_host_selection_never_calls_external_api(engine,text_server):
    config,calls,_=text_server;engine.settings['text_provider']=config
    tid=engine.start('test-product','automatic',user_ref='user:host',text_source='host')['task_id']
    assert engine.next_action(tid)['kind']=='NEEDS_MODEL'
    with pytest.raises(ValueError):engine.run_text(tid)
    assert not calls

def test_received_response_recovers_without_second_paid_request(engine,text_server,monkeypatch):
    config,calls,_=text_server;engine.settings['text_provider']=config
    tid=engine.start('test-product','learning',user_ref='user:api',text_source='api')['task_id']
    original=engine.submit
    def crash(*args,**kwargs):raise RuntimeError('simulated crash after response persisted')
    monkeypatch.setattr(engine,'submit',crash)
    with pytest.raises(RuntimeError):engine.run_text(tid)
    assert engine.status(tid)['text_requests'][0]['status']=='RECEIVED'
    monkeypatch.setattr(engine,'submit',original)
    assert engine.run_text(tid)['state']=='WAITING_APPROVAL'
    assert len(calls)==1

def test_request_cap_and_manual_result_cannot_bypass_api_selection(engine,text_server):
    config,calls,_=text_server;config['max_requests_per_task']=1;engine.settings['text_provider']=config
    tid=engine.start('test-product','automatic',user_ref='user:api',text_source='api')['task_id']
    a=engine.next_action(tid)
    with pytest.raises(ValueError,match='文字API'):
        engine.submit(tid,a['action_id'],a['expected_revision'],{'understanding':'host fake','source_ids':['S1'],'gaps':[]})
    engine.run_text(tid)
    with pytest.raises(ValueError,match='上限'):engine.run_text(tid)
    assert len(calls)==1

def test_unknown_charge_blocks_retries_until_explicit_resolution(engine,text_server,monkeypatch):
    from geo_article_studio.text_api import TextProvider
    from geo_article_studio.images import ProviderError
    config,_,_=text_server;engine.settings['text_provider']=config
    count=[]
    def timeout(*args):count.append(1);raise ProviderError('request_timeout',status_unknown=True)
    monkeypatch.setattr(TextProvider,'generate',timeout)
    tid=engine.start('test-product','automatic',user_ref='user:api',text_source='api')['task_id']
    with pytest.raises(ProviderError):engine.run_text(tid)
    assert engine.status(tid)['text_requests'][0]['status']=='UNKNOWN'
    with pytest.raises(ValueError):engine.run_text(tid)
    assert len(count)==1

def test_full_zero_image_flow_uses_api_for_each_independent_stage(engine,text_server):
    from test_engine import good_review
    config,calls,response=text_server;config['max_requests_per_task']=10;engine.settings['text_provider']=config
    tid=engine.start('test-product','automatic',user_ref='user:api',text_source='api')['task_id']
    engine.run_text(tid)
    response.clear();response.update({'topics':[{'topic_id':'T1','direction':'收纳','question_summary':'能否收纳','source_ids':['S1'],'scope':'product_specific','count_basis':'conversation','verified_count':1,'supporting_fact_ids':[],'distinct_angles':['收纳准备'],'gaps':[],'status':'ready','priority_reason':'测试咨询'}],'coverage_note':'虚构会话'})
    engine.run_text(tid);assert engine.next_action(tid)['kind']=='NEEDS_USER'
    engine.select(tid,[{'topic_id':'T1','article_count':1,'image_counts':[0]}],user_ref='user:selection')
    for result in ({'angle':'收纳准备','question':'如何准备','outline':['准备'],'fact_ids':[],'source_ids':['S1']},{'title':'测试准备','body':'这是没有产品性能主张的虚构测试文字。','claims':[]},good_review('TEXT_REVIEW'),good_review('FINAL_REVIEW')):
        response.clear();response.update(result);engine.run_text(tid)
    from pathlib import Path
    assert Path(engine.export(tid)).is_dir()
    assert len(calls)==6
    assert all(r['status']=='APPLIED' for r in engine.status(tid)['text_requests'])

def test_text_configuration_persists_across_cli_processes_and_partial_edits(tmp_path,text_server):
    import subprocess,sys
    from pathlib import Path
    config,_,_=text_server
    script=Path(__file__).resolve().parents[1]/'scripts/geo.py'
    target=tmp_path/'settings.json';incoming=tmp_path/'input.json'
    base=[sys.executable,str(script),'--config',str(target)]
    for value in ({'text_provider':config},{'defaults':{'image_text_policy':'none'}}):
        incoming.write_text(json.dumps(value),encoding='utf-8')
        result=subprocess.run(base+['configure','--file',str(incoming)],capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stdout
    saved=json.loads(target.read_text(encoding='utf-8'));assert saved['text_provider']==config
    result=subprocess.run(base+['form','开始任务'],capture_output=True,text=True,encoding='utf-8');assert result.returncode==0
    form=json.loads(result.stdout)
    assert form['text_options'][1]['available'] is True and form['values']['text_source'] is None

def test_text_provider_does_not_claim_visual_capability():
    from geo_article_studio.text_api import uses_text_api
    assert uses_text_api({'text_source':'api'},'IMAGE_PLANNING',{'image_count':1})
    assert not uses_text_api({'text_source':'api'},'IMAGE_REVIEW',{'image_count':1})
    assert not uses_text_api({'text_source':'api'},'FINAL_REVIEW',{'image_count':1})

def test_new_task_requires_explicit_text_source(engine):
    with pytest.raises(ValueError,match='请选择'):
        engine.start('test-product','learning',user_ref='user:start')

def test_external_context_redacts_free_text_and_drops_paths():
    from geo_article_studio.text_api import external_context
    a={'stage':'PREFLIGHT','result_schema':{},'context':{'extra_requirements':'电话13800138000，api_key=private-dummy-value','feedback':[{'text':'地址：虚构小区。'}],'sources':[{'location':{'absolute_path':'C:/private/file','relative_path':'13800138000.txt'}}]}}
    content=json.dumps(external_context(a),ensure_ascii=False)
    for value in ('13800138000','private-dummy-value','虚构小区','C:/private/file'):assert value not in content

@pytest.mark.parametrize('change_content',[False,True])
def test_received_result_after_pause_only_reuses_unchanged_content(engine,text_server,monkeypatch,change_content):
    config,calls,_=text_server;engine.settings['text_provider']=config
    tid=engine.start('test-product','learning',user_ref='user:api',text_source='api')['task_id']
    original=engine.submit
    def crash(*a,**k):raise RuntimeError('simulated crash')
    monkeypatch.setattr(engine,'submit',crash)
    with pytest.raises(RuntimeError):engine.run_text(tid)
    monkeypatch.setattr(engine,'submit',original)
    engine.pause(tid,user_ref='user:pause');engine.resume(tid,user_ref='user:resume')
    if change_content:
        a=engine.next_action(tid);engine.revise(tid,a['action_id'],a['expected_revision'],'预检增加新的关注点',user_ref='user:change')
        with pytest.raises(ValueError):engine.run_text(tid)
    else:
        assert engine.run_text(tid)['state']=='WAITING_APPROVAL'
    assert len(calls)==1

def test_persistent_text_provider_rejects_non_object_configuration():
    from geo_article_studio.config import validate_settings
    with pytest.raises(ValueError,match='文字'):
        validate_settings({'text_provider':'invalid'})

def test_cli_api_flow_with_real_library_index_and_saved_selection(tmp_path,text_server):
    import subprocess,sys
    from pathlib import Path
    config,calls,response=text_server
    libraries={name:str(tmp_path/name) for name in ('chat','product_info','reference_images','product_images')}
    for folder in libraries.values():Path(folder).mkdir()
    (Path(libraries['chat'])/'fixture.txt').write_text('虚构测试问题：写作前如何核对资料？',encoding='utf-8')
    settings={'libraries':libraries,'workspace_root':str(tmp_path/'work'),'output_root':str(tmp_path/'out'),'text_provider':config,'products':[{'product_id':'fixture','name':'虚构CLI测试产品','version':'test','source_ids':[],'image_source_ids':[]}],'source_mappings':{'chat/fixture.txt':'fixture'}}
    source=tmp_path/'input.json';target=tmp_path/'settings.json';source.write_text(json.dumps(settings),encoding='utf-8')
    script=Path(__file__).resolve().parents[1]/'scripts/geo.py';base=[sys.executable,str(script),'--config',str(target)]
    def run(*args):
        result=subprocess.run(base+list(args),capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stdout+result.stderr
        return json.loads(result.stdout)
    run('configure','--file',str(source))
    task=run('start','--product-id','fixture','--mode','learning','--text-source','api','--user-ref','test:user:choose-api')
    a=run('next-action',task['task_id']);response['source_ids']=[a['input_refs'][0]['source_id']]
    result=run('run-text',task['task_id'])
    assert result['state']=='WAITING_APPROVAL' and len(calls)==1
    persisted=run('status',task['task_id']);assert persisted['text_source']=='api'
    assert persisted['text_requests'][0]['status']=='APPLIED'

def test_pause_while_request_is_running_preserves_paid_response(engine,text_server,monkeypatch):
    from geo_article_studio.text_api import TextProvider
    config,calls,_=text_server;engine.settings['text_provider']=config
    tid=engine.start('test-product','learning',user_ref='user:api',text_source='api')['task_id']
    original=TextProvider.generate
    def delayed(provider,action):
        result=original(provider,action)
        engine.pause(tid,user_ref='user:pause-during-request')
        return result
    monkeypatch.setattr(TextProvider,'generate',delayed)
    with pytest.raises(ValueError):engine.run_text(tid)
    assert engine.status(tid)['text_requests'][0]['status']=='RECEIVED'
    engine.resume(tid,user_ref='user:resume')
    assert engine.run_text(tid)['state']=='WAITING_APPROVAL'
    assert len(calls)==1
