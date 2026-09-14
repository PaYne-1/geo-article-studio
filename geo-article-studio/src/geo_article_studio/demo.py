"""Explicit, isolated offline simulation. Never used as the production model bridge.

All user decisions, writing and visual verdicts in this module are test fixtures.
The local HTTP service returns Pillow fixtures, not AI-generated product images.
"""
from __future__ import annotations

import base64
import io
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from .config import validate_settings
from .libraries import LibraryIndex
from .products import ProductRegistry
from .review import REVIEW_CHECKS
from .storage import atomic_json
from .workflow import Engine

PRODUCT_ID = 'fictional-simulation-product'
PRODUCT_NAME = '虚构离线演示产品'
SIMULATION_REF = 'simulation:scripted-user-not-a-real-user-approval'


def _fixture_png(color):
    stream = io.BytesIO()
    Image.new('RGB', (64, 64), color).save(stream, format='PNG')
    return stream.getvalue()


@contextmanager
def _local_image_service(reference_bytes):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            references = sum(body.count(value) for value in reference_bytes)
            requests.append({'simulation': True, 'endpoint': self.path,
                             'reference_uploads': references,
                             'multipart': 'multipart/form-data' in self.headers.get('Content-Type', ''),
                             'authorization_header_present': bool(self.headers.get('Authorization'))})
            if self.path != '/v1/images/edits' or references != 2:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"simulation_requires_two_uploaded_references"}')
                return
            color = (32 + len(requests) * 10, 100, 140)
            result = json.dumps({'data': [{'b64_json': base64.b64encode(_fixture_png(color)).decode('ascii')}]}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            self.wfile.write(result)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {'base_url': f'http://127.0.0.1:{server.server_port}/v1', 'requests': requests}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _setup(root, mode, service, references):
    root.mkdir(parents=True)
    libraries = {}
    for kind in ('chat', 'product_info', 'reference_images', 'product_images'):
        library = root / 'sources' / kind
        library.mkdir(parents=True)
        libraries[kind] = str(library)
    chats = [
        {'role': 'customer', 'conversation_id': 'simulation-session-a', 'date': '2026-01-01',
         'text': '虚构测试咨询：出门之前怎样记录通道和转弯空间？'},
        {'role': 'customer', 'conversation_id': 'simulation-session-b', 'date': '2026-01-02',
         'text': '虚构测试咨询：怎样整理需要向商家确认的问题？'},
        {'role': 'service', 'conversation_id': 'simulation-session-b',
         'text': '虚构测试客服回复，不作为客户诉求统计。'},
    ]
    (Path(libraries['chat']) / 'fictional-chat.jsonl').write_text(
        '\n'.join(json.dumps(row, ensure_ascii=False) for row in chats), encoding='utf-8')
    (Path(libraries['product_info']) / 'fictional-info.txt').write_text(
        '这是虚构离线演示资料。没有任何真实产品参数，也没有已批准的性能主张。', encoding='utf-8')
    for kind, name, raw in [('product_images', 'fictional-product.png', references[0]),
                            ('reference_images', 'fictional-style.png', references[1])]:
        path = Path(libraries[kind]) / name
        path.write_bytes(raw)
        path.with_suffix('.json').write_text(json.dumps({
            'simulation': True, 'description': 'Pillow测试色块，非真实产品照片，非AI成品',
            'approved': True, 'status': 'approved', 'external_use_approved': True,
            'version': 'fictional-v1', 'immutable': ['仅保留虚构色块形状'],
            'borrow': ['光线'], 'forbidden': ['Logo', '旧产品参数'],
        }, ensure_ascii=False), encoding='utf-8')
    mappings = {'chat/fictional-chat.jsonl': PRODUCT_ID,
                'product_info/fictional-info.txt': PRODUCT_ID,
                'product_images/fictional-product.png': PRODUCT_ID,
                'reference_images/fictional-style.png': PRODUCT_ID}
    settings = validate_settings({
        'simulation': True, 'simulation_notice': 'Offline fixtures only; no real user/Qwen/visual/API approval.',
        'default_product_name': PRODUCT_NAME, 'libraries': libraries,
        'workspace_root': str(root / 'workspace'), 'output_root': str(root / 'simulation_outputs'),
        'products': [{'product_id': PRODUCT_ID, 'name': PRODUCT_NAME, 'version': 'fictional-v1',
                      'source_ids': [], 'image_source_ids': []}],
        'source_mappings': mappings,
        'defaults': {'article_length': {'min': 30, 'max': 1000}, 'image_ratio': '1:1',
                     'image_dimensions': [64, 64], 'image_format': 'png', 'image_text_policy': 'none'},
        'limits': {'max_image_requests_per_task': 8 if mode == 'automatic' else 1},
        'host': {'visual_capability': True, 'visual_verification_ref': 'offline-simulated',
                 'simulation': True, 'ai_visual_review_performed': False},
        'image_provider': {'adapter': 'openai_compatible', 'base_url': service['base_url'],
                           'model': 'offline-pillow-fixture', 'auth_type': 'none', 'api_key_env': 'GEO_SIMULATION_UNUSED_KEY',
                           'supports_references': True, 'max_reference_images': 4,
                           'allowed_local_hosts': ['127.0.0.1'], 'timeout_seconds': 5,
                           'max_response_bytes': 1000000, 'max_image_bytes': 1000000,
                           'output_formats': ['png'], 'extra_parameters': {}},
    })
    index = LibraryIndex(settings)
    coverage = index.update()
    settings['image_authorizations'] = {
        row['source_id']: {'user_ref': SIMULATION_REF, 'external_use_approved': True,
                           'hash': row['hash'],
                           'product_id': PRODUCT_ID, 'version': 'fictional-v1',
                           'allow_borrow': ['光线'], 'immutable': ['仅保留虚构色块形状'],
                           'simulation': True}
        for library in ('product_images', 'reference_images')
        for row in index.search('', library_type=library, product_id=PRODUCT_ID, is_image=True)
    }
    atomic_json(root / 'simulation_settings.json', settings)
    index = LibraryIndex(settings)
    products = ProductRegistry(settings, index)
    engine = Engine(settings, index=index, products=products, simulation=True)
    rules = root / 'simulation_rules.json'
    atomic_json(rules, {'formal': False, 'test_only': True, 'simulation': True, 'version': 'offline-fixture-v1',
                        'notice': '仅用于隔离测试，不是用户正式禁限规则',
                        'rules': [{'rule_id': 'SIM_ONLY', 'scope': 'global', 'target_id': None,
                                   'type': 'hard_ban', 'content': '虚构测试禁限项，不替代生产规则',
                                   'terms': ['模拟禁用承诺'], 'severity': 'hard',
                                   'check_method': '本地测试断言；不代表语义审核'}]})
    engine.rules.import_file(rules, user_ref=SIMULATION_REF)
    return engine, coverage


def _simulated_result(action):
    """Strict-schema fixture output. Never exported as a production model adapter."""
    stage, context = action['stage'], action['context']
    sources = context['sources']
    chats = [row for row in sources if row['library_type'] == 'chat' and row['metadata']['role'] == 'customer']
    article = context['article']
    if stage == 'LEARNING_REVIEW':
        feedback = next(item for item in context['feedback']
                        if item['status'] == 'revised_waiting_approval' and not item.get('reflection'))
        return {'feedback_id': feedback['feedback_id'],
                'reason': 'OFFLINE SIMULATION：旧策划先概述现场，未优先呈现具体咨询问题；此因果解释仅为复盘测试夹具。',
                'reason_uncertain': True,
                'corrective_action': '本篇提纲已改为先写具体问题，再整理需要核实的信息，等待模拟人工批准。',
                'check_method': '对照当前文章提纲、用户反馈和旧版本，确认仅当前文章适用，并验证复盘持久化。'}
    if stage == 'PREFLIGHT':
        return {'understanding': '离线模拟：只有虚构咨询和测试色块，不存在真实产品事实。',
                'source_ids': [row['source_id'] for row in chats], 'gaps': []}
    if stage == 'ANALYZING':
        directions = [
            ('T01', '出门前的空间记录', ['通道记录方法', '转弯观察要点'], chats[0]),
            ('T03', '咨询前的信息整理', ['商家问题清单'], chats[1]),
        ]
        return {'topics': [{'topic_id': tid, 'direction': direction,
                            'question_summary': source['snippet'], 'source_ids': [source['source_id']],
                            'scope': 'product_specific', 'count_basis': 'conversation', 'verified_count': 1,
                            'supporting_fact_ids': [], 'distinct_angles': angles, 'gaps': [], 'status': 'ready',
                            'priority_reason': '离线虚构咨询仅检验流程，不代表真实需求频率。'}
                           for tid, direction, angles, source in directions],
                'coverage_note': '全部为虚构片段；按明确会话标识计数，不统计客户数或市场比例。'}
    if stage == 'PLANNING':
        revised = bool(context.get('feedback'))
        return {'angle': article['angle'], 'question': '怎样整理待核对的实际环境信息？',
                'outline': ['先写具体问题' if revised else '记录现场情况', '整理待核实的信息'],
                'fact_ids': [], 'source_ids': [chats[0]['source_id']]}
    if stage == 'WRITING':
        bodies = {
            '通道记录方法': ('出门前先记录通道情况', '可以先记录路线上的狭窄位置、门口和沿途障碍，把不清楚的地方列成问题。记录应以现场观察为依据，保留测量条件。\n\n随后将这些信息提供给商家，请对方依据实际资料说明适配条件。信息不足时继续核实，不预先承诺能否通行。'),
            '转弯观察要点': ('把转弯位置单独记下来', '观察路线时，可以把拐角位置和周围物品分开记录。描述空间形状、障碍摆放与观察角度，有助于说明具体疑问。\n\n咨询时说明现场条件仍待核实，并请商家指出需要补充的资料。不要把平面印象直接当作通行结论。'),
            '商家问题清单': ('咨询前怎样整理问题', '整理咨询内容时，先区分已经确认的信息与尚不清楚的条件。把想解决的问题逐项写清，并注明需要对方提供哪类依据。\n\n收到回复后，可以核对回答是否对应原问题、是否说明限制。对没有材料支持的表述继续追问，暂不形成产品性能判断。'),
        }
        title, body = bodies[article['angle']]
        return {'title': title, 'body': body, 'claims': []}
    if stage == 'IMAGE_PLANNING':
        product = next(row['source_id'] for row in sources if row['library_type'] == 'product_images' and row['metadata'].get('is_image'))
        reference = next(row['source_id'] for row in sources if row['library_type'] == 'reference_images' and row['metadata'].get('is_image'))
        return {'images': [{'image_id': f'{article["article_id"]}_I{i:02d}', 'article_id': article['article_id'],
                            'paragraph': 1 if i % 2 else 2, 'purpose': '离线检验正文段落与配图计划绑定',
                            'scene': '虚构测试色块画面', 'people_actions': '', 'show_product': True,
                            'product_image_ids': [product], 'reference_image_ids': [reference],
                            'borrow': ['光线'], 'immutable': ['仅保留虚构色块形状'], 'allowed_text': '',
                            'prompt': 'OFFLINE SIMULATION ONLY: Pillow fixture for multipart integration testing; no real product depiction.',
                            'fact_ids': []} for i in range(1, article['image_count'] + 1)]}
    if stage in REVIEW_CHECKS:
        viewed = list(article['images']) if stage != 'TEXT_REVIEW' else []
        return {'verdict': 'passed', 'reviewer': 'qwen',
                'checks': [{'check_id': check, 'verdict': 'passed', 'severity': 'info',
                            'evidence': 'OFFLINE SIMULATION：脚本测试判定，仅检验契约与文件；未调用Qwen，未执行AI视觉审核。',
                            'suggestion': ''} for check in REVIEW_CHECKS[stage]],
                'viewed_image_ids': viewed}
    raise ValueError('离线演示尚不支持此流程动作：' + stage)


def _run_mode(root, mode, service, references):
    engine, coverage = _setup(root, mode, service, references)
    task = engine.start(PRODUCT_ID, mode, user_ref=SIMULATION_REF,
                        extra_requirements='OFFLINE SIMULATION：全部素材、用户交互、模型结果及图像审核均为测试夹具。')
    task_id = task['task_id']
    trace, revised, selection_calls = [], False, 0
    for _ in range(200):
        action = engine.next_action(task_id)
        kind, stage = action['kind'], action['stage']
        event = {'simulation': True, 'stage': stage, 'revision': action['expected_revision']}
        if kind == 'FINISHED':
            state = engine.status(task_id)
            return {'simulation': True, 'state': state['state'], 'task_id': task_id,
                    'article_count': len(state['articles']), 'image_count': sum(len(a['images']) for a in state['articles']),
                    'selection_calls': selection_calls, 'feedback_count': len(state['feedback']),
                    'output_path': state['output_path'], 'state_path': str(engine._path(task_id) / 'state.json'),
                    'coverage': coverage, 'trace': trace}
        if kind == 'NEEDS_MODEL':
            trace.append(dict(event, operation='submit'))
            engine.submit(task_id, action['action_id'], action['expected_revision'], _simulated_result(action))
        elif kind == 'NEEDS_USER' and stage == 'WAITING_SELECTION':
            selection = ([{'topic_id': 'T01', 'article_count': 2, 'image_counts': [3, 3]},
                          {'topic_id': 'T03', 'article_count': 1, 'image_counts': [2]}]
                         if mode == 'automatic' else [{'topic_id': 'T01', 'article_count': 1, 'image_counts': [1]}])
            engine.select(task_id, selection, user_ref=SIMULATION_REF)
            selection_calls += 1
            trace.append(dict(event, operation='select'))
        elif kind == 'NEEDS_USER' and action['approval_required']:
            if mode == 'learning' and stage == 'PLANNING' and not revised:
                engine.revise(task_id, action['action_id'], action['expected_revision'],
                              '这篇先写具体问题，再整理需要核实的信息。', user_ref=SIMULATION_REF, scope='article')
                revised = True
                trace.append(dict(event, operation='revise'))
            else:
                engine.approve(task_id, action['action_id'], action['expected_revision'], user_ref=SIMULATION_REF)
                trace.append(dict(event, operation='approve'))
        elif kind == 'NEEDS_TOOL':
            if action['tool'] == 'run-image':
                engine.run_image(task_id)
            elif action['tool'] == 'export':
                engine.export(task_id)
            else:
                raise ValueError('未知演示工具动作')
            trace.append(dict(event, operation=action['tool']))
        else:
            raise ValueError(f'离线模拟未完成：{kind}/{stage}；{action.get("error") or "动作不可执行"}')
    raise ValueError('离线模拟超过状态转换上限，未完成')


def run_demo(root: Path, mode='both') -> dict:
    """Create a fresh isolated fixture tree and run real engine/HTTP/file operations."""
    if mode not in ('both', 'learning', 'automatic'):
        raise ValueError('演示模式必须为 both、learning 或 automatic')
    root = Path(root).expanduser()
    if root.exists() or root.is_symlink():
        raise ValueError('演示根目录已存在，拒绝覆盖；请指定新的隔离目录')
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / 'SIMULATION_ONLY.txt').write_text(
        '此目录全部为离线模拟：虚构资料、脚本模拟用户和模型、Pillow图片夹具。\n'
        '不是真实产品内容，不是Qwen生成，不是AI视觉审核，不是第三方付费API联调。\n', encoding='utf-8')
    references = [_fixture_png((10, 100, 10)), _fixture_png((10, 10, 100))]
    modes = ('learning', 'automatic') if mode == 'both' else (mode,)
    with _local_image_service(references) as service:
        results = {name: _run_mode(root / 'simulation' / name, name, service, references) for name in modes}
        report = {'simulation': True, 'root': str(root), 'product_name': PRODUCT_NAME,
                  'real_api_tested': False, 'real_qwen_tested': False, 'hermes_tested': False,
                  'ai_visual_review_performed': False, 'user_decisions': 'scripted_fixture_not_real_approval',
                  'images': 'Pillow fixtures, not real generated deliverables',
                  'modes': results, 'http': {'simulation': True, 'request_count': len(service['requests']),
                                           'requests': service['requests']}}
    atomic_json(root / 'simulation_report.json', report)
    return report
