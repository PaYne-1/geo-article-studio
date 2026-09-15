import json
import subprocess
import sys
from pathlib import Path

from geo_article_studio.host_bridge import form_for

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'geo.py'


def test_configuration_removes_legacy_length_and_keeps_task_length_choice():
    form=form_for('配置任务',{'defaults':{'article_length':{'min':1,'max':50}}})
    assert 'article_length' not in form['values']
    assert all('article_length' not in section['fields'] for section in form['sections'])
    start=form_for('开始任务',{})
    assert start['choices']['article_type']==['short','long']


def test_api_requirements_are_conditional_and_technical_fields_are_agent_owned():
    form=form_for('配置任务',{})
    shown={field for section in form['sections'] for field in section['fields']}
    assert set(form['missing'])=={'chat','product_info','reference_images','product_images','output_root','rule_import_sources'}
    assert {'provider','supports_references','text_adapter','text_endpoint'}<=set(form['agent_fields'])
    assert not shown.intersection(form['agent_fields'])
    assert 'base_url' in form['conditional_missing']['with_images']
    assert 'text_base_url' in form['conditional_missing']['text_api']
    assert form['persistence']['can_save_partial'] is True


def test_form_marks_saved_defaults_and_unsaved_provided_values_separately():
    settings={'image_provider':{'base_url':'https://example.invalid/v1','model':'saved-model','supports_references':False}}
    form=form_for('配置任务',settings,{'model':'new-model'})
    assert form['field_states']['base_url']=='saved'
    assert form['field_states']['model']=='provided'
    assert form['field_states']['supports_references']=='saved'
    assert form['field_states']['api_key_env']=='default'
    assert 'model' not in form['conditional_missing']['with_images']
    assert settings['image_provider']['model']=='saved-model'


def test_landscape_is_a_preference_without_changing_existing_specs():
    form=form_for('配置任务',{'defaults':{'image_dimensions':[1024,1024],'image_ratio':'1:1'}})
    assert form['values']['dimensions']==[1024,1024]
    assert form['values']['image_ratio']=='1:1'
    assert form['recommendations']['orientation']=='landscape'
    assert '1024×1024' not in form_for('配置任务',{})['message']
    assert form_for('配置任务',{})['values']['dimensions'] is None


def cli(config,*args):
    result=subprocess.run([sys.executable,str(SCRIPT),'--config',str(config),*args],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
    return result.stdout


def test_partial_save_returns_checks_and_new_process_reads_saved_settings(tmp_path):
    config=tmp_path/'runtime'/'settings.json'
    data=tmp_path/'partial.json'
    data.write_text(json.dumps({'default_product_name':'虚构配置测试','text_provider':{'base_url':'https://example.invalid/v1','model':'persisted-model'}}),encoding='utf-8')
    saved=json.loads(cli(config,'configure','--file',str(data)))
    assert saved['saved']==str(config.resolve())
    assert saved['configuration']['persistence']['saved_config_loaded'] is True
    assert saved['configuration']['checks']['paid_request_sent'] is False
    assert saved['configuration']['checks']['text_api']['ok'] is False
    assert saved['configuration']['conditional_missing']['text_api']
    data.write_text(json.dumps({'defaults':{'image_text_policy':'none'}}),encoding='utf-8')
    cli(config,'configure','--file',str(data))
    form=json.loads(cli(config,'form','配置任务'))
    assert form['values']['text_model']=='persisted-model'
    assert form['field_states']['text_model']=='saved'
    assert form['persistence']['config_path']==str(config.resolve())
    assert 'text_model' not in form['conditional_missing']['text_api']


def test_cli_text_form_is_ready_to_display_without_internal_field_names(tmp_path):
    message=cli(tmp_path/'absent.json','form','配置任务','--format','text')
    assert '最少字数' not in message
    assert '文章篇幅' not in message
    assert '适配器：' not in message
    assert '是否支持参考图：' not in message
    assert '图片API' in message and '第三方文字API' in message
    assert '未保存' in message and '本地' in message


def test_form_and_save_checks_do_not_send_requests_or_disclose_credentials(tmp_path,monkeypatch):
    import socket
    from geo_article_studio.cli import parser,run
    monkeypatch.setenv('TEST_LOCAL_FORM_KEY','private-local-secret')
    def denied(*args,**kwargs):raise AssertionError('network access during form/configuration')
    monkeypatch.setattr(socket.socket,'connect',denied)
    config=tmp_path/'settings.json';data=tmp_path/'partial.json'
    data.write_text(json.dumps({'image_provider':{'api_key_env':'TEST_LOCAL_FORM_KEY'}}),encoding='utf-8')
    result,code=run(parser().parse_args(['--config',str(config),'configure','--file',str(data)]))
    assert code==0 and result['configuration']['checks']['paid_request_sent'] is False
    assert 'private-local-secret' not in json.dumps(result)
    assert result['configuration']['checks']['credentials']['image_api']['connected'] is True
