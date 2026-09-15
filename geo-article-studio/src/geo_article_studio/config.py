"""Non-secret configuration and actual-runtime path validation."""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

LIBRARY_TYPES = ('chat', 'product_info', 'reference_images', 'product_images')
DEFAULT_SETTINGS = {
    'schema_version': '1.0', 'default_product_name': '218轻便侠',
    'libraries': dict.fromkeys(LIBRARY_TYPES), 'output_root': None,
    'workspace_root': None, 'user_path_mapping': None, 'rule_import_sources': [],
    'products': [], 'source_mappings': {},
    'defaults': {'language': 'zh-CN', 'mode': None, 'article_length': None,
                 'image_ratio': '3:4', 'image_dimensions': None, 'image_format': 'png',
                 'image_text_policy': 'auto', 'image_count_includes_cover': True},
    'limits': {'max_generation_attempts_per_image': 3, 'max_text_revision_attempts': 3,
               'max_parallel_image_requests': 1, 'max_image_requests_per_task': None,
               'max_cost': None, 'currency': None},
}

def api_resolution_ready(settings,kind):
    """Legacy configurations stay valid; an explicit pending model switch blocks use."""
    record=(settings.get('api_resolution') or {}).get(kind)
    return not record or record.get('status')=='resolved_local'


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _check_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key != 'image_authorizations' and re.search(r'(api[_-]?key|secret|password|access[_-]?token|authorization)', key, re.I):
                if not re.search(r'(env|environment)(?:_name)?$', key, re.I):
                    if item not in (None, ''):
                        raise ValueError('普通配置禁止保存密钥；仅保存凭据环境变量名称')
                elif item is not None and (not isinstance(item, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', item)):
                    raise ValueError('凭据环境变量名称无效')
            _check_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _check_secrets(item)
    elif isinstance(value, str) and (re.search(r'\b(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+\S+)', value)
                                   or re.search(r'https?://[^/\s]+:[^/\s]+@', value)):
        raise ValueError('普通配置疑似含凭据，禁止保存')


def _mapped_path(value, mapping):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('路径必须是非空绝对路径')
    if mapping:
        if not isinstance(mapping, dict):
            raise ValueError('user_path_mapping 必须为用户路径到实际运行路径的对象')
        for source, target in sorted(mapping.items(), key=lambda p: -len(p[0])):
            if value == source:
                value = target
                break
            separator = '\\' if '\\' in source else '/'
            if value.startswith(source.rstrip('/\\') + separator):
                suffix = value[len(source.rstrip('/\\')) + 1:]
                value = str(Path(target).joinpath(*re.split(r'[/\\]', suffix)))
                break
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('路径必须在实际运行环境中可读；跨主机路径请配置显式 user_path_mapping')
    return path.resolve()


def paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def validate_settings(data: dict, production: bool = False) -> dict:
    """Return a deep merged, validated copy; incomplete setup is legal outside production.

    Production checks configuration completeness, not semantic rule/API approval.
    Those authorizations are independently checked by the workflow.
    """
    if not isinstance(data, dict):
        raise ValueError('配置必须为 JSON 对象')
    _check_secrets(data)
    settings = _merge(copy.deepcopy(DEFAULT_SETTINGS), data)
    if settings.get('text_provider') is not None and not isinstance(settings['text_provider'],dict):
        raise ValueError('文字API配置text_provider必须为对象')
    if not isinstance(settings['libraries'], dict):
        raise ValueError('libraries 必须为对象')
    unknown = set(settings['libraries']) - set(LIBRARY_TYPES)
    if unknown:
        raise ValueError('未知资料库类型')
    resolved = {}
    for kind in LIBRARY_TYPES:
        raw = settings['libraries'].get(kind)
        if raw is None:
            continue
        path = _mapped_path(raw, settings['user_path_mapping'])
        if not path.is_dir() or not os.access(path, os.R_OK):
            raise ValueError(f'{kind} 资料库路径不可读：{path}')
        if any(paths_overlap(path, existing) for existing in resolved.values()):
            raise ValueError('四库逻辑根目录必须独立，不能相同或嵌套')
        resolved[kind] = path
        settings['libraries'][kind] = str(path)
    for field in ('workspace_root', 'output_root'):
        if settings[field] is not None:
            path = _mapped_path(settings[field], settings['user_path_mapping'])
            if any(paths_overlap(path, source) for source in resolved.values()):
                raise ValueError('工作目录与成品目录必须与源库隔离')
            if path.exists() and not path.is_dir():
                raise ValueError(f'{field} 必须为目录')
            ancestor = path
            while not ancestor.exists():
                ancestor = ancestor.parent
            if not os.access(ancestor, os.W_OK):
                raise ValueError(f'{field} 不可写')
            settings[field] = str(path)
    if settings['workspace_root'] and settings['output_root'] and paths_overlap(
            Path(settings['workspace_root']), Path(settings['output_root'])):
        raise ValueError('工作目录与成品目录必须独立')
    products = settings.get('products')
    if not isinstance(products, list):
        raise ValueError('products 必须为列表')
    ids = set()
    for product in products:
        if not isinstance(product, dict) or not all(isinstance(product.get(k), str) and product[k].strip()
                                                   for k in ('product_id', 'name', 'version')):
            raise ValueError('产品须有明确 product_id/name/version')
        if product['product_id'] in ids or product['product_id'] == 'general':
            raise ValueError('产品 ID 重复或为保留值 general')
        ids.add(product['product_id'])
        for key in ('source_ids', 'image_source_ids'):
            product.setdefault(key, [])
            if not isinstance(product[key], list) or not all(isinstance(v, str) for v in product[key]):
                raise ValueError(f'{key} 必须为来源 ID 列表')
    if not isinstance(settings['source_mappings'], dict):
        raise ValueError('source_mappings 必须为对象')
    for source, product_id in settings['source_mappings'].items():
        parts = source.replace('\\', '/').split('/')
        if len(parts) < 2 or parts[0] not in LIBRARY_TYPES or any(p in ('', '.', '..') for p in parts):
            raise ValueError('来源映射必须使用 资料库类型/相对文件 且不能越界')
        if product_id not in ids:
            raise ValueError('来源映射指向未注册产品')
    limits = settings['limits']
    for key in ('max_generation_attempts_per_image', 'max_text_revision_attempts', 'max_parallel_image_requests'):
        if type(limits.get(key)) is not int or limits[key] < 1:
            raise ValueError(f'{key} 必须为正整数，次数包含首次')
    image_cap=limits.get('max_image_requests_per_task')
    if image_cap is not None and (type(image_cap) is not int or image_cap<1):
        raise ValueError('max_image_requests_per_task 必须为空或正整数')
    if production:
        missing = [f'libraries.{k}' for k in LIBRARY_TYPES if settings['libraries'][k] is None]
        missing += [k for k in ('workspace_root', 'output_root') if settings[k] is None]
        missing += [f'defaults.{k}' for k in ('article_length', 'image_ratio', 'image_dimensions', 'image_text_policy')
                    if settings['defaults'].get(k) is None]
        if missing:
            raise ValueError('缺少生产配置：' + '、'.join(missing))
    return settings


def load_settings(path) -> dict:
    try:
        with Path(path).open('r', encoding='utf-8-sig') as handle:
            return validate_settings(json.load(handle))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError('配置读取失败，请检查路径、编码及 JSON 格式') from exc
