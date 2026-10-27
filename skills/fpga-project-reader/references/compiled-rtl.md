# 框图生成前的编译数据优先级

生成工程框图前先检查所选 project/revision 的已有编译产物，优先使用 **RTL Viewer 对应的 Analysis & Elaboration 阶段**结构；该检查适用于快速与详细模式，不自动扩大阅读深度。

## 发现与选择

可运行 `scripts/find_compiled_rtl.py <project> --revision <revision> --output <mode>/data/compiled-rtl-discovery.json`。它只列出常见 Quartus 报告、DNI elaborated 检查点和 qdb 目录，不打开数据库、不运行综合，也不证明输入新鲜度。非默认输出目录、不同版本检查点、已有人工导出文件另按工程配置查找，不把脚本未找到等同于不存在。

1. 先读报告与编译配置：确认工具版本/edition、project、revision、top、device、阶段是否成功。对照宏、参数、文件集与当前输入；有编译输入清单/哈希时逐项核对。时间戳只能辅助，报告“成功”不能证明对应当前源码。缺少输入身份记录时注明未确认，不能把历史网表称为当前完整事实。
2. 若有与当前身份匹配的 RTL 阶段网表导出或可读数据库，优先用它建立实例、generate/参数展开、端口及连接；按本次阅读深度选取所需子系统。以实际工具对象 ID/路径关联源码，不强行将综合后重命名对象映射为原 RTL。
3. 原生数据库需要匹配版本 Quartus。先查安装版本和本地命令帮助，使用只读查询或隔离副本，记录命令、所选检查点、输出和限制。不能把二进制数据库当文本搜索，也不将 Standard 的原子网表接口直接套用 Pro/DNI。内部命令无稳定适配保证；工具崩溃、版本不匹配或数据库打不开时停止该路径，不反复试错或触发重编译。
4. 有工具报告但没有连接导出时，报告仅用于它实际包含的配置/层级/警告，连接回退到当前 Qsys/BD 和综合包装器/RTL。只有后综合/后布局网表时明确标注阶段，不能改称 RTL Viewer 阶段；优化丢失层级时用源码补功能关系并区别推断。
5. 在报告和模型 `diagram_source` 中写明实际采用来源、阶段、身份核对范围与回退原因。机器发现清单放 data，不能把“找到 RTL 数据库”写成“已导入 RTL Viewer”。板外器件仍需顶层引脚、板卡资料或驱动证据。

## 验证边界

编译数据库能提高配置/实例/连接的可靠性，不提供板外 PCB 完整结构、加密 IP 源码或功能正确性证明。无需截图也可能读取底层数据；只有截图时结论限于可见部分。成功读取一个版本不承诺其他版本自动兼容。默认不重新执行 Analysis & Elaboration、完整编译、迁移或升级 IP。

Quartus 官方阶段说明：[RTL Viewer](https://docs.altera.com/r/docs/683641/25.3.1/quartus-prime-pro-edition-user-guide-design-optimization/rtl-viewer-overview?contentId=9mhY_sT~ftJ5qG6OEMsTkA)。
