# Direct-Use Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an explicitly authorized automatic task use generated images without visual review while accurately recording that status.

**Architecture:** Bind a task-level policy at start. Route image generation directly to limited final text/file review under direct_use. Keep source upload, request and file integrity gates intact; publish a separate disclosure artifact.

**Tech Stack:** Python 3.11+, pytest, current CLI and durable workflow.

## Global Constraints

- Default and legacy tasks remain reviewed.
- Direct use is only for automatic mode with explicit real user authorization.
- Never report unviewed images as visually checked.
- Preserve existing source upload approvals and image request limits.

---

### Task 1: Bind policy and preserve existing safeguards

**Files:** `src/geo_article_studio/workflow.py`, `src/geo_article_studio/cli.py`, `src/geo_article_studio/host_bridge.py`, `tests/test_workflow_safety.py`, `tests/test_host_portability.py`

- [ ] Write failing tests for explicit selection, learning rejection, default visual gate and direct-use visual-gate exemption.
- [ ] Run the targeted tests and confirm expected failures.
- [ ] Add policy to start CLI, form and persisted task authorization; keep all source/request checks in select.
- [ ] Run targeted tests.

### Task 2: Route generation and final review without false visual claims

**Files:** `src/geo_article_studio/workflow.py`, `src/geo_article_studio/review.py`, `prompts/review_final.md`, `tests/test_workflow_safety.py`

- [ ] Write failing state-machine tests from generated images through final review; require accurate skipped-review receipt and no image_alignment passed claim.
- [ ] Run targeted tests and confirm failure.
- [ ] Implement direct route, receipt, restricted final review, and export invariant.
- [ ] Run targeted tests.

### Task 3: Disclose in output, document, package, publish

**Files:** `src/geo_article_studio/storage.py`, `src/geo_article_studio/workflow.py`, `SKILL.md`, `README.md`, `references/forms.md`, `references/hermes_bridge.md`, `docs/安装与首次配置.md`, version files and tests.

- [ ] Write failing export/manifest test for separate disclosure file.
- [ ] Implement minimal export/manifest support and update user-facing skill instructions.
- [ ] Run full pytest, package build, ZIP install smoke and secret scan.
- [ ] Commit, push public repo and publish versioned ZIP; clearly separate offline and Hermes/API verification.
