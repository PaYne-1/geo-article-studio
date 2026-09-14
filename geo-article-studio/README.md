# GEO图文生产助手

可安装的通用 Agent 技能包（v1.3.0），默认产品显示名 **218轻便侠**。Codex负责开发；Hermes、Codex、Claude Code 或具备文件、终端和人工确认能力的其他Agent负责运行。宿主负责对话，每次开始任务由用户选择当前宿主模型或提前保存的第三方文字API进行资料分析、策划、写作和独立语义审核。Python负责四库检索、人工授权状态、文件校验和第三方图片API。带图自动审核另需已验证的视觉能力。

先看[多Agent安装与兼容性](docs/多Agent安装与兼容性.md)与[通用宿主协议](references/agent_bridge.md)。安装支持不等于真实联调通过，具体范围见验收记录。

启动入口只有“开始任务”和“配置任务”。配置任务统一包含图片API和四库；开始任务后选择学习/自动模式。API密钥通过本地环境接入，不能发到聊天。

请先看 [安装与首次配置](docs/安装与首次配置.md)、[日常操作示例](docs/日常操作示例.md)、[验收记录](docs/验收记录.md)、[已知限制](docs/已知限制.md)。图片协议说明在 [图片接口适配说明](docs/图片接口适配说明.md)。

本包没有真实四库、产品事实、正式禁限规则或密钥。它们是首次运行配置项；不通过聊天收集密钥。选择宿主模型无需额外文字密钥；选择第三方文字API需要本地接入相应凭据。没有Web服务器、数据库服务或后台定时任务。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,documents]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/geo.py form "开始任务"
```

生产代码从自身位置加载资源，推荐用安装目录的`scripts/geo.py`；不要只单独复制src目录或单个SKILL.md。安装脚本完整复制包，不依赖Hermes Hub选择性下载未引用文件。

单次操作是 `python scripts/geo.py --config <绝对配置路径> <command>`。完整命令见`--help`。`next-action`与`submit-result`是内部CLI，由当前宿主自动推进，无需用户手填模型JSON。宿主模板为`config/host.example.json`，`host-check`检查声明能力；它不证明真实会话已通过。

离线演示必须选择一个尚不存在的隔离目录：

```powershell
.\.venv\Scripts\python.exe scripts/geo.py demo --root "D:\GEO演示运行" --mode both
```

demo仅使用虚构测试产品、脚本模拟用户/Qwen/视觉判定，以及本地HTTP返回的Pillow测试图。任何demo输出均为模拟结果，不是真实产品成品，不代表Hermes或收费图片API已通过。

第三方文字API的持久化设置、启动选项与限制见[文字模型配置与选择](docs/文字模型配置与选择.md)。
