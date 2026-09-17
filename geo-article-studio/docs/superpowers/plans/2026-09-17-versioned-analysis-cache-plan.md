# 跨任务聊天分析复用 Implementation Plan

**Goal:** 对输入完全相同的新任务复用已校验的聊天主题分析，同时保留人工选题与所有成稿审核。

**Architecture:** `Engine` 从成功的 ANALYZING 提交写入运行工作区的版本化本地缓存；`next_action` 报告命中；`reuse_analysis` 再次验证并应用。CLI 暴露 `reuse-analysis`，宿主循环按 `NEEDS_TOOL` 执行。

**Tech Stack:** Python 3.11、JSON 状态机、pytest。

## Global Constraints

- 不跨产品/资料/事实/规则/配置/文字来源复用。
- 不绕过当前任务人工选题、文章生成、事实/GEO/合规/视觉终审。
- 不发送新的文字或图片 API 请求来检查缓存。

---

### Task 1: 严格输入指纹与缓存文件

**Files:** `src/geo_article_studio/workflow.py`, `tests/test_workflow_safety.py`

- [x] 写失败测试：同输入新任务命中，任一来源、事实、规则或配置变化均未命中。
- [x] 确认测试因尚无复用动作而失败。
- [x] 用稳定指纹缓存分析结果与哈希，成功提交后原子写入本地工作区。
- [x] 定向测试通过。

### Task 2: 状态机和宿主协议

**Files:** `src/geo_article_studio/workflow.py`, `src/geo_article_studio/cli.py`, `tests/test_workflow_safety.py`

- [x] 写失败测试：命中时返回 `NEEDS_TOOL/reuse-analysis`，工具应用后停人工选题，重复或过期动作拒绝。
- [x] 实现 `reuse_analysis`，重新验证当前来源、缓存哈希和完整分析约束，再写入复用历史。
- [x] 增加 CLI 子命令与宿主文档。
- [x] 定向测试通过。

### Task 3: 技能发布

**Files:** `SKILL.md`, `README.md`, `references/agent_bridge.md`, `docs/已知限制.md`, `pyproject.toml`, `src/geo_article_studio/__init__.py`

- [x] 说明命中/未命中行为及仍需人工选题与审核。
- [x] 全量回归、技能校验、安装 ZIP 冒烟测试。
- [ ] 更新正式包和公共 Git 仓库。
