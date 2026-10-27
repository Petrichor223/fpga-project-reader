# 工程配置与有效构建集合

## 发现入口

先建立候选配置矩阵，再深入有效构建。以下是识别线索，文件存在本身不证明使用该厂商或目标：

| 工具/入口 | 常见材料 | 需要确认 |
|---|---|---|
| Vivado | `.xpr`、工程/非工程 Tcl、`.xdc`、`.xci/.xcix`、`.bd` | part/board、source/simulation/constraint sets、各 set 的 top、宏和 include、文件 used-in/enabled 状态、run 对应的 set、IP/BD 输出产物 |
| ISE | `.xise`、`.prj`、`.ucf`、构建脚本 | device/package/speed、实现/仿真源角色、top 和库、生成核 |
| Quartus | `.qpf`、各 revision 的 `.qsf`、`.qip/.ip/.qsys`、`.sdc`、Tcl | project revision 列表与实际选择、family/device、top、文件 assignment、宏/include/library、IP 递归引入、TimeQuest 约束 |
| Lattice/其他厂商 | `.ldf/.rdf/.prj`、`.lpf/.pdc/.sdc/.cst`、厂商 XML/Tcl | 工具身份、implementation/strategy、器件、源集合、top、有效约束和 IP 配置；不确定字段先查相应版本文档 |
| 通用构建/仿真 | Makefile、shell/PowerShell/Python、`.f/.flist`、FuseSoC `.core`、Bender 清单、仿真脚本 | 选定 target、工作目录、变量/环境、编译器参数、库映射、递归清单、覆盖参数 |

搜索隐藏目录和生成目录时有选择地展开：通常先跳过缓存、版本控制和旧输出以节约搜索，但若有效清单引用其中的文件，必须纳入。不要按 `backup`、`old`、`test` 等目录名直接判定失效。

## 解析配置

1. 追踪实际构建入口及调用链：用户命令/CI target → 工程/revision → 文件集/清单 → 递归 include/source/IP。多个可用 revision 不代表都已被本次构建使用；列表顺序、文件时间不能替代选择证据。
2. 记录命令行、环境变量、脚本参数、工程属性和默认值的覆盖关系。未提供构建命令时明确区分“声明了哪些配置”与“当前使用哪个配置”。
3. 根据各文件格式/命令的路径语义解析相对路径；记录引入者和基准目录。不要把所有路径都机械地相对根目录解析。保留路径含空格、大小写敏感库名和跨平台路径转换信息。
4. Tcl/QSF 是可执行语言；静态字符串扫描不能可靠计算变量、glob、循环或条件。能确认的 assignment 记录来源；不能求值的分支标“未解析”。原生查询可用时在隔离副本中校核，不要为读取配置直接执行未知副作用的脚本。
5. 按综合、实现、仿真分别确认文件角色。include 头文件、package 和 IP 元数据不是单独编译单元；约束的处理顺序、scoped-to、used-in、启用状态也影响适用范围。

## 文件清单与激活状态

每项记录 `配置 ID | 路径 | 角色 | 激活状态 | 库/编译顺序 | 引入链 | 证据`。

角色包括设计源、仿真源、头文件、package、约束、IP 配置、生成源、网表/checkpoint、初始化数据和脚本。

激活状态使用：

- **纳入**：该配置明确引入且条件已解析。
- **排除**：有显式禁用、条件不成立或其他直接证据。
- **未引用**：在已解析范围的清单中未被引入；不直接称为“废弃”。
- **条件未决**：动态选择、变量/宏未知或依赖缺失。

“纳入编译”与“顶层可达”分开：清单可包含未被实例化的库模块；被实例化的 include 定义又可能不作为单独编译文件出现。列出仿真替身、stub 与真实实现的选择条件，防止把它们同时绑定到同一实例。

## 顶层、参数与展开

- 综合顶层、仿真顶层、BD wrapper、test DUT 和板级 top 各自记录；工程名或文件名不能代替顶层配置。
- 保存 Verilog/SV defines、`ifdef` 分支、include、package、parameter override、generate 的条件和展开次数。宏可能对编译单元或文件顺序敏感。
- 保存 VHDL 库、entity/architecture、configuration、generic 和绑定规则；同一 entity 可能选择不同 architecture。
- 参数依赖不确定时保留表达式及其来源，不伪造实际位宽、实例数和功能分支。
- 工具展开失败时，保留已确认的部分层级，记录出错文件/位置、缺少库/IP、未解析表达式；其下节点不可宣称完整。

## 原生工具校核

如有匹配版本的工具，可查询工程属性、文件集/编译顺序、顶层、revision、宏/include/library、elaborated design、IP 状态和约束启用信息。查询语法先用本机帮助或官方文档核对。

记录运行阶段及是否读取当前保存状态。单纯读取元数据的结果可确认配置声明；只有实际展开成功且输入匹配，才确认工具解析的实例拓扑。不能把“打开工程成功”写成“编译通过”。
