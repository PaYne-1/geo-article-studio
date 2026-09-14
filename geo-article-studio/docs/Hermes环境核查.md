# Hermes 环境核查

核查日期：2026-09-14（Asia/Shanghai）。本记录区分本地实现、配置声明、只读服务探测与真实推理；后两者不互相替代。没有打印或复制 `.env`、认证文件或配置全文。

| 项目 | 实测结果 |
|---|---|
| 操作系统 | Windows，原生 PowerShell；没有假定 WSL 或远程挂载 |
| Hermes 入口 | `C:\Users\Administrator\AppData\Local\hermes\bin\hermes.exe` |
| 版本 | v0.20.5，upstream `5eb99eb2`，本地提交 `1fac4408`（主任务前置核查） |
| 源码 | `C:\Users\Administrator\AppData\Local\hermes\hermes-agent` |
| Hermes Python | `C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`，3.11.16 |
| 当前 PATH 的 `python` | `D:\cow agent\python.exe`，3.9.13；不要用它创建生产运行环境 |
| 实际 HERMES_HOME | `C:\Users\Administrator\AppData\Local\hermes` |
| sticky/effective profile | `default` / `default` |
| 实际技能目录 | `C:\Users\Administrator\AppData\Local\hermes\skills` |
| external_dirs / create_dir | 未配置 |
| 终端 | `terminal.backend=local`，`cwd=.`；真实终端工具使用 Windows Git Bash（见下文） |
| 当前默认文字模型 | `deepseek-v4-flash`，provider=`deepseek`；不能声称当前默认就是 Qwen |
| 已配置本地 Qwen | provider=`local-qwen`，`api=http://127.0.0.1:7001/v1`，`transport=chat_completions`，`default_model=qwen3.5:9b` |
| 本地模型只读探测 | `GET http://127.0.0.1:7001/v1/models` 返回 `qwen3.5:9b` |
| Ollama 只读探测 | `GET http://localhost:11434/api/tags` 返回 `qwen3.5:9b`，文件大小 6594474711 字节 |
| 视觉 | local-qwen 的模型配置声明 `supports_vision=true`；本核查未执行图像推理，不能视为视觉审核已验证 |

## 官方资料和本地实现对照

已访问 [Hermes 官方 Skills 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/)。文档支持 `SKILL.md` 的 name、description 元数据，渐进加载 references/scripts 等资源，`skills_list` / `skill_view`，以及 `/skill-name` 显式命令。`external_dirs` 可加入外部目录，当前进程/profile 的技能目录优先。受信任项目技能可具有更高优先级；本包安装器不修改项目信任或 Hermes 配置。

本地以下接口已核实存在，生产技能不用导入它们：

- `hermes_constants.get_hermes_home()`：上下文覆盖 → HERMES_HOME → 平台原生默认路径；Windows 默认是 LOCALAPPDATA/hermes，不能照搬 Linux `~/.hermes`。
- `hermes_cli.profiles.get_active_profile()` 与 `get_active_profile_name()`：分别反映 sticky 和当前有效 profile。命令行 `--profile` 在导入大量模块前设置 home。
- `agent.skill_utils.get_all_skills_dirs()`：profile 本地目录与外部目录；`get_scan_ordered_skills_dirs()` 额外处理受信任项目的优先级。
- `tools.skills_tool.skills_list(category=None, task_id=None)`、`skill_view(name, file_path=None, task_id=None, preprocess=True)`：本地真实技能接口。`_skills_dir()` 按实时 profile home 解析。
- `toolsets.py` 注册 `terminal`、`read_file`、`write_file`、`patch`、`search_files`；`tools/vision_tools.py` 注册 `vision_analyze`。存在工具实现不等于当前模型会可靠调用，也不等于远端模型可以读取本机路径。
- `check_vision_requirements()` 仅检测能否解析视觉客户端，不能替代用实际图片进行的视觉审核验收。

官方 URL/GitHub 单技能安装可能只复制 SKILL.md 明确引用的局部资源。为了确保 `src`、prompts、config 等完整安装，本包采用显式目标的本地完整目录/ZIP安装器，不声称 Hermes Hub 会自动拉取整个仓库。

## 有限真实联调方案

以下参数已由本机 `hermes chat --help` 核实：`--provider`、`-m`、`--query-file`、`-s`、`--max-turns`、`--run-budget`、`-Q`。先只读确认本地代理，再显式覆盖 provider 和 model，避免落到当前 DeepSeek 默认服务。

```powershell
hermes chat --provider local-qwen -m qwen3.5:9b --query-file '完整路径\联调提示.txt' --max-turns 4 --run-budget 90 -Q
```

联调提示只能含合成资料和有限动作上下文。技能安装后可加 `-s geo-article-studio` 测试显式预加载；自然语言触发要在没有 `-s` 的独立会话中另测。若测试超时、未触发或未调用脚本，记录实际失败，不能把预加载或纯文本回复当成自然语言触发通过。可在独立 `HERMES_HOME` 中复制经过白名单提取的本地 provider 非敏感配置并安装技能进行隔离验收，但不得修改现有活动 profile，也不得复制真实凭据。

上述前置核查只读且没有调用模型；后续真实调用均在隔离 home 中进行，没有安装进活动 profile。最终真实联调以 `验收记录.md` 中主任务追加的执行证据为准。真实四库、完整规则、第三方图片协议与密钥仍需首次配置，离线测试不替代这些验证。

后续隔离真实联调补充：已在源包之外的 `D:\0-AI 项目\GEO\artifacts\hermes-validation\hermes-home` 完整安装。真实 `skill_view(..., preprocess=False)` 成功读到元数据和正文，`skills_list()` 包含本技能。首个 Qwen 会话日志证实请求发往 `http://127.0.0.1:7001/v1`、模型为 `qwen3.5:9b`，并实际发起 terminal 工具调用。但 PowerShell 的 `& 'python' ...` 在该工具的 `/usr/bin/bash` 中被拒绝，首轮达到外层 105 秒超时，不能计为 doctor 成功。实际 Hermes 的90秒 run-budget 未可靠硬终止该会话，外层看门狗负责结束进程。

本地 `tools/environments/local.py` 的 `_find_bash()` 优先寻找 Windows Git Bash、区分 WSL。宿主应先探测真实 shell 后正确引用命令；本机 Git Bash 可用带引号的 `C:/.../python.exe` 直接执行，不加 PowerShell 的 `&`。这是本机 shell 兼容性事实，不是把 Windows 路径擅自映射为 WSL。

四次真实会话已完成，停止进一步模型调用：

| 会话 | 验证层级与结果 |
|---|---|
| preload_doctor，105.02秒 | 真实模型/terminal调用成立；PowerShell语法不兼容，预检闭环未通过，外层超时 |
| natural_form，105.02秒 | 无-s自然语言命中skill_view成立；模型遗漏配置路径引号，form未成功，外层超时 |
| preflight_bridge，16.00秒 | 真实模型生成JSON；额外coverage_basis被严格schema拒绝，状态未推进 |
| preflight_retry，10.28秒 | 反馈具体错误后同action/revision重新生成，原样提交成功，停在WAITING_APPROVAL/PREFLIGHT/revision2；不是人工批准或语义终审通过 |

另外，直接通过真实 Hermes `terminal_tool` 执行正确引用的 doctor（预期缺配置exit2）和 form（exit0）均通过。详细证据、合成数据说明、辅助标题配置、仍需修订的语义措辞与未验证事项见 [Hermes真实联调记录](Hermes真实联调记录.md)。本技能安装器12项测试在实际Hermes Python3.11.16通过；完整工程测试由主验收记录汇总。

## 可重复的只读检查

```powershell
& 'C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe' 'D:\0-AI 项目\GEO\geo-article-studio\scripts\install.py' --probe
```

`--probe` 不写配置、不读取 `.env`、不请求生成、不自动安装。输出当前启动环境以及经实际存在的 Hermes 解释器读取的 home/profile/skills 路径。迁移到 WSL、容器或其他机器时，在那个实际 Hermes 运行环境内重新运行；Windows 探测结果不证明远程可读。
