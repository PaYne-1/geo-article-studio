import copy
import pytest
from geo_article_studio.config import DEFAULT_SETTINGS
from geo_article_studio.host_bridge import route, form_for

def test_persistent_editorial_choices_prefill_start_but_keep_per_task_choices_open():
    from geo_article_studio.config import validate_settings
    from geo_article_studio.workflow import execution_config_digest
    settings=validate_settings({'task_defaults':{
        'goals':['品牌曝光','型号种草','用户转化','AI引用'],
        'platforms':['知乎','头条','搜狐','百家号','企鹅号','网易'],
        'target_ais':['DeepSeek','豆包','文心一言','元宝']}})
    form=form_for('开始任务',settings)
    assert form['values']['goals']==settings['task_defaults']['goals']
    assert form['values']['platforms']==settings['task_defaults']['platforms']
    assert form['values']['target_ais']==settings['task_defaults']['target_ais']
    assert {'mode','text_source','article_type'} <= set(form['missing'])
    assert form_for('开始任务',settings,{'goals':['AI引用']})['values']['goals']==['AI引用']
    assert execution_config_digest(settings)==execution_config_digest(validate_settings({}))

def test_task_defaults_reject_mode_and_invalid_goals():
    from geo_article_studio.config import validate_settings
    with pytest.raises(ValueError,match='task_defaults'):
        validate_settings({'task_defaults':{'mode':'automatic'}})
    with pytest.raises(ValueError,match='task_defaults'):
        validate_settings({'task_defaults':{'goals':['绝对第一']}})

def test_only_two_entrypoints_and_contextual_controls():
    assert route('开始任务')=='start'
    assert route('配置任务')=='configure_task'
    for old in ('开始学习任务','开始自动任务','配置API','配置资料库','确认','修改：更简洁','暂停任务','继续任务','查看规则','更新规则'):
        assert route(old) is None
    assert route('确认',in_task=True)=='approve'
    assert route('修改：更简洁',in_task=True)=='revise'
    assert route('继续任务',in_task=True)=='resume'
    assert route('确认',in_task=True,origin='source') is None
    assert route('配置任务',origin='source') is None

def test_start_uses_correct_product_and_asks_mode():
    assert DEFAULT_SETTINGS['default_product_name']=='218轻便侠'
    form=form_for('开始任务',copy.deepcopy(DEFAULT_SETTINGS))
    assert form['values']['product']=='218轻便侠'
    assert form['values']['mode'] is None and 'mode' in form['missing']
    assert form['choices']['mode']==['learning','automatic']

def test_full_current_message_candidate_lists_are_explicit_all_selections_without_followup():
    from geo_article_studio.editorial import GOALS, PLATFORMS, TARGET_AIS
    form=form_for('开始任务',copy.deepcopy(DEFAULT_SETTINGS),{
        'mode':'automatic', 'text_source':'host', 'image_review_policy':'direct_use',
        'goals':copy.deepcopy(GOALS), 'platforms':copy.deepcopy(PLATFORMS),
        'target_ais':copy.deepcopy(TARGET_AIS), 'article_type':'short'})
    assert form['missing']==[]
    policy=form['selection_interpretation']
    assert policy['full_list_is_explicit_selection'] is True
    assert policy['followup_required_when']=='only_partial_missing_or_unknown'
    assert policy['canonical_candidates']=={'goals':GOALS,'platforms':PLATFORMS,'target_ais':TARGET_AIS}

def test_configuration_includes_api_and_libraries_in_one_form(monkeypatch):
    monkeypatch.delenv('GEO_IMAGE_API_KEY',raising=False)
    monkeypatch.delenv('GEO_TEXT_API_KEY',raising=False)
    form=form_for('配置任务',copy.deepcopy(DEFAULT_SETTINGS))
    assert form['action']=='configure_task'
    for key in ('chat','product_info','reference_images','product_images','output_root'):
        assert key in form['missing']
    assert form['conditional_missing']['with_images']==['model','image_api_key']
    assert form['values']['api_key_env']=='GEO_IMAGE_API_KEY'
    assert 'api_key' not in form['values']
    assert any(s['id']=='image_api' for s in form['sections'])
    assert '本地' in form['credential_notice']

def test_configuration_prefills_false_capability_and_updates_only_missing():
    settings=copy.deepcopy(DEFAULT_SETTINGS)
    settings['image_provider']={'adapter':'openai_compatible','base_url':'https://example.invalid/v1','model':'configured-model','api_key_env':'MY_IMAGE_KEY','supports_references':False}
    settings['image_protocol_verification']='local:vendor-doc'
    form=form_for('配置任务',settings,{'max_requests':5})
    assert form['values']['model']=='configured-model'
    assert form['values']['api_key_env']=='MY_IMAGE_KEY'
    assert form['values']['supports_references'] is False
    assert 'supports_references' not in form['missing']
    assert 'base_url' not in form['missing'] and 'max_requests' not in form['missing']
    assert settings['limits']['max_image_requests_per_task'] is None

def test_form_rejects_removed_entry_and_secret_input():
    with pytest.raises(ValueError):form_for('配置API',{})
    with pytest.raises(ValueError):form_for('配置任务',{}, {'api_key':'private-value'})

def test_explicit_existing_product_is_not_silently_rewritten():
    assert form_for('开始任务',{'default_product_name':'实际已登记产品'})['values']['product']=='实际已登记产品'
