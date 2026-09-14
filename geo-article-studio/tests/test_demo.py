"""Executable simulation proves orchestration, not Hermes/Qwen/API integration."""
import json
from pathlib import Path

import pytest


def test_demo_two_modes_actual_indexes_http_and_exports(tmp_path):
    from geo_article_studio.demo import run_demo
    root = tmp_path / '中文 空格 离线演示'
    report = run_demo(root)
    assert report['simulation'] is True
    assert report['real_api_tested'] is False
    assert report['real_qwen_tested'] is False
    assert report['ai_visual_review_performed'] is False
    automatic = report['modes']['automatic']
    learning = report['modes']['learning']
    assert automatic['state'] == learning['state'] == 'COMPLETED'
    assert automatic['article_count'] == 3
    assert automatic['image_count'] == 8
    assert automatic['selection_calls'] == 1
    assert learning['feedback_count'] >= 1
    trace = learning['trace']
    revised = next(i for i, event in enumerate(trace) if event['operation'] == 'revise')
    assert trace[revised]['stage'] == trace[revised + 1]['stage'] == trace[revised + 3]['stage'] == 'PLANNING'
    assert trace[revised + 1]['operation'] == 'submit'
    assert trace[revised + 2]['stage'] == 'LEARNING_REVIEW'
    assert trace[revised + 2]['operation'] == 'submit'
    assert trace[revised + 3]['operation'] == 'approve'
    assert report['http']['request_count'] == 9
    assert all(request['reference_uploads'] == 2 for request in report['http']['requests'])
    assert all(request['endpoint'] == '/v1/images/edits' for request in report['http']['requests'])
    assert all(request['authorization_header_present'] is False for request in report['http']['requests'])
    for name, mode in report['modes'].items():
        output = Path(mode['output_path'])
        assert output.is_relative_to(root / 'simulation')
        articles = list(output.iterdir())
        assert len(articles) == mode['article_count']
        for article in articles:
            assert (article / '标题.txt').read_text(encoding='utf-8').strip()
            assert (article / '正文.txt').read_text(encoding='utf-8').strip()
            assert not list(article.glob('*.json'))
        assert (root / 'simulation' / name / 'workspace' / 'index.sqlite').exists()
        state = json.loads(Path(mode['state_path']).read_text(encoding='utf-8'))
        assert state['simulation'] is True
        assert state['config_snapshot']['simulation'] is True
        assert state['product']['name'] != '218轻便侠'
        assert all(ref.startswith('src_') for ref in state['sources'])
        assert state['rules_snapshot']['simulation'] is True
        assert state['rules_snapshot']['formal'] is False
        if name == 'learning':
            assert state['feedback']
            for feedback in state['feedback']:
                reflection = feedback['reflection']
                assert reflection['feedback_id'] == feedback['feedback_id']
                assert reflection['reason'] and reflection['corrective_action'] and reflection['check_method']
                assert isinstance(reflection['reason_uncertain'], bool)
                assert feedback['status'] == 'confirmed'
        from geo_article_studio.workflow import Engine
        with pytest.raises(ValueError, match='模拟|simulation'):
            Engine(state['config_snapshot'])
        from geo_article_studio.learning import RuleStore
        production_rules = RuleStore(root / 'production-rejection-check' / name)
        with pytest.raises(ValueError, match='正式'):
            production_rules.import_file(root / 'simulation' / name / 'simulation_rules.json', user_ref='real-user:test-boundary')
    assert json.loads((root / 'simulation_report.json').read_text(encoding='utf-8')) == report


def test_demo_rejects_existing_root_before_mutation(tmp_path):
    from geo_article_studio.demo import run_demo
    existing = tmp_path / '已有演示'
    existing.mkdir()
    marker = existing / '用户文件.txt'
    marker.write_text('keep', encoding='utf-8')
    with pytest.raises(ValueError, match='存在'):
        run_demo(existing)
    assert marker.read_text(encoding='utf-8') == 'keep'
    assert list(existing.iterdir()) == [marker]


def test_demo_rejects_unknown_mode_without_creation(tmp_path):
    from geo_article_studio.demo import run_demo
    root = tmp_path / '不应创建'
    with pytest.raises(ValueError, match='模式'):
        run_demo(root, 'production')
    assert not root.exists()
