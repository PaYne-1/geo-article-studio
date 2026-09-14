import subprocess
import sys
from pathlib import Path
import json

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'geo.py'

def test_cli_form_other_cwd_and_missing_config(tmp_path):
    r=subprocess.run([sys.executable,str(SCRIPT),'form','开始任务'],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stderr
    result=json.loads(r.stdout)
    assert result['values']['product']=='218轻便侠'
    assert result['values']['mode'] is None and 'mode' in result['missing']
    r=subprocess.run([sys.executable,str(SCRIPT),'doctor'],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==2
    assert 'Traceback' not in r.stderr+r.stdout

def test_cli_rejects_secret_in_config(tmp_path):
    p=tmp_path/'bad.json';p.write_text(json.dumps({'api_key':'private-secret'}))
    r=subprocess.run([sys.executable,str(SCRIPT),'--config',str(tmp_path/'settings.json'),'configure','--file',str(p)],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==2
    assert 'private-secret' not in r.stdout+r.stderr

def test_configure_partial_update_preserves_prior_values(tmp_path):
    config=tmp_path/'settings.json';first=tmp_path/'first.json';second=tmp_path/'second.json'
    first.write_text(json.dumps({'default_product_name':'虚构配置测试产品','output_root':str(tmp_path/'out')}),encoding='utf-8')
    second.write_text(json.dumps({'defaults':{'image_text_policy':'none'}}),encoding='utf-8')
    for source in (first,second):
        result=subprocess.run([sys.executable,str(SCRIPT),'--config',str(config),'configure','--file',str(source)],capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stdout
    result=json.loads(config.read_text(encoding='utf-8'))
    assert result['default_product_name']=='虚构配置测试产品'
    assert result['output_root']==str(tmp_path/'out')
