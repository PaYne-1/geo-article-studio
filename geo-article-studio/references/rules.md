# 规则导入、学习及回滚

技能自带用户确认的GEO编辑规则，可直接用于生产。外部自定义规则为可选扩展：导入JSON包含formal=true、真实version与非空rules数组，每条包含rule_id/scope/target_id/type/content/check_method/severity，词语禁用可加terms。config/rules.example.json示例标example=true，不能生产导入。原有TXT/MD禁限表可由当前模型按来源逐条整理为候选JSON，用户核对完整性后正式导入，不把示例表当法规全覆盖。

scope为article/topic/product/style/global；type为hard_ban/conditional/writing_preference/image_preference/product_structure。article/topic还需绑定task_id，不能把A001带入下一任务。偏好不能发明参数或覆盖禁用。

`rules import --file FILE --user-ref REF`记录来源路径、hash、版本及用户输入；`rules show`查看。`revise`立即把反馈约束当前对象，自动保存proposed规则；`approve --rule-ids ID`同时人工批准当前结果和明确展示的规则。不传rule-ids则仅批准结果，长期规则继续待审。

每次修改记录feedback_id、对象、旧新版本、问题、原因(未知则待验证)、措施、建议规则范围、检查方法、生效状态与确认时间。具体语义复盘由当前模型按prompts/learn_from_feedback.md解释；程序保存必要审计，无模型权重训练。

冲突规则可指定conflict_key，同范围同键不同内容需显式解决；确定性冲突检查不声称能识别全部语义冲突，审核动作仍必须检查。`rules rollback --version N --user-ref REF`创建新的历史版本，不能无痕删除规则。活跃任务碰到规则版本变化阻断，用户refresh重新预检复审。
