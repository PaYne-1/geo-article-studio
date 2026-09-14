import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image


def api():
    assert importlib.util.find_spec('geo_article_studio.images'), '图片模块尚未实现'
    from geo_article_studio.images import ImageProvider, ProviderError, validate_image
    return ImageProvider, ProviderError, validate_image


def png():
    out = io.BytesIO()
    Image.new('RGB', (32, 24), 'green').save(out, 'PNG')
    return out.getvalue()


@pytest.fixture
def server():
    state = {'requests': [], 'mode': 'base64'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            state['requests'].append((self.path, dict(self.headers), body))
            if state['mode'] == 'auth':
                self.send_response(401); self.end_headers(); self.wfile.write(b'secret-key'); return
            if state['mode'] == 'timeout':
                time.sleep(.3)
            payload = {'data': [{'b64_json': base64.b64encode(png()).decode()}]}
            if state['mode'] == 'url':
                payload = {'data': [{'url': state['url'] + '/redirect'}]}
            if state['mode'] == 'corrupt':
                payload = {'data': [{'b64_json': base64.b64encode(b'bad-image').decode()}]}
            raw = json.dumps(payload).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): return
        def do_GET(self):
            state['requests'].append((self.path, dict(self.headers), b''))
            if self.path == '/redirect':
                self.send_response(302); self.send_header('Location', state.get('redirect', state['url'] + '/image')); self.end_headers(); return
            raw = png()
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    state['url'] = 'http://127.0.0.1:' + str(httpd.server_port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    yield state
    httpd.shutdown(); httpd.server_close(); thread.join()


def config(server):
    return {'adapter': 'openai_compatible', 'base_url': server['url'] + '/v1',
            'model': 'fixture-model', 'api_key_env': 'GEO_TEST_KEY',
            'supports_references': True, 'max_reference_images': 2,
            'allowed_local_hosts': ['127.0.0.1'], 'timeout_seconds': 2,
            'max_response_bytes': 100000, 'max_image_bytes': 100000,
            'output_formats': ['png'], 'extra_parameters': {}}


@pytest.mark.parametrize('mode', ['base64', 'url'])
def test_real_multipart_and_decode(server, tmp_path, monkeypatch, mode):
    Provider, _, validate = api(); monkeypatch.setenv('GEO_TEST_KEY', 'secret-key')
    server['mode'] = mode
    refs = [tmp_path / '产品基准 图.png', tmp_path / '风格.png']
    for ref in refs: ref.write_bytes(png())
    p = Provider(config(server)); out = tmp_path / '实际成品.png'
    result = p.generate('仅测试', refs, out, dimensions=[32, 24], image_format='png', request_id='req-1')
    assert result['hash'] == validate(out, [32, 24], 'png')['hash']
    assert len(result['references']) == 2
    endpoint, headers, body = server['requests'][0]
    assert endpoint == '/v1/images/edits'
    assert 'multipart/form-data' in headers['Content-Type']
    assert body.count(png()) == 2
    assert b'image[]' in body
    for _, get_headers, _ in server['requests'][1:]: assert 'Authorization' not in get_headers
    assert p.check()['network_verified'] is False
    assert p.query('req-1')['supported'] is False


def test_generation_without_references(server, tmp_path, monkeypatch):
    Provider, _, _ = api(); monkeypatch.setenv('GEO_TEST_KEY', 'secret-key')
    Provider(config(server)).generate('test', [], tmp_path/'图.png', dimensions=[32,24], image_format='png', request_id='r')
    assert server['requests'][0][0] == '/v1/images/generations'
    assert json.loads(server['requests'][0][2])['size'] == '32x24'


@pytest.mark.parametrize('mode,code,unknown', [('auth','authentication_failed',False), ('timeout','request_timeout',True), ('corrupt','invalid_image',False)])
def test_failures_are_sanitized_and_never_retried(server, tmp_path, monkeypatch, mode, code, unknown):
    Provider, Error, _ = api(); monkeypatch.setenv('GEO_TEST_KEY','secret-key'); server['mode']=mode
    cfg=config(server)
    if mode == 'timeout': cfg['timeout_seconds']=.05
    with pytest.raises(Error) as caught:
        Provider(cfg).generate('test',[],tmp_path/'x.png',dimensions=[32,24],image_format='png',request_id='r')
    assert caught.value.code == code
    assert caught.value.status_unknown is unknown
    assert 'secret-key' not in str(caught.value)
    assert len(server['requests']) == 1
    assert not (tmp_path/'x.png').exists()


def test_reject_references_limits_and_private_hosts(server, tmp_path, monkeypatch):
    Provider, Error, _ = api(); monkeypatch.setenv('GEO_TEST_KEY','secret-key')
    ref=tmp_path/'ref.png'; ref.write_bytes(png())
    for overrides, refs, code in [({'supports_references':False},[ref],'references_unsupported'), ({'max_reference_images':1},[ref,ref],'too_many_references'), ({'allowed_local_hosts':[]},[],'unsafe_url'), ({},[tmp_path/'不存在.png'],'invalid_reference')]:
        cfg=config(server); cfg.update(overrides)
        with pytest.raises(Error) as caught:
            Provider(cfg).generate('test',refs,tmp_path/'x.png',dimensions=[32,24],image_format='png',request_id='r')
        assert caught.value.code == code
    assert not server['requests']


def test_response_limit_dimensions_and_encoding(server,tmp_path,monkeypatch):
    Provider, Error, validate=api(); monkeypatch.setenv('GEO_TEST_KEY','secret-key')
    cfg=config(server); cfg['max_response_bytes']=10
    with pytest.raises(Error,match='response_too_large'):
        Provider(cfg).generate('test',[],tmp_path/'x.png',dimensions=[32,24],image_format='png',request_id='r')
    path=tmp_path/'图.png'; path.write_bytes(png())
    with pytest.raises(Error,match='dimensions_mismatch'): validate(path,[31,24],'png')
    with pytest.raises(Error,match='format_mismatch'): validate(path,[32,24],'jpeg')


def test_storage_publish_and_lock(tmp_path):
    assert importlib.util.find_spec('geo_article_studio.storage'), '存储模块尚未实现'
    from geo_article_studio.storage import atomic_json, read_json, safe_name, task_lock, publish_article
    state=tmp_path/'内部'/'状态.json'; atomic_json(state,{'中文':1}); assert read_json(state)=={'中文':1}
    assert safe_name('CON') != 'CON'; assert '/' not in safe_name('中/文:*?')
    with task_lock(tmp_path/'task.lock'):
        with pytest.raises(RuntimeError):
            with task_lock(tmp_path/'task.lock'): pytest.fail('重复锁成功')
    staging=tmp_path/'内部'/'暂存'; staging.mkdir()
    (staging/'标题.txt').write_text('虚构测试标题',encoding='utf-8')
    (staging/'正文.txt').write_text('虚构测试正文\n\n第二段',encoding='utf-8')
    (staging/'配图_01.png').write_bytes(png())
    final=tmp_path/'成品'/'001_中文'
    manifest=publish_article(staging,final,1)
    assert set(p.name for p in final.iterdir())=={'标题.txt','正文.txt','配图_01.png'}
    assert manifest['files']['标题.txt']['hash']
    assert publish_article(staging,final,1)==manifest
    (staging/'正文.txt').write_text('另一篇',encoding='utf-8')
    with pytest.raises(ValueError): publish_article(staging,final,1)


def test_publish_rejects_internal_and_missing_files(tmp_path):
    api()
    from geo_article_studio.storage import publish_article
    source=tmp_path/'stage'; source.mkdir()
    (source/'标题.txt').write_text('测试',encoding='utf-8'); (source/'正文.txt').write_text('测试正文',encoding='utf-8')
    with pytest.raises(ValueError): publish_article(source,tmp_path/'out',1)
    (source/'audit.json').write_text('{}')
    with pytest.raises(ValueError): publish_article(source,tmp_path/'out',0)


@pytest.mark.parametrize('changes', [
    {'allowed_local_hosts': '127.0.0.1'},
    {'extra_parameter_allowlist':['bad\r\nname'],'extra_parameters':{'bad\r\nname':'x'}},
    {'timeout_seconds':float('inf')},
    {'idempotency_header':'Authorization'},
    {'base_url':'https://example.com?secret=key'},
])
def test_unsafe_configuration_is_reported(server,monkeypatch,changes):
    Provider,_,_=api(); monkeypatch.setenv('GEO_TEST_KEY','secret-key')
    cfg=config(server); cfg.update(changes)
    assert Provider(cfg).check()['ok'] is False


def test_output_existing_is_not_overwritten_and_format_field_optional(server,tmp_path,monkeypatch):
    Provider,Error,_=api(); monkeypatch.setenv('GEO_TEST_KEY','secret-key')
    cfg=config(server); cfg['send_response_format']=False; cfg['send_output_format']=True
    target=tmp_path/'x.png'
    p=Provider(cfg)
    p.generate('test',[],target,dimensions=[32,24],image_format='png',request_id='r')
    assert 'response_format' not in json.loads(server['requests'][0][2])
    assert json.loads(server['requests'][0][2])['output_format']=='png'
    with pytest.raises(Error,match='output_exists'):
        p.generate('test',[],target,dimensions=[32,24],image_format='png',request_id='r')
    assert len(server['requests'])==1


def test_interrupted_copy_resumes_without_touching_history(tmp_path,monkeypatch):
    api()
    from geo_article_studio import storage
    staging=tmp_path/'workspace'/'draft'; staging.mkdir(parents=True)
    (staging/'标题.txt').write_text('测试',encoding='utf-8')
    (staging/'正文.txt').write_text('正文',encoding='utf-8')
    final=tmp_path/'output'/'文章'
    real=storage.shutil.copyfileobj
    def interrupted(*args,**kwargs): raise OSError('模拟中断')
    monkeypatch.setattr(storage.shutil,'copyfileobj',interrupted)
    with pytest.raises(OSError): storage.publish_article(staging,final,0)
    assert not final.exists()
    monkeypatch.setattr(storage.shutil,'copyfileobj',real)
    manifest=storage.publish_article(staging,final,0)
    assert len(manifest['files'])==2
    assert set(p.name for p in final.iterdir())=={'标题.txt','正文.txt'}


def test_redirect_to_unapproved_private_host_is_blocked(server,tmp_path,monkeypatch):
    Provider,Error,_=api(); monkeypatch.setenv('GEO_TEST_KEY','secret-key')
    server['mode']='url'; server['redirect']='http://127.0.0.2/image'
    with pytest.raises(Error,match='unsafe_url'):
        Provider(config(server)).generate('test',[],tmp_path/'x.png',dimensions=[32,24],image_format='png',request_id='r')
    assert len(server['requests'])==2
    assert 'Authorization' not in server['requests'][1][1]


def test_process_lock_blocks_other_process(tmp_path):
    api()
    from geo_article_studio.storage import task_lock
    path=tmp_path/'跨进程锁'
    code='from geo_article_studio.storage import task_lock; import sys\nwith task_lock(sys.argv[1]):\n print("locked",flush=True)\n sys.stdin.readline()\n'
    env=dict(os.environ)
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    proc=subprocess.Popen([sys.executable,'-c',code,str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    try:
        assert proc.stdout.readline().strip()=='locked'
        with pytest.raises(RuntimeError):
            with task_lock(path): pytest.fail('第二进程获得锁')
    finally:
        proc.communicate('\n',timeout=5)
    with task_lock(path):
        assert proc.returncode==0


def test_publish_rejects_symlink_staging(tmp_path):
    api()
    from geo_article_studio.storage import publish_article
    actual=tmp_path/'actual'; actual.mkdir()
    (actual/'标题.txt').write_text('测试',encoding='utf-8'); (actual/'正文.txt').write_text('测试',encoding='utf-8')
    alias=tmp_path/'alias'
    try: alias.symlink_to(actual,target_is_directory=True)
    except OSError: pytest.skip('宿主未授权符号链接')
    with pytest.raises(ValueError,match='符号链接'): publish_article(alias,tmp_path/'output',0)


@pytest.mark.parametrize('changes',[{'api_key_env':None},{'base_url':{}},{'auth_type':[]},{'idempotency_header':{}},{'extra_parameter_allowlist':None}])
def test_malformed_config_check_returns_safe_report(server,changes):
    Provider,_,_=api()
    cfg=config(server); cfg.update(changes)
    assert Provider(cfg).check()['ok'] is False
