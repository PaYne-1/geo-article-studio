import importlib.util
from pathlib import Path
import zipfile

def test_zip_allowlist_excludes_secrets_runtime_and_config(tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts'/'build_package.py'
    spec=importlib.util.spec_from_file_location('build_package',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=tmp_path/'source';source.mkdir()
    (source/'SKILL.md').write_text('---\nname: geo-article-studio\ndescription: test\n---')
    (source/'.env').write_text('real-private-fixture')
    (source/'.env.example').write_text('GEO_IMAGE_API_KEY=')
    (source/'work').mkdir();(source/'work'/'customer.txt').write_text('private-customer-fixture')
    (source/'config').mkdir();(source/'config'/'settings.json').write_text('private-config-fixture')
    (source/'config'/'settings.example.json').write_text('{}')
    result=module.build(source,tmp_path/'delivery.zip')
    with zipfile.ZipFile(result['path']) as z:
        assert set(z.namelist())=={'geo-article-studio/SKILL.md','geo-article-studio/.env.example','geo-article-studio/config/settings.example.json','geo-article-studio/manifest.sha256'}
        assert all(b'private-' not in z.read(name) for name in z.namelist())
