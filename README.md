# GEO图文生产助手

完整可安装技能，技术标识`geo-article-studio`，默认产品名 **218轻便侠**。支持具备文件、Python执行和人工确认能力的不同Agent，Qwen为优先模型选项，图片使用用户配置的第三方API。

启动词仅为 **开始任务** 和 **配置任务**。配置任务统一包含图片API，密钥只在本地接入；开始任务后选择学习/自动模式。

- [完整源码与开发命令](geo-article-studio/README.md)
- [多Agent安装与兼容性](geo-article-studio/docs/多Agent安装与兼容性.md)
- [首次配置](geo-article-studio/docs/安装与首次配置.md)和[日常操作](geo-article-studio/docs/日常操作示例.md)
- [v1.3可安装ZIP](dist/geo-article-studio-1.3.0.zip)和[SHA256](dist/geo-article-studio-1.3.0.zip.sha256)
- [本次更新与测试](geo-article-studio/docs/v1.3更新与测试.md)和[已知限制](geo-article-studio/docs/已知限制.md)

四库按需检索，人工多选主题并逐篇填写图数，学习模式确认、修改、复盘和规则持久化，自动模式完成配置后连续生成和独立审核。成品逐篇独立目录，标题TXT、正文TXT和实际图片分别保存。

四库路径、产品资料、完整规则、图片协议均在首次运行配置。密钥只通过本地环境或宿主安全凭据接入。仓库不包含真实资料、运行任务、环境或密钥。

兼容安装不代表所有Agent实机通过。当前有有限Codex及Hermes交接证据，Claude Code真实会话和真实图片API尚未验证。详细范围以测试记录为准。

开始任务后，每次选择当前Agent默认模型或已提前配置的第三方文字API。[文字模型配置与选择](geo-article-studio/docs/文字模型配置与选择.md)说明持久化、密钥接入和费用边界。
