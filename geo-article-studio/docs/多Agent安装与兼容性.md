# 多 Agent 安装与兼容性

核实日期：2026-09-14。本包向支持 Agent Skills、文件读取和本地命令执行的宿主提供同一份 `SKILL.md`、提示词及 Python 执行层。`--host` 选择安装记录和环境探测方式，不改写技能正文、不绑定文字模型，也不证明任意 Agent 已能可靠完成任务。

## 格式和加载位置

Agent Skills 标准使用包含 YAML 元数据和 Markdown 正文的 `SKILL.md`，可随包提供脚本和参考文件。本包必须完整安装，不能只复制单个 Markdown 文件。[Agent Skills 官方规范](https://agentskills.io/specification)

| 宿主 | 官方或实测技能父目录 | 本包验证范围 |
| --- | --- | --- |
| 通用 Agent | 由其官方文档或显式技能加载接口确定，标准不规定统一安装路径 | 完整目录安装、升级、只读探测；不依赖 Hermes |
| Codex | 项目 `.agents/skills`；个人 `~/.agents/skills` | 安装、离线契约和当前Codex显式读取后的有限真实预检交接；原生发现未验证 |
| Claude Code | 项目 `.claude/skills`；个人 `~/.claude/skills` | 格式、安装及离线契约测试；尚未完成真实 Claude Code 联调 |
| Hermes | 当前实际会话/profile 的技能目录 | 保留已有有限真实联调证据，见下文；新版本安装测试不替代真实联调 |

Codex 会从当前工作目录向仓库根目录查找 `.agents/skills`；官方旧地址现重定向至 [Build skills](https://learn.chatgpt.com/docs/build-skills)。Claude Code 的项目和个人路径见 [官方 Skills 文档](https://code.claude.com/docs/en/skills)。两者的加载规则不同，不能把通用目录当成自动共享目录。

## 共同前提

选择独立 Python 3.11+，显式提供技能父目录和运行数据目录。下面示例适用于 Windows PowerShell；其他机器替换为实际绝对路径。安装器不自动创建宿主配置、选择活动 profile、安装依赖或调用模型。

```powershell
$basePython = 'D:\0-AI 项目\GEO\.venv\Scripts\python.exe'
$source = 'D:\0-AI 项目\GEO\geo-article-studio'
```

后面的安装示例分别使用独立的验证目录。真实安装时将 `$skills` 改为已经确认的目标父目录；代码与数据必须完全分离，并位于源代码目录外。`$data` 保存配置、索引、任务和学习规则，不能放入技能目录。每个宿主建议使用独立 `$data`，避免多个进程同时推进同一任务。

### 通用 Agent

```powershell
$skills = 'D:\0-AI 项目\GEO\宿主验证\通用技能'
$data = 'D:\0-AI 项目\GEO\宿主验证\通用运行数据'
& $basePython "$source\scripts\install.py" --host generic --probe --skills-dir $skills --data-dir $data
& $basePython "$source\scripts\install.py" --host generic --skills-dir $skills --data-dir $data
```

省略 `--host` 等同于 `generic`。安装完成后，按目标 Agent 自己的机制发现或显式加载 `$skills\geo-article-studio\SKILL.md`，并允许其读取随包资源、执行指定 Python。没有技能加载机制但可以读文件、执行命令的 Agent，也可显式读取该文件后按契约执行；仅聊天、无法访问文件或执行命令的宿主无法直接运行本包。

### Codex

```powershell
$codexProject = 'D:\0-AI 项目\GEO\宿主验证\Codex工作区'
$skills = "$codexProject\.agents\skills"
$data = 'D:\0-AI 项目\GEO\宿主验证\Codex运行数据'
& $basePython "$source\scripts\install.py" --host codex --probe --skills-dir $skills --data-dir $data
& $basePython "$source\scripts\install.py" --host codex --skills-dir $skills --data-dir $data
```

在 Codex 中打开对应项目工作区，核对技能列表或明确调用 `$geo-article-studio`。个人安装可将技能父目录明确设为用户目录下的 `.agents\skills`。宿主必须获准访问运行数据和素材的实际位置；沙箱权限与模型能力另行验收。项目目录的来源和范围见前述 Codex 官方文档。

### Claude Code

```powershell
$claudeProject = 'D:\0-AI 项目\GEO\宿主验证\Claude工作区'
$skills = "$claudeProject\.claude\skills"
$data = 'D:\0-AI 项目\GEO\宿主验证\Claude运行数据'
& $basePython "$source\scripts\install.py" --host claude-code --probe --skills-dir $skills --data-dir $data
& $basePython "$source\scripts\install.py" --host claude-code --skills-dir $skills --data-dir $data
```

从对应项目启动 Claude Code，使用 `/geo-article-studio` 显式调用。个人安装可明确选择用户目录下的 `.claude\skills`。此路径和调用形式来自 [Claude Code 官方文档](https://code.claude.com/docs/en/skills)，本项目尚未完成该宿主真实会话、自然语言触发、模型输出或视觉审核联调。Claude Code 本地目录安装不能据此推断为 Claude 网页或云端会话安装。

### Hermes

```powershell
$skills = 'D:\0-AI 项目\GEO\宿主验证\Hermes独立Home\skills'
$data = 'D:\0-AI 项目\GEO\宿主验证\Hermes运行数据'
& $basePython "$source\scripts\install.py" --host hermes --probe --skills-dir $skills --data-dir $data
& $basePython "$source\scripts\install.py" --host hermes --skills-dir $skills --data-dir $data
```

探测观察当前启动环境中实际存在的 Hermes 解释器，并保留原来的 home/profile/skills 只读接口探测。示例 `$skills` 是显式隔离目标，不会因为探测到活动 home 就自动改装过去。要由 Hermes 发现此目录，必须在明确采用该独立 home 的会话中运行，或由用户明确配置其支持的技能目录机制。

已有实际 Windows 路径、profile 与终端差异见 [Hermes 环境核查](Hermes环境核查.md)。此前真实技能发现、自然语言加载、终端 doctor/form 和有限 Qwen 结构化预检证据见 [Hermes 真实联调记录](Hermes真实联调记录.md)。这些证据不表示完整生产任务或实际图片视觉审核通过。

## 所有宿主共用的运行环境

选定上面的一组 `$skills`、`$data` 后，执行：

```powershell
$skill = "$skills\geo-article-studio"
& $basePython -m venv "$data\venv"
$python = "$data\venv\Scripts\python.exe"
& $python -m pip install "$skill"
& $python "$skill\scripts\geo.py" --help
& $python "$skill\scripts\geo.py" --config "$data\settings.json" form '配置资料库'
```

配置和资料来源继续遵循 [首次配置说明](安装与首次配置.md) 及技能内的表单与宿主契约。安装记录不会自动生成生产 `settings.json`。运行命令始终显式带实际 `--config`；宿主根据 `next-action` 读取提示词、收集真实用户批准并通过 `submit-result` 提交结构化输出，不能用宿主自写文本绕过状态和修订校验。

文字模型由宿主选择，生成图片使用已配置并获授权的图片接口。若业务配置要求 Qwen，需在该宿主中确认实际调用了 Qwen；换 Agent 不意味着可以静默换模型。图像审核需要实际可用的视觉模型和可读图片；CLI 路径存在或安装成功不提供这种能力。

PowerShell 使用 `& $python ...`；Bash 使用带引号的解释器路径直接执行。先确认目标宿主实际 shell，不把 Windows 盘符替换成斜杠就声称完成 WSL 或远程路径映射。

## 探测、升级及边界

`generic`、`codex`、`claude-code` 的 `--probe` 仅输出当前 Python、PATH 中的相应 CLI（通用模式没有专属 CLI）及用户显式提供的目标路径；不启动宿主进程，不调用 Hermes Python/接口，不读宿主配置。`skill_loading_verified` 和 `model_capabilities_verified` 始终为 `false`，需通过真实会话另外验证。未安装 CLI 时报告 `null`，仍可离线安装完整技能包。

CLI 的 `--probe` 默认现在是通用探测；需要原 Hermes 观察结果时必须加 `--host hermes`。为兼容已有 Python 调用者，无参数 `probe()` 仍保留 Hermes 行为。

安装记录 `installation.json` 包含 `host`、`protocol: "geo.host.v1"` 和独立 `data_dir`。该协议字段是本包宿主桥接版本，不是宿主官方能力认证。四种宿主安装完全相同的技能源文件，只记录所选宿主。

```powershell
# $selectedHost 必须和该安装的 installation.json 一致。
$selectedHost = 'generic'
& $basePython "$source\scripts\install.py" --host $selectedHost --skills-dir $skills --data-dir $data --upgrade
```

升级先备份旧代码并沿用已登记的数据目录，默认拒绝覆盖。已登记 host 的目标不允许切换 host 升级；请使用新的明确技能目录。旧版安装记录没有 host 时按 Hermes 处理，升级必须加 `--host hermes`。发现旧技能内运行数据时仍拒绝升级。ZIP 安全检查、链接拒绝、敏感文件排除及原子替换回滚继续生效，安装器不会为了换宿主删除运行数据。

本次自动化覆盖无 Hermes 环境下通用安装、备份升级和探测，四种宿主相同源码安装、只读探测不启动进程，以及数据隔离和跨宿主升级拒绝。它们是安装与契约层证据，不能代替各宿主实际加载、文字模型质量、工具调用、图片服务或视觉审核验收。

当前版本实测的具体过程与未验证项见[多Agent实测记录](多Agent实测记录.md)。
