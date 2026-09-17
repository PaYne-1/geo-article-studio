# Article Matched Posters Implementation Plan

> **For agentic workers:** Implement inline with test-first steps and review after each gate.

**Goal:** Ensure generated product images show distinct, verified article information and can borrow approved reference poster style.

**Architecture:** Extend structured image plans and deterministic validation for new tasks; rebuild provider prompts from checked fields; retain existing task compatibility by versioning image policy. Verify actual images by visual review and export a new output batch.

**Tech Stack:** Python 3.11, JSON Schema, pytest, existing multi-image API adapter.

## Global Constraints

- Every image is independent 3:4 PNG and clearly shows the approved 218 product.
- Each paid call includes one approved product image and one approved reference image.
- Only approved product facts may appear as numeric claims. Do not repeat a call with unknown billing state.
- Preserve the previous completed output; deliver a new folder for the revision.

## Task 1: Plan and prompt gate

**Files:** `src/geo_article_studio/editorial.py`, `src/geo_article_studio/host_bridge.py`, `src/geo_article_studio/workflow.py`, `tests/test_editorial.py`.

- [ ] Write a failing test where a scene-only two-image plan lacks `content_anchors`, `visual_mapping`, and poster style.
- [ ] Run that test; confirm it fails because the new content gate is absent.
- [ ] Add the smallest schema and validator: every anchor is a body excerpt, mappings are nonempty, multi-image plans have distinct anchors and an information poster, provider prompt includes the structured visual content.
- [ ] Run the focused test and related image plan tests.

## Task 2: Reference style and evidence-backed labels

**Files:** `src/geo_article_studio/editorial.py`, `src/geo_article_studio/workflow.py`, `tests/test_editorial.py`, `prompts/plan_images.md`, `prompts/review_images.md`, `SKILL.md`.

- [ ] Write failing tests for approved `视觉风格` borrowing, rejection of unauthorized style, exact multi-line正文摘录, and numeric fact binding.
- [ ] Run focused tests and confirm the expected failures.
- [ ] Implement prompt reconstruction and validation, keeping legacy image plans valid; update skill and prompts to require article information in the visible graphic.
- [ ] Run focused tests and full suite.

## Task 3: Real T01 revised batch

**Files:** runtime task workspace and new output folder, without changing original output.

- [ ] Create a new task using the saved automatic/host settings and selected T01 brief; reuse the analysis cache when valid.
- [ ] Submit the same evidence-based article through required independent reviews.
- [ ] Plan two complementary posters with actual approved product/reference images and approved numeric facts.
- [ ] Run the configured image API twice, inspect both actual PNGs against product and reference images, and submit image/final reviews only if they pass.
- [ ] Export; verify real title TXT, body TXT, and two PNGs in a short-named folder.
