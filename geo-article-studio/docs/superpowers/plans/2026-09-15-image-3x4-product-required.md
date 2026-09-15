# Mandatory 3:4 Product Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every image in every new illustrated article a 3:4 portrait that uses an approved current-version product image and visibly contains the product.

**Architecture:** Put invariant constants and deterministic image-plan validation in `editorial.py` and `workflow.py`, then align prompts, built-in rules, forms, examples, runtime settings, and visual review language. Preserve zero-image tasks and completed outputs. Use exact ratio arithmetic before any paid request.

**Tech Stack:** Python 3.11, JSON Schema, pytest, Markdown skill instructions, JSON runtime configuration.

## Global Constraints

- `3:4` always means width:height and portrait.
- Every planned image has `show_product=true` and at least one approved `product_image_id` for the current product version.
- Missing product reference or transmission authorization blocks before a paid API request.
- Completed artifacts remain immutable.
- The current provider dimension becomes `[768, 1024]`; compatibility with that third-party model remains locally configured but not claimed as remotely verified until a future authorized generation.

---

### Task 1: Add deterministic image invariants

**Files:**
- Modify: `tests/test_editorial.py`
- Modify: `tests/test_workflow_safety.py`
- Modify: `src/geo_article_studio/editorial.py`
- Modify: `src/geo_article_studio/workflow.py`

**Interfaces:**
- Produces: `editorial.REQUIRED_IMAGE_RATIO == '3:4'` and `editorial.REQUIRED_IMAGE_DIMENSION_RATIO == (3, 4)`.
- Produces: `validate_images(result, count)` rejection for missing product display/reference.
- Consumes: existing image authorization and current-product/version checks in `Engine._validate_image_plan`.

- [ ] **Step 1: Write failing tests**

```python
def test_image_standard_requires_3x4_and_product_in_every_image():
    assert editorial.REQUIRED_IMAGE_RATIO == '3:4'
    with pytest.raises(ValueError, match='产品'):
        editorial.validate_images({'images':[{'layout':'single','role':'cover','show_product':False,'product_image_ids':[]}]}, 1)
```

Add workflow cases showing a non-3:4 configured task fails selection and a product-free plan fails before generation.

- [ ] **Step 2: Run tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_editorial.py tests/test_workflow_safety.py -q`

Expected: failures because the current standard permits other ratios and product-free images.

- [ ] **Step 3: Implement the invariant**

```python
REQUIRED_IMAGE_RATIO = '3:4'
REQUIRED_IMAGE_DIMENSION_RATIO = (3, 4)

def validate_images(result, count):
    images = result['images']
    if any(not p.get('show_product') or not p.get('product_image_ids') for p in images):
        raise ValueError('每张图片必须展示产品并引用当前版本产品图')
```

In `Engine.select`, require `image_ratio == '3:4'` and `width * 4 == height * 3` when the selected image count is positive. Keep zero-image tasks unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_editorial.py tests/test_workflow_safety.py -q`

Expected: all selected tests pass.

### Task 2: Align rules, prompts, forms, and examples

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `prompts/plan_images.md`
- Modify: `prompts/review_images.md`
- Modify: `src/geo_article_studio/editorial.py`
- Modify: `src/geo_article_studio/configuration_form.py`
- Modify: `src/geo_article_studio/builtin_rules.json`
- Modify: `config/geo_editorial_rules.v1.json`
- Modify: `config/settings.example.json`
- Modify: `references/geo_editorial_standards.md`
- Modify: `references/forms.md`
- Modify: `docs/安装与首次配置.md`
- Modify: `docs/日常操作示例.md`
- Modify: `docs/图片接口适配说明.md`
- Modify: `tests/test_configuration_form.py`

**Interfaces:**
- Consumes: constants and validation from Task 1.
- Produces: consistent host instructions and user-facing configuration state.

- [ ] **Step 1: Change form test expectations to 3:4 portrait**

```python
form = form_for('配置任务', {})
assert form['values']['image_ratio'] == '3:4'
assert form['recommendations']['orientation'] == 'portrait'
```

- [ ] **Step 2: Run the form tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_configuration_form.py -q`

Expected: failure showing the old landscape/default-empty behavior.

- [ ] **Step 3: Update all normative content**

Replace landscape preference and conditional product display with fixed 3:4 portrait and mandatory product display. Set configuration defaults to `image_ratio: '3:4'` while leaving dimensions provider-specific in the generic example. Add explicit review language for product visibility, occlusion, deformation, wrong model, Logo, and visible parameters.

- [ ] **Step 4: Run form and editorial tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_configuration_form.py tests/test_editorial.py -q`

Expected: all tests pass.

### Task 3: Migrate the current runtime configuration

**Files:**
- Modify outside source control: `C:\Users\Administrator\.geo-article-studio\settings.json`

**Interfaces:**
- Consumes: validated settings schema.
- Produces: `defaults.image_ratio='3:4'`, `defaults.image_dimensions=[768,1024]`.

- [ ] **Step 1: Create a non-secret patch file**

```json
{"defaults":{"image_ratio":"3:4","image_dimensions":[768,1024]}}
```

- [ ] **Step 2: Apply through the CLI configuration merge**

Run: `scripts/geo.py --config C:\Users\Administrator\.geo-article-studio\settings.json configure --file <patch>`

Expected: saved configuration response with no API request.

- [ ] **Step 3: Read back only safe fields**

Assert the ratio and dimensions are exact, and do not print providers, environment values, or credentials.

### Task 4: Full verification and distribution

**Files:**
- Modify: `docs/v1.4.5更新与测试.md`
- Modify: `docs/测试输出-v1.4.5.txt`
- Rebuild outside source tree: `D:\0-AI 项目\GEO\dist\geo-article-studio-1.4.5.zip`

**Interfaces:**
- Produces: tested public source and installable ZIP without secrets or runtime data.

- [ ] **Step 1: Run full tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass with zero failures.

- [ ] **Step 2: Validate the skill and compile Python**

Run the installed `quick_validate.py` against the skill root and `python -m compileall -q src scripts`.

Expected: `Skill is valid!` and exit code 0.

- [ ] **Step 3: Scan and package**

Run `rg` for credential-like values, `git diff --check`, and `scripts/build_package.py`. Confirm ZIP integrity and that runtime artifacts are excluded.

- [ ] **Step 4: Commit, push, and replace the v1.4.5 release asset**

Commit the implementation, push `main`, rebuild the ZIP, and upload it to the existing public v1.4.5 release with `--clobber`.

- [ ] **Step 5: Report exact behavior and limits**

State that future illustrated tasks use 3:4 and every image requires a product reference. State that `[768,1024]` has not yet been remotely exercised with the configured third-party model and that completed prior outputs were not changed.
