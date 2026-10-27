# Vivado / Quartus 时钟提取

两种适配器只查询**已打开且已准备好时序模型**的会话。不打开/修改工程，不加载约束，不触发编译，不把时钟对象列表解释为完整物理网络。先查本地版本与 `help`/`-long_help`；脚本中的属性不支持时记录 warning，不跨厂商套用命令。

## Vivado

在匹配配置的已打开 elaborated/synthesized/implemented design 或已有 DCP 副本中，确认设计、约束与阶段。在 Tcl Console 中设置绝对输出路径后 source：

```tcl
set fpga_reader_clock_export {D:/reports/quick/data/vivado-clocks.json}
source {<skill>/scripts/export_vivado_clocks.tcl}
```

导出 `get_clocks` 对象的 NAME、PERIOD、WAVEFORM、IS_GENERATED、IS_VIRTUAL、MASTER_CLOCK、SOURCE、SOURCE_PINS、倍分频、反相和边沿变换属性。`SOURCE_PINS` 是时钟定义目标，不是所有负载；MASTER_CLOCK 只证明时序模型派生关系。属性查询缺失为 warning；不从 cell 名猜原语。

如需要真实分配节点，另在该阶段查询对象连接，结合 `report_clock_networks` 和网表中 pin/net/cell 路径核查。注意标准 `report_clock_networks` 文本不包含 GUI 的完整树，不能把 roots-only 文本当完整网络导入。PLL 反馈、MUX 多源和优化后的节点需分别处理。

官方依据：[UG912 CLOCK 属性](https://docs.amd.com/r/en-US/ug912-vivado-properties/CLOCK)、[UG906 Clock Networks](https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/Report-Clock-Networks)。

## Quartus Prime / TimeQuest / Timing Analyzer

从所选 `.qpf`/`.qsf` revision 确认顶层、器件、宏、有效 `.qip`/`.ip`/`.qsys` 与 `.sdc`。PLL/clock control IP 的频率和输出连接须核对实际生效实例。已有编译数据库必须匹配 edition、版本、revision、阶段及输入；Pro/DNI 不能直接使用 Standard 原子网表接口。

在 Timing Analyzer 中准备好已有 timing netlist、读入当前有效 SDC 并更新后，再执行：

```tcl
set fpga_reader_clock_export {D:/reports/quick/data/quartus-clocks.json}
source {<skill>/scripts/export_quartus_clocks.tcl}
```

会话准备不是导出脚本的副作用。无已有网表时不自动编译；`read_sdc` 可执行项目 Tcl，只能对已审阅/可信约束或隔离副本操作，保留相关日志。不要额外执行 `derive_pll_clocks` 改变本来没有的约束来美化图；所选版本/器件可由工具自动推导的时钟以实际查询为准。

适配器用 `get_clocks`、`get_clock_info` 导出名称、type、period、waveform、master clock、倍分频和 phase 等。`-targets` 返回集合，需要 `foreach_in_collection` 和 `get_node_info -name` 解引用；不能把集合句柄当作引脚名。虚拟类型含 `virtual_base` / `virtual_generated`。

更完整的结构查询使用 **Report Clock Network**（与 `report_clocks -hierarchy` 的主/派生层级不同）；按当前版本 GUI 给出的 Tcl 命令保存网络报告。该报告展示输入时钟、MUX/门控/分频及负载，Clock Network Viewer 可查看图形并导出 PDF。自动提取中间分配节点需依据该版本导出内容或受支持连接查询另行建模；本 Skill 不声称 raw clocks 导出已经包含这些节点。

官方依据：[get_clock_info](https://www.intel.com/content/www/us/en/programmable/quartushelp/current/tafs/tafs/tcl_pkg_sta_ver_1.0_cmd_get_clock_info.htm)、[report_clocks](https://resources.altera.com/quartushelp/current/tafs/tafs/tcl_pkg_sta_ver_1.0_cmd_report_clocks.htm)、[Clock Network 与 Viewer](https://www.intel.com/content/www/us/en/docs/programmable/683243/23-3/report-clocks-and-clock-network.html)。版本差异以本地帮助为准。

## 原始导出 → 统一模型

两个 Tcl 入口输出 `fpga-clock-query-v1`，所有属性原值保留为字符串；list 字段是 JSON 数组，错误保留在 warnings。都使用同目录 `clock_query_common.tcl`，无需额外 Tcl 包。空时钟集可以导出，但不能据此断言设计无时钟。

代理先按 [clock-tree-schema.md](clock-tree-schema.md) 准备 context JSON，填写配置、输入哈希、证据和范围；再执行：

```text
python <skill>/scripts/import_clock_query.py <mode>/data/quartus-clocks.json --context <mode>/data/clock-context.json --output <mode>/data/clock-tree.json
python <skill>/scripts/build_clock_tree.py <mode>/data/clock-tree.json --output-dir <mode>
```

导入只生成**时钟派生视图**，频率性质为 `tool_timing_model`。父时钟缺失时生成未知来源节点；查询缺失 type 不当作 primary；不会生成 PLL 实例、内部缓冲或消费者。保留 raw 对象属性便于追加静态/网络证据；collector 的 `session` 与 context 的 project/revision/top/device 不一致时拒绝导入，无法查询的字段列 warning。阶段与编译输入匹配性由 context 及证据负责，不能由导入成功推导。

## 无工具回退

代理阅读并建立相同 schema，`method=static`、`stage=source`。无法求值的 Tcl/generate、缺失 IP、动态重配置、恢复时钟比例和仿真替代实现分别列入 limitations。保留约束频率与 IP 配置频率的冲突，不静默择一；不读取二进制 `.qdb`/DCP 为文本、不执行任意工程脚本猜结果。
