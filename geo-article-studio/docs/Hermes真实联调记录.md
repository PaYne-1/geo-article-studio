# Hermes 真实联调记录

日期：2026-09-14。全部使用本机真实 Hermes v0.20.5 / Python 3.11.16 和显式 `local-qwen` / `qwen3.5:9b`，主模型端点 `http://127.0.0.1:7001/v1`。独立 home、配置、日志、模型输出和空库测试任务均在 `D:\0-AI 项目\GEO\artifacts\hermes-validation`，没有写入活动 profile 或技能源码包内的运行目录。没有真实客户资料、图片生成请求或生产内容。

## 已通过的具体项目

| 项目 | 实际证据与边界 |
|---|---|
| 完整隔离安装 | `install.py --skills-dir .../hermes-home/skills --data-dir .../geo-data` 成功，后续 --upgrade 保留数据并备份代码 |
| 真实技能发现/加载 | `skills_list` 包含 `geo-article-studio`；`skill_view(name, preprocess=False)` 成功返回元数据、正文和资源路径 |
| 自然语言命中一次 | 无 `-s` 的真实 Qwen 会话收到“配置资料库。我要使用 GEO图文生产助手…”后调用 `skill_view`，参数 name=`geo-article-studio`。这是带技能名称上下文的一次命中，不代表任何相似说法必然命中 |
| Hermes terminal → doctor | 使用实际 `terminal_tool` 与正确 Git Bash 引用运行已安装脚本，返回 exit_code=2，明确缺四库、规则、图片接口；`paid_request_sent=false`。预期缺配置阻断，不是假成功 |
| Hermes terminal → form | 实际 `terminal_tool` 运行 `form '配置资料库'`，exit_code=0，返回 configure_libraries 及六项缺失字段 |
| 真实模型结构拒绝 | Qwen 首轮 PREFLIGHT 额外输出 coverage_basis，submit-result 根据 additionalProperties=false 拒绝，action_id/revision 保持不变 |
| 同动作真实纠错重试 | 将具体结构错误反馈给 Qwen 后，第二个真实结果原样提交，进入 WAITING_APPROVAL/PREFLIGHT/revision2；未伪造人工批准 |

## 模型会话执行记录

| 会话 | 结果 |
|---|---|
| preload_doctor | 预加载技能，真实 Qwen 两次发起 terminal，但误用 PowerShell 的 `&` 被 Git Bash 拒绝；外层 105.02 秒结束。没有完成用户可见 doctor 流程 |
| natural_form | 无预加载，自然语言命中 skill_view；模型实际尝试两次 form，但忘记给含空格的 --config 路径加引号，argparse 正确拒绝；105.02 秒超时。完整自然语言表单闭环未通过 |
| preflight_bridge | 16.00 秒，模型真实返回 JSON；result 多出 coverage_basis 被执行层拒绝，未推进状态 |
| preflight_retry | 经明确反馈后，同一 action/revision 纠错重试，10.28 秒完成；未修改生成结果，submit-result 返回 WAITING_APPROVAL/PREFLIGHT/revision2 |

前两个会话的 Hermes `--run-budget 90` 未可靠硬终止流程，由外层看门狗在 105 秒结束；本地自动标题生成发生重试并探测无凭据的 fallback。后两个会话在隔离配置明确设 `auxiliary.title_generation.enabled=false` 和 `auxiliary.free_only=true`，且使用 `--reasoning none`，没有改当前活动 Hermes 的设置。依赖辅助默认设置可能造成额外延迟，运行时需要宿主自行处理真实超时。

## 可核实的文件

以下文件都在上述包外联调目录，ZIP不携带会话数据库或日志：

- `sessions.json`：四次会话的模型、耗时和结果。
- `natural-form-tool-evidence.json`：从隔离 Hermes SQLite 消息记录只读提取的 skill_view 调用、terminal 参数和实际错误。
- `direct-terminal-doctor.json`、`direct-terminal-form.json`：真实 Hermes terminal 工具结果。
- `preflight-action.json`：原动作及 JSON Schema。
- `preflight-qwen-envelope.json`：首轮被拒绝的原模型结果。
- `preflight-retry-qwen-envelope.json`：修订后原样提交的模型结果。
- `preflight-retry-submit.json`：实际状态机接受结果。
- `preflight_retry.log`：真实 Hermes 会话最终输出；`hermes-home/logs/agent.log` 记录本地主模型端点和 API 调用。

任务编号为 `d2ef6c3d6cf447a1`，首轮 action_id=`dc5f8420975c41d89935696ec7494e24`、revision=1。纠错提交后 action_id 更新为 `6b1664e2065e47db9c38f0b28f0d520f`、revision=2、WAITING_APPROVAL。没有执行 approve。

## 尚未通过的事项

这些实测证明本技能可被真实 Hermes 发现、执行脚本并进行真实 Qwen 结构化桥接；不能宣称完整生产端到端通过。

- 自然语言完整表单流程因模型 shell 引用错误超时；桥接文档已补充每个路径分别引用的精确命令，修订后的自然语言流程未再次验证。
- 显式斜杠入口的宿主实时会话未单独测试；本地技能发现和预加载通过不能替代斜杠路由实测。
- 纠错后 PREFLIGHT 只通过结构校验并等待人工审核。模型文字中“产品图像作为功能实现证据”仍需要语义纠正；图像不能证明未显示的性能，不能把这个等待批准结果称为人工批准或语义终审合格。
- 真实产品事实、四库内容、完整规则、第三方图片协议/密钥、真实图片生成与视觉审核尚未配置验证。测试四库为空，测试产品仅为合成上下文，无已确认参数。

建议宿主严格执行 schema、直接回传具体拒绝理由，再让当前 Qwen 重新生成；不要删除多余字段或代改模型正文来伪装通过。本机 shell 为 Git Bash，配置路径中的空格必须引用，参见 `references/hermes_bridge.md`。
