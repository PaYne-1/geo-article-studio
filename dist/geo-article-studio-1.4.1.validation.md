# v1.4.1 最终ZIP安装验证

日期：2026-09-15。Windows、Python3.11.16。

- geo-article-studio-1.4.1.zip：215232字节，90文件（含manifest.sha256）。
- SHA256：db0820ddec768c652b2d4d51884bff67dfae65432a66442f2b40a44a34774e7a。
- ZIP完整性、manifest逐文件SHA256及构建时源码逐字节一致性：通过。
- 未打包真实.env、运行settings/state、缓存或虚拟环境。常见凭据模式扫描0命中，不代表能识别所有秘密形式。
- 源码全量：158 passed in 47.85s；最终中文标注调整后配置专测7 passed in 1.57s。
- 最终ZIP安装副本全量：158 passed in 54.01s，0失败、0跳过；[完整输出](geo-article-studio-1.4.1.installed-tests.txt)。
- 实际执行compileall、技能quick_validate和Git diff空白检查：通过。

独立安装位置：artifacts/zip-install-v1.4.1/skills/geo-article-studio；运行数据分离在artifacts/zip-install-v1.4.1/data；从安装副本测试，使用项目已有Python虚拟环境，安装器未自动安装依赖。

新增7项配置行为测试计入158总数，分别验证字数字段移除、条件要求与技术参数归属、字段状态、已有规格保持、跨进程部分保存、中文表单输出、无网络访问及密钥值不输出。其余为既有GEO生产及历史兼容回归。独立只读代码复核亦运行13项相关测试通过，未重复计入总数。

**分层范围：** 本轮真实执行本地CLI、文件保存/回读、离线测试、既有本地HTTP模拟及隔离ZIP安装。Hermes真实任务、其他Agent真实生产会话、真实第三方文字API和真实第三方图片API均未执行。

升级说明与已知限制见[修复记录](../geo-article-studio/docs/v1.4.1配置表修复与测试.md)。用户未知位置的旧安装副本未自动更新，需要安装新版并重新加载技能；复用原独立数据目录保留配置。

本报告在最终ZIP测试后生成，位于包外并绑定上述哈希。
