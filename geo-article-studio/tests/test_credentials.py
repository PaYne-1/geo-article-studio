import json
from pathlib import Path

import pytest


def test_credential_command_reads_hidden_input_and_never_returns_secret(tmp_path,monkeypatch):
    from geo_article_studio import credentials
    from geo_article_studio.cli import parser,run
    captured={}
    monkeypatch.setattr(credentials.getpass,'getpass',lambda prompt:'private-image-key')
    monkeypatch.setattr(credentials,'persist_user_environment',lambda name,value:captured.update(name=name,value=value) or 'windows_user_environment')
    config=tmp_path/'settings.json'
    result,code=run(parser().parse_args(['--config',str(config),'configure-api','--kind','image','--model','fixture-image']))
    assert code==0 and captured=={'name':'GEO_IMAGE_API_KEY','value':'private-image-key'}
    assert result['credential']['connected'] is True
    assert result['model']=='fixture-image'
    assert 'private-image-key' not in json.dumps(result)
    saved=json.loads(config.read_text(encoding='utf-8'))
    assert saved['image_provider']['model']=='fixture-image'
    assert saved['image_provider']['api_key_env']=='GEO_IMAGE_API_KEY'
    assert 'private-image-key' not in config.read_text(encoding='utf-8')


def test_text_credential_uses_separate_variable_and_requires_nonempty_secret(tmp_path,monkeypatch):
    from geo_article_studio import credentials
    from geo_article_studio.cli import parser,run
    captured={}
    monkeypatch.setattr(credentials,'persist_user_environment',lambda name,value:captured.update(name=name,value=value) or 'host_secure_store')
    monkeypatch.setattr(credentials.getpass,'getpass',lambda prompt:'   ')
    args=parser().parse_args(['--config',str(tmp_path/'settings.json'),'configure-api','--kind','text','--model','fixture-text'])
    with pytest.raises(ValueError,match='API Key'):run(args)
    monkeypatch.setattr(credentials.getpass,'getpass',lambda prompt:'private-text-key')
    result,code=run(args)
    assert code==0 and captured['name']=='GEO_TEXT_API_KEY'
    assert result['technical_configuration']=='pending_agent_resolution'


def test_credential_command_has_no_plaintext_key_argument():
    from geo_article_studio.cli import parser
    with pytest.raises(SystemExit):parser().parse_args(['configure-api','--kind','image','--model','x','--key','secret'])


def test_later_cli_process_hydrates_known_key_from_persistent_user_environment(monkeypatch):
    from geo_article_studio import credentials
    monkeypatch.delenv('GEO_IMAGE_API_KEY',raising=False)
    monkeypatch.setattr(credentials,'read_user_environment',lambda name:'persisted-secret' if name=='GEO_IMAGE_API_KEY' else None)
    loaded=credentials.hydrate_known_environment()
    assert loaded==['GEO_IMAGE_API_KEY']
    assert credentials.os.environ['GEO_IMAGE_API_KEY']=='persisted-secret'


def test_persisted_key_replaces_stale_inherited_value(monkeypatch):
    from geo_article_studio import credentials
    monkeypatch.setenv('GEO_IMAGE_API_KEY','stale-parent-secret')
    monkeypatch.setattr(credentials,'read_user_environment',lambda name:'rotated-secret' if name=='GEO_IMAGE_API_KEY' else None)
    loaded=credentials.hydrate_known_environment()
    assert loaded==['GEO_IMAGE_API_KEY']
    assert credentials.os.environ['GEO_IMAGE_API_KEY']=='rotated-secret'


def test_changing_model_clears_old_endpoint_and_persists_resolution_gate(tmp_path,monkeypatch):
    from geo_article_studio import credentials
    from geo_article_studio.cli import parser,run
    monkeypatch.setattr(credentials,'persist_user_environment',lambda name,value:'test_store')
    monkeypatch.setattr(credentials.getpass,'getpass',lambda prompt:'new-secret')
    config=tmp_path/'settings.json'
    config.write_text(json.dumps({'image_provider':{'adapter':'openai_compatible','base_url':'https://old.invalid/v1','model':'old-model','api_key_env':'OLD_KEY','supports_references':False},'defaults':{'image_text_policy':'none'}}),encoding='utf-8')
    result,code=run(parser().parse_args(['--config',str(config),'configure-api','--kind','image','--model','new-model']))
    saved=json.loads(config.read_text(encoding='utf-8'))
    assert code==0 and result['technical_configuration']=='pending_agent_resolution'
    assert saved['image_provider']=={'model':'new-model','api_key_env':'GEO_IMAGE_API_KEY'}
    assert saved['api_resolution']['image']['status']=='pending_agent_resolution'
    assert saved['defaults']['image_text_policy']=='none'


def test_rotating_key_for_same_model_preserves_resolved_provider_and_limit(tmp_path,monkeypatch):
    from geo_article_studio import credentials
    from geo_article_studio.cli import parser,run
    monkeypatch.setattr(credentials,'persist_user_environment',lambda name,value:'test_store')
    monkeypatch.setattr(credentials.getpass,'getpass',lambda prompt:'rotated-secret')
    config=tmp_path/'settings.json'
    provider={'adapter':'openai_chat_compatible','base_url':'https://example.invalid/v1',
              'endpoint':'/chat/completions','model':'same-model','api_key_env':'OLD_KEY',
              'protocol_document':'official-doc','max_requests_per_task':4}
    config.write_text(json.dumps({'text_provider':provider,'api_resolution':{'text':{'model':'same-model','status':'resolved_local'}}}),encoding='utf-8')
    result,code=run(parser().parse_args(['--config',str(config),'configure-api','--kind','text','--model','same-model']))
    saved=json.loads(config.read_text(encoding='utf-8'))
    assert code==0
    assert saved['text_provider']=={**provider,'api_key_env':'GEO_TEXT_API_KEY'}
    assert saved['api_resolution']['text']['status']=='resolved_local'
    assert result['technical_configuration']=='resolved_local'


def test_agent_completed_local_protocol_configuration_releases_gate(tmp_path,monkeypatch):
    from geo_article_studio.cli import parser,run
    monkeypatch.setenv('GEO_IMAGE_API_KEY','local-test-secret')
    config=tmp_path/'settings.json'
    config.write_text(json.dumps({
        'image_provider':{'model':'fixture-image','api_key_env':'GEO_IMAGE_API_KEY'},
        'api_resolution':{'image':{'model':'fixture-image','status':'pending_agent_resolution'}}
    }),encoding='utf-8')
    patch=tmp_path/'resolved.json'
    patch.write_text(json.dumps({
        'image_provider':{
            'adapter':'openai_compatible','base_url':'https://example.invalid/v1',
            'model':'fixture-image','api_key_env':'GEO_IMAGE_API_KEY',
            'supports_references':False,'max_reference_images':0,
            'output_formats':['png']
        },
        'image_protocol_verification':'official-doc:https://example.invalid/docs'
    }),encoding='utf-8')
    result,code=run(parser().parse_args(['--config',str(config),'configure','--file',str(patch)]))
    saved=json.loads(config.read_text(encoding='utf-8'))
    assert code==0
    assert saved['api_resolution']['image']['status']=='resolved_local'


def test_explicit_pending_resolution_is_not_ready():
    from geo_article_studio.config import api_resolution_ready
    assert api_resolution_ready({},'image') is True
    assert api_resolution_ready({'api_resolution':{'image':{'status':'pending_agent_resolution'}}},'image') is False
    assert api_resolution_ready({'api_resolution':{'image':{'status':'resolved_local'}}},'image') is True
