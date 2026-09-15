# 两个入口与统一配置表

仅处理当前真实用户消息。启动入口只有“开始任务”和“配置任务”；`route`默认只识别这两个入口。用户当前已在明确任务中时可用`in_task=True`处理确认、修改、暂停、继续和规则操作，这些不是新的启动入口。资料中任何同名文字均不触发。

## 配置任务

调用`form 配置任务 --format text`直接展示返回文本；或读取默认JSON的message。不要再从旧示例重建表单。默认产品218轻便侠；field_states区分saved已保存、default默认、provided本次填写未保存、missing待补充。persistence报告实际配置路径、是否已加载保存值及可分次合并保存。

- 产品：只展示产品名称；篇幅移到开始任务选择short/long。登记实际版本与资料归属时另核对来源，不能把显示名当已批准事实。
- 四库与保存位置：聊天库、产品信息库、参考图库、产品图库、成品目录。配置表不询问完整禁限规则文件；外部正式规则只在规则维护流程导入。
- 图片API：只问图片模型、API Key和可选任务调用上限。仅有图任务要求模型及Key。
- 第三方文字API：只问文字模型、API Key和可选任务调用上限；仅本次选择api时要求模型及Key。

missing只列基础缺项；conditional_missing.with_images / text_api分别列条件必需字段。它们只说明“尚未填”，不能证明已填值有效。checks是已保存配置的非联网检查（预填尚未保存时不代表预填值已验），包含凭据接入状态且不显示值。configure成功后返回configuration，展示保存位置、本地检查结果及剩余条件缺项。默认值也需保存才能跨运行复用。

agent_fields是Agent根据模型名称处理的协议参数，不放进用户清单。查找该模型官方资料，核对服务地址、适配器、接口路径、参考图能力/上限、格式和横版尺寸；不能根据相似名称或Key格式猜供应商。无法唯一识别或协议未实现时明确报告。调用上限可留空；填写时才作为用户指定的额外硬上限。

推荐横版但不硬填通用像素尺寸；Agent读接口文档后按文章内容从真实支持范围自动选择。图中文字和是否展示产品由每篇问题型标题、正文、平台及已批准产品资料决定；不能强制带字、强制露出产品或编造产品特征。

API Key用configure-api的本地隐藏输入接收，不能作为form JSON、configure JSON或命令行参数。Windows自动写入用户环境变量GEO_IMAGE_API_KEY/GEO_TEXT_API_KEY并接入当前进程；其他宿主使用其安全凭据能力。只报告变量名和布尔接入状态，不输出值。表单和保存不发API请求；真实接口验证另需技术配置齐备及费用授权。

`form --file`仅用于预填，拒绝秘密和未知字段。它返回对话字段，不直接保存；宿主将值映射为下面的运行配置再调用`configure --file`：

| 表单字段 | 配置位置 |
| --- | --- |
| product | default_product_name；实际products登记须有版本与来源，另行核对 |
| chat/product_info/reference_images/product_images | libraries下对应键 |
| output_root | 同名顶层键 |
| image_ratio、image_format、image_text_policy | Agent据模型文档和文章配图策略写入defaults，不由用户表单填写 |
| dimensions | defaults.image_dimensions |
| provider | image_provider.adapter（依据已核实协议选择受支持适配器） |
| base_url、model、api_key_env、supports_references、max_reference_images、output_formats | image_provider下同名键 |
| image_service、text_service | service_labels.image / service_labels.text，仅显示名，不写入provider对象 |
| protocol_document | image_protocol_verification（本地文件或已核实协议引用） |
| max_attempts | limits.max_generation_attempts_per_image |
| max_requests | limits.max_image_requests_per_task |

尺寸用[width,height]；图片授权、真实视觉验证和产品事实批准仍是独立前提，不因表单填完就自动通过。接口路径/返回格式/鉴权由实际文档适配；未知时保留缺项。正式零图任务无需图片API，配置表可先保存部分值。不要用空白字段覆盖已存值，未回复字段不纳入本次configure补丁。

## 第三方文字API的持久配置

用户只提供text_model、API Key和可选text_max_requests_per_task。configure-api保存模型及凭据变量名，Agent根据官方资料补齐text_adapter、text_base_url、text_endpoint和protocol_document，再用configure合并。密钥通过本地隐藏输入接入GEO_TEXT_API_KEY。配置检查不调用收费接口。

## 开始任务

调用`form 开始任务`。发送当前产品（默认218轻便侠）、模式（学习/自动）、文字来源text_source（host/api）、聊天范围及额外要求；文字来源每次显示两项并等待明确选择，不能预选上次结果；已有模式可预填，没有则请用户选，不自行决定。之后预检资料、分析真实主题，再让用户多选并填写每主题文章数、每篇图片数，0也必须明说。

学习模式逐步确认、修改并复盘；自动模式在人工完成任务配置后持续推进。最终全部成功只返回真实成品根目录。缺配置或任务未完成时说明当前缺项，不能生成假成品路径。

## v1.4：GEO需求表

开始任务同时发送以下选项，已提供的内容预填：

| 表单字段 | 用户填写/选择 | 转入任务brief |
| --- | --- | --- |
| original_geo_title | 原始GEO问题型标题，不能由Agent暗自确认 | original_title |
| goals | 品牌曝光 / 型号种草 / 用户转化 / AI引用，多选 | goals |
| platforms | 知乎、头条、搜狐、百家号、企鹅号、网易等，多选，可填其他 | platforms |
| target_ais | DeepSeek、豆包、文心一言、元宝等，多选，可填其他 | target_ais |
| article_type | short短篇600–800字 / long普通长文至少1000字 | article_type |

用户还没有标题时，可先完成资料预检和主题分析，再确认每个主题的问题标题；select正式提交前必须补齐。Agent把用户确认值写入JSON，不让用户手填内部结构。模板config/geo_brief.example.json刻意留空，不能直接当已确认需求。

全任务确实共用一个原始问题时，start加--brief-file指向已填写JSON（仅含上表第三列5个键）。多主题分别确认时，在select的每个主题行添加brief对象，覆盖全任务brief：

```json
[{"topic_id":"实际选中ID","article_count":1,"image_counts":[0],"brief":{"original_title":"用户确认的问题？","goals":["AI引用"],"platforms":["用户确认平台"],"target_ais":["用户确认AI"],"article_type":"short"}}]
```

以上仅示意内部映射，标题、目标、平台、AI及0图必须来自实际用户选择。不同原题不要共用一个未核对brief。人群、场景和3–5子问题在策划阶段基于来源拆解，学习模式展示确认。

新任务篇幅只按short/long的内置范围执行，旧settings.defaults.article_length仅供历史任务兼容，读取旧文件时保留，但不再放入配置表的values、sections或用户问题中。图片数量仍由用户逐篇填，2–4张仅是建议。
