# 可展开的工程框图

用于“点击子系统看内部 IP”“收起子系统”“交互层级图”等请求。输出可独立离线打开的 HTML，使用 `assets/interactive.html` 与固定版本的 D3 6.7.0、ELK 0.8.2、d3-hwschematic 0.1.6。资源已随 Skill 打包，不在每次阅读时安装依赖。此能力是**已分析结构的查看器和校验器**，不是通用 HDL elaborator。下文 JSON 是虚构的通用格式示例，不来自具体 FPGA 工程。

## 生成路径

1. 按 [compiled-rtl.md](compiled-rtl.md) 先检查编译数据；身份匹配且可读取时优先采用 RTL Viewer / Analysis & Elaboration 阶段结构。记录实际选用的数据与回退原因，再按当前阅读模式建立可核查的实例、接口与连接。优先使用匹配当前 revision 的厂商层级/网表、Qsys/BD 接口元数据和已有可靠 parser；静态读取生成的综合包装器可作为后备，但保留条件未决、表达式、别名和工具验证限制。历史索引只能定位，复用连接前核对当前输入身份。
2. 写 `<mode>/data/architecture.json`，遵循下方模型。工程架构图默认同时提供下述 `presentation` 板级/总线投影；只查看局部 RTL 时可省略。快速模式只包括已读主路径，可只给一个小子系统内部；未分析的内部不填虚构 children。不要扫描完整工程或全部生成 IP 以填满可展开按钮。

   对已纳入的容器，须核对其直接 IP 清单，不能只收录数据路径上的 IP。存在 Qsys/BD 配置时对照启用组件逐项核查，区分配置组件、综合生成的互连/复位实例和未读的 IP 内部。快速模式可减少解释深度，但不能把默认显示的子集称作完整容器。对“缺少 IP”的反馈先区分未收录、已收录但收起、聚焦范围外和筛选隐藏。
3. 代理运行一次打包器（路径相对 Skill 根目录）：

   ```text
   python scripts/build_interactive.py <mode>/data/architecture.json --output <mode>/reports/interactive.html --validation <mode>/data/interactive-validation.json
   ```

   只依赖 Python 标准库；不读取工程源码、不运行工程脚本、不下载、不调用综合。结构校验失败时修正证据模型，不能删校验或猜测连线以使其通过。未确认的连接可以省略，但须统计并说明缺口。
4. 有本地浏览器自动化条件时，检查代表容器展开、子容器继续展开、重复收起恢复、筛选、搜索以及无外部网络请求。没有浏览器条件时说明“结构校验通过，未验证浏览器交互”；不为此强制安装工具。结构校验不等于连接已通过原生 elaboration。
5. 在 `INDEX.md` 和概览中链接交互 HTML，注明范围与静态/工具验证程度。无需用户手动运行中间 Python；打开 HTML 后的所有点击均在本地完成。只有增加已分析层级或源码改变时才重建。

## architecture.json：v1

顶层字段：

- `schema`: 固定 `fpga-reader-architecture/v1`。
- `title`, `project_root`（绝对路径）, `generated_at`（带时区日期）, `mode`（quick/detailed）, `config`（所选 project/revision/top/device）, `scope`（已覆盖层级、未读/未核验范围）。
- `evidence`: ID 到 `{file, line, sha256}` 的映射；file 是工程相对路径，line 为有效正整数行，sha256 标识**本次读取的文件**。哈希匹配只证明身份，不证明语义。配置身份、宏分支等也应有相应证据。
- `configuration_evidence`: 配置身份所依据的 evidence ID 数组，至少包含所选工程/revision/顶层的来源。
- `root`: 下述递归节点。
- 可选 `coverage`: 容器覆盖数组，每项含 instance、configuration、enabled_components、matched_components、missing_components、rtl_direct_instances、generated_infrastructure、evidence。只记录实际对照结果；有缺失时明确列出，不能用 JSON 自身数量证明完整。可在配置节点标记 configuration_component: true。

节点：

```json
{
  "id": "example_top.example_block",
  "label": "example_block",
  "module": "example_processor",
  "description": "虚构的格式演示模块",
  "status": "confirmed",
  "evidence": ["example-definition", "example-instantiation"],
  "visibility": "analyzed",
  "category": "data",
  "ports": [{
    "id": "sample:input", "label": "sample_in", "direction": "input",
    "members": [{"name": "sample_data", "width": "[15:0]"}, {"name": "sample_valid", "width": "1"}]
  }],
  "children": [],
  "edges": [],
  "clocks": [{"name": "example_clk", "frequency_hz": null, "relation": "示例频率未知", "status": "unknown", "evidence": []}],
  "limits": "包装器内部尚未完成时序或 CDC 验证"
}
```

用**完整实例路径**作为 ID，同一模块的多个实例分别记录。可选 `canvas_label` 是画布上的简短功能名，原始 label/module/id 仍保留。`status` 为 confirmed/inferred/unknown，说明及关联证据须支持该状态；混合事实与功能推断时写清或采用 inferred，不能把名称解释当实现事实。`visibility` 为 analyzed/not_analyzed/encrypted/blackbox/missing；后四者不允许填 children。可见包装器有真实子模块时，包装器记 analyzed，实际加密子节点记 encrypted。

`category` 为 data/control/clock/reset/debug，用于功能配色与连线筛选；**不代表真实时钟域**。完整数据保留全部直接实例；时钟、复位、PIO 默认显示框体及有证据的连接。连线筛选不改变框体；辅助系统 IP 的显隐使用独立开关。复合节点在说明中列多个域。可选 `clocks` 中未知频率用 null，已知频率和派生关系逐项附来源，不能从信号名补值。

接口按真实协议和方向聚合；每个聚合接口列出物理端口 members。原始模型中 AXI/AV-ST 的 data/valid 与 ready、AXI 响应分开对应其真实方向；系统总线视图可以合为一条逻辑线，但应说明箭头是主数据/请求流向，保留反向映射。可选 side 为 WEST/EAST/NORTH/SOUTH：例如输入视频的 data 与反向 ready 都在 WEST，side 决定布局，direction 保留真实方向。若元数据不能确认分组，保留独立端口；只因名字相似不能合并独立总线。缩写 label 可读，完整成员保存在侧栏。双向引脚只有方向和驱动证据充分时才建立连接。

每个 `edges` 属于当前容器，只能连接“容器自身端口 ↔ 直接子实例端口”或“直接子实例 ↔ 直接子实例”：

```json
{
  "id": "example_top.example_block::sample-boundary",
  "label": "sample_in → example_child",
  "category": "data",
  "status": "confirmed",
  "evidence": ["example-child-instantiation", "example-boundary-assignment"],
  "source": {"node": "example_top.example_block", "port": "sample:input"},
  "target": {"node": "example_top.example_block.example_child", "port": "sample:input"},
  "signals": [{"source": "sample_data", "target": "data_in", "net": "sample_data"}]
}
```

每条连接保留源/目标**物理信号名**和对应网络或表达式。容器 input 在内部是源，output 在内部是接收端；直接子模块方向相反。不能跨多层绕开边界端口。折叠与展开共用同一个容器接口 ID；内部真实映射通过上述边界 edges 呈现。简单 assign、位切片、拼接、重命名需要读实现或工具证据，不能靠近似字符串建立连接。IP 裸 CSR 被导出不等于 CPU 已连上。

校验器检查 ID 唯一、证据引用、层级归属、端点存在、方向、物理成员映射及未知频率约束；**不检查证据是否真的支持文字或 HDL 功能**。生成前仍由代理核查实际配置、行号、条件与功能。图不代替 CDC/时序/测试报告。

## 系统架构投影：presentation（v1 可选扩展）

`root` 始终保存真实 RTL 层级和有方向的信号连接；新增 `presentation` 只负责视觉抽象。工程图应先识别板外接口用途，再生成投影，不能从 RTL 实例树期待自动出现传感器、存储颗粒、HDMI 收发器。板外型号取自板卡文档、有效引脚配置或软件驱动，并区分设计意图与硬件实测。

- `presentation.root` 是唯一 `kind: board` 的架构容器，不计入 RTL 数量；其直接子节点包括原始 RTL 根与 `kind: external` 的板外器件。外设不填虚构 children，状态、说明、证据及端口均需明确。只知道接口类型时使用“外部存储器”等名称，型号标未知。
- 每个 RTL 投影节点 `kind: rtl`，沿用原实例 ID、父子关系、说明、状态、可见性及证据，保留每个容器的全部直接子实例。投影的 ports/edges 替换为逻辑接口/总线。不得将可视分组冒充真实实例层级。外设绿色显示，RTL 功能配色；该颜色不代表时钟域。
- 逻辑端口含 `id, label, direction, members, physical_ports, status, evidence`，可选 `side`。`physical_ports` 引用该实例原始端口组的 ID，同一组只能归入一个逻辑接口；`members` 为对应物理成员合并清单。外设端口可无原始 RTL 引用。投影 direction/side 决定主接口的布局，不改写原始信号方向。
- 接口分组优先依据 Qsys/BD 元数据、包装器声明和明确连接。仅在确认属于同一协议接口后，将 data/valid/ready、AXI 请求/响应、DDR 地址/控制/数据归入一条总线。不同视频输入索引、CSR 与数据面、不同独立接口必须保留。不要使用“两个模块之间所有信号合一根”的规则。
- 逻辑总线含 `id, source:{node,port}, target:{node,port}, label, category, flow, status, evidence, member_edges, mappings`。端点仍只允许所有者本身或直接子节点，边界接口在折叠/展开间保持稳定。`flow` 为 `forward`（主数据/请求方向）、`bidirectional` 或 `tap`（被动观察）。`member_edges` 引用该容器的原始 edge ID，允许包含反向握手；这些引用在侧栏还原真实方向和源码。
- `mappings` 用于经人工核查的表达式/双向接口或板级对应，每项 `{source:物理信号名,target:物理信号名,expression:实际表达式或板级对应说明}`。RTL 侧物理信号必须属于选定逻辑接口；板外侧仅为接口角色，未验证封装引脚时不要写成已确认 PCB 网络。没有原始成员的总线必须有此映射及来源。复杂连接只能按实际证据补充，不能因为画图缺线而猜测。
- `presentation.omitted_edges` 为 `{id,reason}` 数组，明确投影没有收录的原始连接。所有原始边必须恰好计入一个逻辑总线或一个遗漏项，不能无声丢失或重复计数。正常优先完整投影，再按类别筛选连线。可选 `show_default: true` 保留架构中必要的配置链路/观察支路，时钟、复位默认连通，PIO 的总线和导出连接可标 show_default；其余控制/调试连接按需开启。
- `presentation.scope` 解释投影范围；可选 `updated_on` 使用实际分析日期。模型生成器应与工程身份核查绑定，重建先核对输入，再重建物理模型及投影，最后打包 HTML。工程特定的接口别名和板卡对应放在该工程 data 生成器中，通用 Skill 不硬编码器件名称。

查看器默认“系统总线”，可切换“接口明细”。点击总线查看全部原始成员和补充映射；展开只改变显示，不调用 Python 或厂商工具。图中过长信号名只在侧栏显示，总线标签使用协议/用途。展开后 IP 多时使用聚焦、缩放与层级树，不通过筛选连线顺带删 IP。

投影校验另外检查 RTL 层级一致、板外器件角色、逻辑端口引用、原始边归属、成员端点以及未计数连接；仍不替代 HDL elaboration。浏览器验证应覆盖板外节点默认可见、粗线减少、反向握手详情、两种视图切换、全部直接 IP 数据保留、辅助 IP 恢复和重复收起恢复。对一个实测工程的适配不代表能自动识别所有工程的板卡器件。

## 时钟、复位、PIO 与辅助 IP

时钟、复位复选框默认开启。保留扇出和正确父子边界，用细线及功能颜色与数据总线区分；只从实际网表、接口声明及 RTL 建立连接。不能因为 PLL/复位框无连线而猜测输出用途；未用端口、常量或未知项在详情说明。

PIO 同时检查寄存器访问总线、时钟复位以及导出端口。可对投影中 PIO 的连接设置 `show_default: true`，使控制线总开关关闭时仍能看见 PIO 接口。没有有效外部绑定时不得从名称猜成 LED/SW/KEY。组合/位切片连接按表达式记录；复位存在顶层计数、门控等行为逻辑时，可用 `relation: logic_dependency` 表达功能依赖并在画布使用虚线，说明“经过 POR/门控，非直接物理连线”，不能替代原始网表线。

sysid/systemid、timer、JTAG UART 等无关当前主路径的辅助系统 IP，可在**投影节点**显式设置 `display_role: auxiliary_system, hidden_by_default: true, hide_reason: 具体原因`。不能仅按“control”类别隐藏所有 IP；时钟、复位、PIO 保留。若 timer 是主功能或复位关键条件，则保留显示。完整 RTL 树、连接和 Qsys 覆盖不删除、不改数量；隐藏节点的连接只在画布随端点隐藏，不重接成不存在的旁路。

“显示辅助系统 IP”恢复节点及其连接；树和侧栏仍列全部实例并标明默认隐藏，搜索或选中可单独恢复。状态栏分别显示收录数量、画布数量和隐藏数量，不能把隐藏项计成缺失。浏览器检查至少验证一个时钟、复位、PIO 有可见连线，隐藏项可恢复且查询覆盖数量不变。

## 查看器行为与大工程

有架构投影时初始展开板级容器与 FPGA 顶层，显示板外器件和主要逻辑总线；只有物理模型时展开 RTL 顶层。两者均保留全部顶层实例数据，默认显示主要数据与时钟复位通路；在画布点击容器，或在左侧树点击 `+`/`−` 可展开收起。有两级展开、窗口适应、搜索、控制/时钟复位/调试**连线**筛选。显示已收录/当前展开数量，树与侧栏列出容器全部直接实例及配置覆盖。选中节点后使用“聚焦选中模块”单独查看该子系统，“全工程 / 初始视图”返回总览；搜索并选择范围外实例时须恢复可见的祖先路径。点击名称查看功能、完整实例路径、端口成员与证据；点击连线查看实际信号映射。颜色代表功能类别，未知或不透明实现使用虚线。

页面切换已打包层级，不动态解析源码或运行新分析；快速模式未打包的内部始终明确标为尚未分析。大工程优先按数据/控制和辅助信号分层，使用总线接口代替逐根线，保持可读；详细数据很大时可按真实子系统拆多份独立页面，并用导航连接，不能把全部细节强行展开到一张图里。

单文件 HTML 内嵌 JSON 和运行库，不使用 fetch/CDN/远程字体。原始文件仍放在 data 以便重建；许可证随资源与 HTML 保留。动态文本用 textContent，不能拼入可执行 HTML。打开证据链接需源码仍位于所记录路径；旁边始终显示路径与行号。修改源码后应重读受影响配置/接口再生成，不能只更新时间。
