# 执行状态

PREFLIGHT → ANALYZING → WAITING_SELECTION/WAITING_COUNTS → PLANNING → WRITING → TEXT_REVIEW → IMAGE_PLANNING → GENERATING_IMAGES → IMAGE_REVIEW → FINAL_REVIEW → EXPORT。零图跳过三个图片阶段。每篇EXPORT后自动处理下一篇；全部校验发布后COMPLETED。

学习模式在预检、当前篇策划、正文及独立自审、配图计划、实际图片审核、最终审核后WAITING_APPROVAL。主题与数量由select提交即批准选题配置。修改保留旧结果/审批历史并清理受影响结果，不能越级。

自动模式仍等待用户选择和逐篇数量；其余NEEDS_MODEL由宿主在当前会话执行，不让用户手工填JSON。独立审核失败有上限地修正文本，图片关键失败/UNKNOWN/预算上限暂停。局部问题默认pause_all；本版本不支持自动跳过失败篇目，已有完整篇保留并报告未完成。

PAUSED保存resume_state；pause marker在请求期间可持久化，已发出请求不假称取消。resume校验快照/文件哈希；未知收费先核实再resolve-request，成功下载可recover-image。refresh在明确用户输入后重建预检，重新选择数量；原发布目录保留。已完成修改fork-revision另建任务。
