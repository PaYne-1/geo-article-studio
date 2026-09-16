# 数据与宿主提交

`next-action TASK_ID`返回task_id/action_id/expected_revision/kind/stage/object_id/prompt_template/input_refs/context/result_schema/approval_required/content_hash。每次提交都会产生新action_id与revision，重放旧请求拒绝。

```json
{
 "action_id":"从本次next-action取得",
 "expected_revision":1,
 "actor":"model",
 "result":{}
}
```

result必须满足本次返回的完整JSON Schema，不能只抄此空结构。语义生成使用model；只有真实人工看图结果可以actor=user、user_ref=当前用户消息引用，reviewer=human。这是宿主信任边界，不具备强身份验证，恶意本地操作者仍能修改文件或假报actor。

来源含source_id/library_type/product_id/hash/location/snippet/metadata，snippet已本地脱敏；location可能包含本地真实路径，仅内部可用。事实以fact_id/claim/text/source_ids/status维护；模型候选只能pending。索引source_id非文件路径；提交结果不接受任意输出文件路径。product_id和version必须显式配置或通过人工确认映射。

图片索引说明文件只是不可信描述。真实第三方传输许可应在普通配置的image_authorizations按来源ID记录当前用户授权引用，不能让源图片说明中的approved自行提供上传授权。新写实产品配图的product_image_ids与reference_image_ids均须非空，render_mode固定reference_edit；接口一次接收产品基准图和场景参考图，产品与参考来源不可互换。

内部任务记录位于workspace_root/tasks，普通源库不得写回。输出仅标题.txt、正文.txt、配图文件。费用未知保持null，使用调用上限；金额硬上限需要image_pricing的真实计费依据。

当前所有新任务带editorial_version=geo-editorial.v2。next-action.context包含editorial_standards和geo_brief，PLANNING/WRITING必须满足返回Schema中的geo结构。计划包含核心答案、3–5子问题、人群/场景、有序章节、真实场景source_ids及批准产品fact_ids。正文geo包含opening、sections(kind/heading/text)、faqs(question/answer)；body必须与它们的标准拼接结果完全一致。四图计划role依次cover/content_summary/real_scene/product_summary，每图layout=single、show_product=true并包含当前版本product_image_ids。所有图片宽:高固定3:4。

FACT_REVIEW、GEO_REVIEW、CONTENT_REVIEW是三个独立提交，每轮check_id要求见review.py和对应提示词；带图仍需单独IMAGE_REVIEW及FINAL_REVIEW实际看图。用户确认字段映射见forms.md。旧Schema中的可选geo仅用于历史快照兼容，新任务执行层强制必需，不能删除字段绕过。
