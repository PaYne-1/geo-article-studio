# v1.4.0 最终发布包安装验证

验证日期：2026-09-15；Windows、Python3.11.16。

- 包：geo-article-studio-1.4.0.zip，204636字节，86个文件（含manifest.sha256）。
- SHA256：9e74df67135058b433e26fb6789e46772fbe2308a03c7aa4d9f981a6e8424472。
- manifest逐文件SHA256及与构建时源码逐字节一致性：实际校验通过。
- ZIP不包含真实.env、settings.json、state.json、虚拟环境或缓存；常见凭据模式扫描0命中（不是对所有秘密形式的保证）。
- 最终源码全量测试：151 passed in 53.65s，0失败、0跳过。
- 最终ZIP隔离安装成功：技能和运行数据使用两个独立目录；安装器没有自动安装依赖，测试使用已有项目Python环境。
- 从最终安装副本执行全量测试：151 passed in 54.04s，0失败、0跳过；[完整输出](geo-article-studio-1.4.0.installed-tests.txt)。
- compileall、SKILL quick_validate和Git diff空白检查通过。

安装目录：D:\0-AI 项目\GEO\artifacts\zip-install-v1.4-final\skills\geo-article-studio。
测试工作目录：D:\0-AI 项目\GEO\artifacts\zip-install-v1.4-final。
独立运行数据：D:\0-AI 项目\GEO\artifacts\zip-install-v1.4-final\data。

13项新GEO用例涵盖原题/需求、结构/字数、真实来源ID门、三轮审核顺序、学习中连续修改与复盘、默认宿主路径、本地文字HTTP路径与四张图片独立HTTP下载/落盘。其他138项为既有模块和历史任务兼容测试；不把151项都称为新标准专用测试。

**测试性质：离线模拟和本地HTTP。** 模型返回及视觉判定为脚本，图片为Pillow测试图。Hermes v1.4真实完整任务、其他Agent真实生产会话、真实第三方文字API、真实第三方图片API均未执行；历史有限联调记录不能代替本版本验收。

完整变更、操作与边界见[版本说明](../geo-article-studio/docs/v1.4更新与测试.md)。本文件在最终包完成安装测试后生成，位于发布包旁，不计入ZIP内部manifest，避免测试报告与其所指包的哈希相互依赖。
