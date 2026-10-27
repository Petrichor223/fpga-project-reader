# 厂商 IP、系统集成与混合语言

## VHDL 与跨语言绑定

区分 entity、architecture、package/body、configuration、component declaration 和 component instantiation。component 声明本身不是实例，也不证明已经绑定。读取库映射、`work` 的实际库上下文、use/context、direct entity instantiation、configuration/binding，以及 generic map/port map。

实际顶层和库的编译顺序决定可见定义。存在多个 architecture 时不能从文件名或目录顺序猜选中的实现；记录直接绑定或工具结果，否则标绑定未知。Verilog 的大小写规则与 VHDL 不同，跨语言时以工具绑定结果/相应规则核查，不做全局小写归一化。

泛型依赖位宽、数组方向、record/interface 边界、signed/unsigned、整数范围和类型转换可能影响跨语言接口。接口形状能确认不代表模拟/综合工具都支持相同绑定；无法展开的包装和转换层写清楚。

## Vivado Block Design 与 Xilinx/AMD IP

- 关联 `.bd`、生成 HDL wrapper、顶层选择、XCI/XCIX、IP 输出产物和工程文件集；旧生成 wrapper 不一定匹配当前 BD。
- 读取 BD cells、接口/port/net、地址空间、clock/reset 连接与配置属性；区分 interconnect、converter、processor、memory 和用户模块。
- IP 的身份记录实例路径、VLNV/版本（可见时）、配置文件、生成状态、仿真/综合模型、网表/checkpoint、约束和可见源码。
- 对 Clocking Wizard、Processor System、MIG、GT 等，只解释配置与可见连接能支持的行为。PS 输出时钟与复位还可能依赖启动软件或运行时配置，不能只按 GUI 默认值确认板上运行状态。
- 将 BD 高层结构图与生成 RTL/综合网表层级分别展示，给出对应关系，避免重复统计或把 wrapper 当成整个系统的全部逻辑。

## Quartus Platform Designer 与 Intel/Altera IP

- 关联 `.qsys/.ip`、`.qip`、生成 HDL、仿真文件清单和所选 revision 的 QSF 引入链。
- 提取组件名/版本/参数、Avalon/AXI 接口、地址映射、clock/reset connection、导出接口以及 clock bridge/reset controller。
- 不同生成变体或 synthesis/simulation 子目录可能使用不同模型。以所选文件集确定实际使用的生成文件，未生成目录不代表组件没有配置，也不证明可成功展开。
- 对 PLL、EMIF、PCIe、收发器等记录参考时钟、输出/用户时钟的配置依据和动态模式限制；内部实现不可见时不补造细节。

## 黑盒与不可见实现

每个 IP 使用可见性状态：`源码可见`、`仅接口/配置可见`、`仅网表/checkpoint`、`加密`、`缺失/未绑定`、`仿真替代模型`。列出依赖库、许可证/工具约束（有证据时）和受影响的分析结论。

接口 stub 能证明声明接口，通常不能证明内部功能、流水线深度、CDC 或真实复位行为。加密代码不尝试绕过保护。可以引用匹配版本的厂商手册来解释公开行为，但标明“文档规定”及所选参数，不将其冒充源码观察。

缺失 IP 时继续分析可见父级和其他模块，明确层级在何处中断；不要自行下载其他版本、自动升级 IP 或以同名开源模块替换。初始化文件（ROM/RAM `.mem/.mif/.hex/.coe` 等）缺失会限制功能解释，即使 HDL 可展开也要记录。
