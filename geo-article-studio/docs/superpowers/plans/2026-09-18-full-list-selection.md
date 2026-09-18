# 完整候选清单免追问实施计划

> **For implementer:** Use test-first execution. Do not change incomplete-input behavior.

1. 在 `tests/test_entrypoints.py` 新增完整候选清单的开始任务表单测试，先确认它因缺少解释合同而失败。
2. 在 `src/geo_article_studio/host_bridge.py` 返回选择解释合同及规范候选集。
3. 在 `SKILL.md`、`references/forms.md`、`references/hermes_bridge.md` 写明“完整清单即全选”的宿主执行规则。
4. 运行针对性测试和完整测试套件，构建安装包并进行 ZIP 与 Hermes CLI 联调。
5. 更新版本、发布说明和公共 GitHub Release，明确未实测的 Hermes 自然语言界面与真实图片 API 项目。
