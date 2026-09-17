# 执行状态

新任务：PREFLIGHT → ANALYZING → WAITING_SELECTION/WAITING_COUNTS → PLANNING → WRITING → FACT_REVIEW → GEO_REVIEW → CONTENT_REVIEW → IMAGE_PLANNING → GENERATING_IMAGES → IMAGE_REVIEW → FINAL_REVIEW → EXPORT。ANALYZING可对完全相同且已验证的输入执行reuse-analysis，省去重复模型分析；来源、事实、规则、配置、需求或编辑标准变化时失效。人工选题与各篇数量不可跳过。零图跳过三个图片阶段。每篇EXPORT后自动处理下一篇；全部校验发布后COMPLETED。旧任务无editorial_version时仍使用TEXT_REVIEW，refresh后升级。

学习模式在预检、当前篇策划、正文及独立自审、配图计划、实际图片审核、最终审核后WAITING_APPROVAL。主题与数量由select提交即批准选题配置。修改保留旧结果/审批历史并清理受影响结果，不能越级。

新任务在开始表单确认目标、平台、目标AI和short/long。ANALYZING从聊天库的真实客户关注中生成问题型钩子标题候选；用户在WAITING_SELECTION人工多选即确认标题，执行层把选中topic.question_summary写入每篇geo_brief.original_title，并拒绝不一致的替换标题。PLANNING先给核心答案和固定大纲，WRITING通过结构/字数检查后依次进入三个独立审核动作；学习模式每轮等待人工批准。正文修改回PLANNING重新策划，但正文反馈等CONTENT_REVIEW通过后才进入LEARNING_REVIEW复盘与确认，批准大纲不等于正文反馈完成。

自动模式仍等待用户选择和逐篇数量；其余NEEDS_MODEL由宿主在当前会话执行，不让用户手工填JSON。独立审核失败有上限地修正文本，图片关键失败/UNKNOWN/预算上限暂停。局部问题默认pause_all；本版本不支持自动跳过失败篇目，已有完整篇保留并报告未完成。

PAUSED保存resume_state；pause marker在请求期间可持久化，已发出请求不假称取消。resume校验快照/文件哈希；未知收费先核实再resolve-request，成功下载可recover-image。refresh在明确用户输入后重建预检，重新选择数量；原发布目录保留。已完成修改fork-revision另建任务。
