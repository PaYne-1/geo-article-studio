# 通用Agent桥接：geo.host.v1

核心只依赖Python CLI，不导入Agent SDK、不启动多Agent框架、按本轮用户选择使用当前宿主模型或已保存的第三方文字API。先读docs/文字模型配置与选择.md，start必须显式传--text-source host或api。

v1.4新增三个独立文本审核动作FACT_REVIEW/GEO_REVIEW/CONTENT_REVIEW，host和api两条文字路径都依次执行。先按forms.md映射并确认geo_brief，遵循next-action给出的editorial_standards、prompt_template和result_schema。不得沿用旧TEXT_REVIEW单步代替三轮。完整要求见geo_editorial_standards.md。

## 能力声明

将config/host.example.json合并到运行配置。host.agent可以是hermes、codex、claude-code或其他标识；host.model记录实际模型，不知道则保持null。capabilities使用true/false/null：file_io、terminal、structured_results、human_confirmation，自动图片审核另需visual_review及visual_verification_ref。null是未确认，不等于true。

`python "技能路径/scripts/geo.py" host-check --file "宿主配置.json"`无需产品资料。加`--stage IMAGE_REVIEW --with-images --mode automatic`检查图片审核能力。ready只表示声明满足契约；declared_only不等于平台实测。旧版未声明capabilities的配置仍可执行，但标记undeclared，不能报告兼容性验证通过。

工具映射由宿主选择：读文件→它自己的文件工具，运行CLI→终端/执行工具，确认→当前真实用户会话，看图→实际可用的视觉工具或多模态模型。不要求工具叫terminal或skill_view，不要求有Hermes目录。

## 动作循环

1. 根据真实用户输入调用form/configure/start/select；用户不用维护模型结果JSON。
2. next-action返回kind/stage/host_contract/prompt_template/input_refs/result_schema。NEEDS_MODEL由当前模型完成，写一个受支持字段的信封：

```json
{"protocol":"geo.host.v1","action_id":"本次动作ID","expected_revision":1,"actor":"model","producer":{"agent":"实际宿主","model":"实际模型"},"result":{}}
```

result必须满足当前schema，不是照抄空对象。producer可省略，记录是self_reported，不能证明身份。旧信封不带protocol/producer仍兼容。审核reviewer=model，旧qwen兼容。真人看图则reviewer=human、actor=user和真实user_ref，不能附producer冒充模型。

3. `submit-result TASK_ID --file "绝对JSON路径"`。资料文字不得拼接shell命令；优先用文件工具写JSON，只向shell传固定命令及正确引用的路径。被拒绝后按具体错误重新生成；连续3次失败pause，不修改执行层来接受错误。
4. NEEDS_USER展示并等待真实确认；NEEDS_TOOL按tool执行run-text、reuse-analysis、run-image或export。reuse-analysis需传当前action_id和expected_revision，执行后重新调用next-action；复用仅限输入指纹一致的聊天主题分析，仍须人工选题和逐篇填写数量。BLOCKED展示host_contract.missing或具体错误。LEARNING_REVIEW是独立模型复盘动作，完成后回当前步骤批准。自动模式普通动作连续循环至完成/阻断。
   图片审核失败或暂停后，若当前用户明确接受当前文章的图片，可调用`accept-images TASK_ID --action-id ID --revision N --user-ref 当前用户引用`。执行层核对图片文件、正文和计划哈希，记录人工通过并进入最终联合审核；旧模型失败审核仍留在历史中。该操作不重生图、不改变后续任务规则。
5. 完成CLI直接返回真实目录字符串，只把路径交用户；未完成JSON不是成功路径。

## 环境与迁移

每个宿主的沙箱、挂载和环境变量机制不同，必须验证路径可达，凭据在实际执行进程接入，不打印值。跨机器不自动替换斜杠猜路径；改变运行配置须显式refresh复审。没有Skills发现机制的Agent可显式读取本SKILL再操作CLI；纯聊天无执行工具时不能生产文件。

能力不足时仍可做不依赖该能力的操作，例如没有视觉能力可做合法零图文章。不能把协议兼容测试表述为所有Agent真实端到端通过。宿主安装方式与验证分层见docs/多Agent安装与兼容性.md。
