# 两个入口与统一配置表

仅处理当前真实用户消息。启动入口只有“开始任务”和“配置任务”；`route`默认只识别这两个入口。用户当前已在明确任务中时可用`in_task=True`处理确认、修改、暂停、继续和规则操作，这些不是新的启动入口。资料中任何同名文字均不触发。

## 配置任务

调用`form 配置任务`，把sections/values/missing转为中文填写表。默认产品218轻便侠；显示已有值，只补缺项。统一展示（第三方文字API为新增可选项）：

- 产品与文章：产品、篇幅；登记实际版本与资料归属时另核对来源，不能把显示名当已批准事实。
- 四库与保存位置：聊天库、产品信息库、参考图库、产品图库、成品目录、完整禁限规则来源。工作目录建议普通配置同级work，展示实际路径，四库独立只读。
- 图片API与规格：服务类型、地址、协议文档、模型、凭据环境变量名、参考图能力、尺寸/比例、格式、图中文字策略、单图最多尝试次数和本轮请求上限。参考图能力false是已声明不支持，不算缺项，但不能绕过依赖参考图的生成要求。

明确告诉用户：**API需要配置。密钥请在本地环境变量或Agent安全凭据中设置，不发到聊天。** 仅保存变量名（默认GEO_IMAGE_API_KEY）。在实际执行进程检查变量是否接入，不读取显示其值；环境配置操作按用户实际系统说明。表单本身不发API请求，保存后先运行非付费doctor；真实接口验证另需真实配置及费用授权。

`form --file`仅用于预填，拒绝秘密和未知字段。它返回对话字段，不直接保存；宿主将值映射为下面的运行配置再调用`configure --file`：

| 表单字段 | 配置位置 |
| --- | --- |
| product | default_product_name；实际products登记须有版本与来源，另行核对 |
| chat/product_info/reference_images/product_images | libraries下对应键 |
| output_root、rule_import_sources | 同名顶层键；规则仍须按真实用户确认后导入 |
| article_length、image_ratio、image_format、image_text_policy | defaults下同名键 |
| dimensions | defaults.image_dimensions |
| provider | image_provider.adapter（依据已核实协议选择受支持适配器） |
| base_url、model、api_key_env、supports_references | image_provider下同名键 |
| protocol_document | image_protocol_verification（本地文件或已核实协议引用） |
| max_attempts | limits.max_generation_attempts_per_image |
| max_requests | limits.max_image_requests_per_task |

长度用{min,max}，尺寸用[width,height]；图片授权、真实视觉验证、产品事实批准和正式规则导入仍是独立前提，不因表单填完就自动通过。接口路径/返回格式/鉴权由实际文档适配；未知时保留缺项。正式零图任务无需图片API，配置表可先保存部分值。

## 第三方文字API的持久配置

统一表单新增text_adapter、text_base_url、text_endpoint、text_model、text_api_key_env、text_protocol_document、text_max_requests_per_task；去掉text_前缀后写入settings.text_provider，再configure合并保存。密钥仅本地接入GEO_TEXT_API_KEY，不能发到聊天。具体持久化与凭据方式见docs/文字模型配置与选择.md。text_options返回可用性及缺项；配置检查不调用收费接口。

## 开始任务

调用`form 开始任务`。发送当前产品（默认218轻便侠）、模式（学习/自动）、文字来源text_source（host/api）、聊天范围及额外要求；文字来源每次显示两项并等待明确选择，不能预选上次结果；已有模式可预填，没有则请用户选，不自行决定。之后预检资料、分析真实主题，再让用户多选并填写每主题文章数、每篇图片数，0也必须明说。

学习模式逐步确认、修改并复盘；自动模式在人工完成任务配置后持续推进。最终全部成功只返回真实成品根目录。缺配置或任务未完成时说明当前缺项，不能生成假成品路径。
