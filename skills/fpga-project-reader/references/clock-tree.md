# FPGA 时钟树：流程与厂商适配

详细模式默认使用本功能生成独立时钟树；快速模式在用户要求“时钟树、时钟拓扑、PLL 到各模块的时钟分配图”时使用。作为工程阅读的一部分，不另装 skill；定向画图不自动扩大为全工程详细分析。

## 选择来源和视图

1. 沿用所选配置 ID、revision、顶层、器件和快速/详细范围。检查已有编译输入身份；时间戳或成功报告不能单独证明与当前输入匹配。按 [compiled-rtl.md](compiled-rtl.md) 检查已有产物，但**时钟工具视图可以来自综合/布局后时序网表**，不强求 RTL Viewer 阶段。注明阶段和优化后的对象路径。
2. 有匹配的 Vivado/Quartus 工具与已有网表时，按 [clock-tree-vendors.md](clock-tree-vendors.md) 在隔离副本或已有只读会话查询；失败后记录原因并回退。不自动综合、Fitter、改约束或升级 IP。
3. 没有可用工具时，从有效 RTL 实例连线、PLL/MMCM/IP 配置、Qsys/BD 和引用的 SDC/XDC 建立静态模型。正则只定位候选；不承诺自动展开任意 HDL/Tcl、加密内部或所有器件原语。
4. 分开表达 `derivation`（时序分析中的主/派生时钟）与 `distribution`（实际信号分配路径）。只有时钟查询清单时只画前者，不能补画虚构的 PLL、buffer 或消费者。结构路径和时序派生路径可同时存在；PLL 反馈作为 `feedback` 单独记录，不参与 DAG 布局。
5. 可见原语保留厂商类型：Vivado 的 MMCM/PLL、BUFG/BUFH 等；Quartus 的 PLL、clock control、global/regional clock 等。节点的通用 kind 只是绘图角色，不能把 ALTCLKCTRL 改名成 BUFG。一个 PLL 多个输出分别建节点，用 `instance` 关联原实例。

## 证据建模

按 [clock-tree-schema.md](clock-tree-schema.md) 创建 `data/clock-tree.json`。每条连接、每项频率都有独立状态和证据；结构已确认不代表频率也确认。本功能的确认含义遵循 [evidence.md](evidence.md)。

- 外部规格、IP 配置、约束目标、工具时序模型、仿真激励、测量频率分开记录；同一时钟的冲突值全部保留。未知值用 null，不能填 0 或按名称猜。
- 虚拟时钟只属于时序关系视图，不造物理分配边。clock enable 不是新时钟。相同频率、同 PLL、同名信号均不能直接证明同域或异步。
- MUX 保留所有有证据的输入、选择条件和动态模式；门控保留控制说明，不推导无毛刺。动态频率保留各模式/范围，不能无条件计算单一输出。
- consumers 可按明确的实例范围汇总，但写明范围及计数来源；未全量遍历时不能把图中消费者数量称为设计总扇出。CDC 和复位依赖记录于台账；不要作为时钟分配边混入图。
- 来源不清的输入使用 `unknown` 节点并写原因，边的未知状态仍需引用支持“存在未解析连接”的位置。无法定位的缺失用 `missing` 证据及检查范围，不伪造源文件。

## 一次构建与交付

模型/原始查询/哈希/日志置于同一模式 `data/`，可读产物在 `reports/`。多配置使用各自的模式目录或对应配置子目录。示例：

```text
python <skill>/scripts/build_clock_tree.py <mode>/data/clock-tree.json --output-dir <mode>
```

`--project-root` 可在工程移动后覆盖模型记录的根目录。脚本仅用 Python 标准库，校验引用、频率、虚拟时钟、重复边、反馈和组合关系环路，重新核对声明的输入 SHA256；失败时只写 `data/clock-tree-validation.json`，不生成新图。遇到旧的图必须明确其日期；不能把旧图当作本次结果。

输出：

- `reports/clock-tree.svg`：静态图；派生边紫色虚线、分配边蓝色实线，状态在文字中标出。
- `reports/clock-tree.drawio`：可编辑节点与连线。
- `reports/clock-tree.html`：无 CDN、无需服务器的单文件浏览；搜索、派生/分配关系筛选、隐藏/恢复消费者、点击查看证据、缩放。
- `reports/clock-tree.md`：配置、阶段、频率性质、未知/冲突、证据索引和验证边界。
- `data/clock-tree-validation.json`：结构、输入身份、警告、输出哈希与浏览器检查边界。

脚本拒绝覆盖不属于上一次构建清单的文件，或已人工修改的输出；选用新目录保留人工内容。普通本地构建由代理直接执行，所需升级权限遵从环境规则。

从 `OVERVIEW.md` 或 `clock-domains.md` 链接真实生成文件并更新 `INDEX.md`；脚本不覆盖已有导航。已有交互框图保持独立，可互相链接，不能把时钟树替代数据路径框图。源证据在详情中为文本定位，图内嵌 HTML 不自动运行工程 Tcl 或源码。

## 完成检查

- 所选配置和阶段明确；输入哈希仅证明记录范围内输入当前未变，**不自动证明旧编译数据库使用了这些输入**。`identity_match` 需要编译清单/运行身份依据，未确认则保留历史/匹配性未知。
- 每个节点有来源；每条边和频率可追溯，冲突双方可见；虚拟时钟无物理负载；反馈不冒充派生关系。
- 多源 MUX、独立根、孤立/未约束候选和未知源未被静默丢弃；频率相同不合并；未读范围与负载汇总范围可见。
- 打开 SVG/draw.io 检查节点、文字与连线可读；具备浏览器条件时验证离线搜索、筛选、点击和无外部请求。没有运行厂商软件时明确“未进行原生工具验证”，不把 mock 测试称为 Quartus/Vivado 兼容认证。

## 设计参考

参考 [crg-design-gen](https://github.com/siliconpeasant/soc_agent_skill/blob/master/crg-design-gen/SKILL.md) 的“关系数据→校验→布局→可编辑图”思路，脚本与模型为本 Skill 独立实现，不复制或依赖该仓库。实际厂商查询依据下一参考中的官方文档。
