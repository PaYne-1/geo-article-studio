# 人工图片复核与空间关系判断 Implementation Plan

> **For agentic workers:** Implement inline with test-driven development and verify each state transition.

**Goal:** 将用户对当前生成图的人工接受转成可审计、原子化的工作流动作，并避免把二维重叠误判为人物动作。

**Architecture:** `Engine.accept_images` 负责文件/快照/版本校验、人工审核记录和状态转换；CLI 只暴露参数与调用。提示词、内置规则和中文文档明确动作与空间关系分类。

**Tech Stack:** Python 3.11、pytest、JSON 状态机、PowerShell 打包。

## Global Constraints

- 仅当前任务当前文章的图片版本有效。
- 不新增图片 API 调用，不放宽未来审核规则。
- 自动模式在当前人工复核后恢复；学习模式保持原样。

---

### Task 1: 原子化人工接受

**Files:** `src/geo_article_studio/workflow.py`, `src/geo_article_studio/cli.py`, `tests/test_workflow_safety.py`

- [x] 写失败测试：从暂停的图片审核调用 `accept_images` 后只前进到 `FINAL_REVIEW`，记录人工结论和原始图片哈希，不增加请求。
- [x] 运行该测试并确认因缺方法而失败。
- [x] 实现 `Engine.accept_images(tid, action_id, revision, *, user_ref, actor='user')`；拒绝过期动作、文件损坏、非图片审核和无人工引用。
- [x] 增加 CLI `accept-images`，用同一方法执行。
- [x] 运行定向测试并确认通过。

### Task 2: 审核语义和交付

**Files:** `prompts/review_images.md`, `SKILL.md`, `config/geo_editorial_rules.v1.json`, `src/geo_article_studio/builtin_rules.json`, `README.md`, `docs/日常操作示例.md`, `pyproject.toml`

- [x] 明确人物真实动作、空间错位与不确定性分属不同审核项。
- [x] 写明人工接受只覆盖当前图片版本，不作为长期规则，不触发重生成。
- [x] 更新版本并重建安装 ZIP。
- [ ] 运行完整测试、打包验证和 Git 状态检查后推送公共仓库。
