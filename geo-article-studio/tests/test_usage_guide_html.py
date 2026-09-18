from pathlib import Path


def test_html_usage_guide_covers_install_configuration_and_task_continuation():
    guide=Path(__file__).parents[1] / 'docs' / '技能包使用方法明细.html'
    assert guide.is_file()
    content=guide.read_text(encoding='utf-8')
    for text in ('GEO图文生产助手', '安装与升级', '配置任务', '开始任务',
                 '选择 T01，写1篇，每篇2张', '继续任务＋任务编号',
                 '不审核 直接用', '成品目录'):
        assert text in content
