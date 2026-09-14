"""Product registry and source-bound facts; only explicit user decisions approve facts.

The actor flag is a host trust boundary, not identity authentication. The host must
only pass actor='user' for the current real user input, never for model/library text.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path

from .config import validate_settings
from .libraries import LibraryIndex, redact
from .storage import task_lock


def _locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with task_lock(self.path.with_suffix('.lock')):
            return method(self, *args, **kwargs)
    return wrapped


class ProductRegistry:
    def __init__(self, settings, index=None):
        self.settings = validate_settings(settings)
        self.index = index or LibraryIndex(self.settings)
        self.path = Path(self.settings['workspace_root']) / 'products.json'
        if self.path.is_symlink():
            raise ValueError('产品状态不能为符号链接')
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self):
        if not self.path.exists():
            return {'schema_version': '1.0', 'facts': []}
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('产品事实状态损坏，禁止自动覆盖') from exc

    def _save(self, state):
        descriptor, temporary = tempfile.mkstemp(prefix='.products-', suffix='.json', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            if self._read() != state:
                raise ValueError('事实写入回读校验失败')
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def list_products(self):
        return json.loads(json.dumps(self.settings['products'], ensure_ascii=False))

    def get(self, product_id):
        for product in self.list_products():
            if product['product_id'] == product_id:
                return product
        raise ValueError('产品未注册或缺少资料，不会自动选择其他产品：' + str(product_id))

    def _valid_source(self, source_id, product_id):
        source = self.index.get(source_id)
        if source['library_type'] != 'product_info' or source['product_id'] != product_id:
            raise ValueError('事实必须引用所选产品的有效产品资料，不得使用聊天或其他产品')
        return source

    def extract_candidates(self, product_id):
        """Extract explicit label:value lines; never infer absent product properties."""
        self.get(product_id)
        candidates = []
        # Chunked corpus enumeration is local. No source text is uploaded here.
        with self.index._connect() as db:
            rows = db.execute("SELECT * FROM sources WHERE library_type='product_info' AND product_id=?", (product_id,)).fetchall()
        for raw in rows:
            source = self.index._row(raw)
            for line in source['snippet'].splitlines():
                match = re.match(r'^\s*(?:[-*#]\s*)?([^:：\n]{1,80})\s*[:：]\s*(\S.{0,1999})$', line)
                if match:
                    candidates.append({'field': match.group(1).strip(), 'value': match.group(2).strip(),
                                       'source_id': source['source_id'], 'quote': line.strip()})
        return self.add_candidates(product_id, candidates)

    @_locked
    def add_candidates(self, product_id, candidates):
        """Accept model-proposed candidates only as pending and with literal evidence."""
        product = self.get(product_id)
        if not isinstance(candidates, list):
            raise ValueError('候选事实必须为列表')
        state = self._read()
        for candidate in candidates:
            if not isinstance(candidate, dict) or any(not isinstance(candidate.get(k), str) or not candidate[k].strip()
                                                      for k in ('field', 'value', 'source_id', 'quote')):
                raise ValueError('候选须含 field/value/source_id/quote')
            if candidate.get('status', 'pending') != 'pending' or candidate.get('approval'):
                raise ValueError('模型不得自行批准候选事实')
            source = self._valid_source(candidate['source_id'], product_id)
            quote = candidate['quote'].strip()
            if quote not in source['snippet'] or candidate['value'].strip() not in quote:
                raise ValueError('候选必须有真实原文摘录，不能凭空生成参数')
            field, value = redact(candidate['field'].strip()), redact(candidate['value'].strip())
            identifier = 'fact_' + hashlib.sha256(f'{product_id}\0{product["version"]}\0{field}\0{value}\0{source["source_id"]}'.encode()).hexdigest()[:24]
            if any(f['fact_id'] == identifier for f in state['facts']):
                continue
            state['facts'].append({'fact_id': identifier, 'product_id': product_id, 'version': product['version'],
                                   'field': field, 'value': value, 'claim': field + '：' + value, 'text': field + '：' + value,
                                   'source_ids': [source['source_id']], 'source_hashes': {source['source_id']: source['hash']},
                                   'quote': redact(quote), 'status': 'pending', 'approval': None,
                                   'created_at': datetime.now(timezone.utc).isoformat()})
        self._invalidate(state)
        current = [f for f in state['facts'] if f['product_id'] == product_id and f['version'] == product['version'] and f['status'] != 'stale']
        for fact in current:
            if fact['status'] == 'rejected':
                continue
            conflicts = [other for other in current if other['field'] == fact['field'] and other['value'] != fact['value'] and other['status'] != 'rejected']
            if conflicts:
                fact['status'] = 'conflict'
                fact['approval'] = None
                fact['conflicting_source_ids'] = sorted(set(fact['source_ids'] + [sid for other in conflicts for sid in other['source_ids']]))
        self._save(state)
        return [f for f in state['facts'] if f['product_id'] == product_id and f['status'] != 'stale']

    def _invalidate(self, state):
        for fact in state['facts']:
            try:
                product = self.get(fact['product_id'])
                if product['version'] != fact['version']:
                    raise ValueError('version_changed')
                for sid, digest in fact['source_hashes'].items():
                    if self._valid_source(sid, fact['product_id'])['hash'] != digest:
                        raise ValueError('source_changed')
            except ValueError:
                if fact['status'] != 'stale':
                    fact['previous_status'] = fact['status']
                    fact['status'] = 'stale'
                    fact['approval'] = None

    @_locked
    def facts(self, product_id, approved_only=False):
        self.get(product_id)
        state = self._read()
        before = json.dumps(state, sort_keys=True)
        self._invalidate(state)
        if before != json.dumps(state, sort_keys=True):
            self._save(state)
        return [f for f in state['facts'] if f['product_id'] == product_id and
                (f['status'] == 'approved' if approved_only else True)]

    @_locked
    def approve(self, fact_id, user_input, actor='user'):
        """Approve one shown fact ID; host must bind this call to real user input."""
        if actor != 'user' or not isinstance(user_input, str) or user_input.strip() not in ('确认', '确认下一步', '批准', '同意'):
            raise ValueError('必须由当前用户明确确认指定事实；模型与资料文本不可批准')
        state = self._read()
        self._invalidate(state)
        fact = next((f for f in state['facts'] if f['fact_id'] == fact_id), None)
        if fact is None or fact['status'] not in ('pending', 'approved'):
            raise ValueError('事实不存在、来源失效或存在冲突，不能批准')
        fact['status'] = 'approved'
        fact['approval'] = {'actor': 'user', 'user_input': user_input.strip(), 'fact_id': fact_id,
                            'version': fact['version'], 'source_hashes': fact['source_hashes'].copy(),
                            'confirmed_at': datetime.now(timezone.utc).isoformat(),
                            'identity_boundary': 'host_current_user_input; not cryptographic authentication'}
        self._save(state)
        return fact

    @_locked
    def resolve_conflict(self, fact_id, user_input, rejected_fact_ids, actor='user'):
        """User selects one shown candidate and explicitly rejects every conflicting one."""
        if actor != 'user' or not isinstance(user_input, str) or user_input.strip() not in ('确认', '确认下一步', '批准', '同意'):
            raise ValueError('冲突处理须来自当前用户对指定事实的明确确认')
        if not isinstance(rejected_fact_ids, list) or not rejected_fact_ids or not all(isinstance(v, str) for v in rejected_fact_ids):
            raise ValueError('必须明确列出被拒绝的竞争事实 ID')
        state = self._read()
        self._invalidate(state)
        chosen = next((f for f in state['facts'] if f['fact_id'] == fact_id), None)
        if chosen is None or chosen['status'] != 'conflict':
            raise ValueError('指定事实不处于有效冲突状态')
        competing = [f for f in state['facts'] if f['product_id'] == chosen['product_id'] and
                     f['version'] == chosen['version'] and f['field'] == chosen['field'] and
                     f['value'] != chosen['value'] and f['status'] not in ('rejected', 'stale')]
        if set(rejected_fact_ids) != {f['fact_id'] for f in competing} or len(set(rejected_fact_ids)) != len(rejected_fact_ids):
            raise ValueError('必须逐项明确拒绝全部竞争事实，不能拒绝无关对象')
        decision = {'actor': 'user', 'user_input': user_input.strip(), 'fact_id': fact_id,
                    'version': chosen['version'], 'source_hashes': chosen['source_hashes'].copy(),
                    'rejected_fact_ids': rejected_fact_ids.copy(),
                    'rejected_evidence': [{'fact_id': f['fact_id'], 'claim': f['claim'],
                                          'source_ids': f['source_ids'], 'source_hashes': f['source_hashes']}
                                         for f in competing],
                    'confirmed_at': datetime.now(timezone.utc).isoformat(),
                    'identity_boundary': 'host_current_user_input; not cryptographic authentication'}
        for fact in competing:
            fact['status'] = 'rejected'
            fact['approval'] = None
            fact['rejection'] = decision.copy()
        chosen['status'] = 'approved'
        chosen['approval'] = decision
        chosen.pop('conflicting_source_ids', None)
        # Same-value records are no longer in conflict, but need their own user approval.
        for fact in state['facts']:
            if fact['fact_id'] != fact_id and fact['product_id'] == chosen['product_id'] and fact['version'] == chosen['version'] and fact['field'] == chosen['field'] and fact['value'] == chosen['value'] and fact['status'] == 'conflict':
                fact['status'] = 'pending'
                fact.pop('conflicting_source_ids', None)
        self._save(state)
        return chosen
