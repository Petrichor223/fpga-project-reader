# 时钟树统一数据（schema_version 1）

供代理根据证据填写；`build_clock_tree.py` 为可执行验证器，不是 HDL parser。文件名/节点 ID 为任意非空字符串，实例路径保留原文；不要把实例路径直接当文件名。

## 最小模型 / context

以下值是格式示意，不能当目标工程事实。`inputs` 的 SHA256 必须由实际字节计算。context 与模型使用相同的顶层字段，但**context 不填 nodes/edges**，交给 `import_clock_query.py` 建立派生图。

```json
{
  "schema_version": 1,
  "source_root": "D:/project",
  "config": {
    "id": "CFG-01", "vendor": "quartus", "project": "demo",
    "revision": "rev_a", "top": "top", "device": "unknown"
  },
  "analysis": {
    "mode": "quick", "method": "static", "stage": "source",
    "identity_match": "unverified",
    "scope": "仅本次追踪的主时钟及代表消费者",
    "limitations": ["未读取编译数据库；未验证 CDC 或板上频率"]
  },
  "inputs": [{"file": "top.sv", "sha256": "实际文件的64位SHA256"}],
  "evidence": {
    "E1": {"kind": "rtl", "file": "top.sv", "locator": "L3 input ref_clk"},
    "E2": {"kind": "missing", "reason": "未提供板卡晶振规格", "checked": "工程说明、顶层和所选约束"}
  },
  "nodes": [{
    "id": "clk:ref", "label": "ref_clk", "kind": "source",
    "status": "confirmed", "evidence": ["E1"],
    "frequencies": [{"value_mhz": null, "basis": "unknown", "status": "unknown", "evidence": ["E2"]}]
  }],
  "edges": []
}
```

`source_root` 相对模型文件所在目录解析；context 相对 context 文件解析，导入后写绝对路径。`--project-root` 可覆盖根路径。inputs/evidence 的 file 可为相对根路径或明确的绝对路径（例如隔离查询目录）。只纳入本次事实所依赖的输入，不在快速模式全盘哈希。

## 字段规则

- `config`：以上六项必填；vendor 为 `vivado` / `quartus` / `other`，不能确认的字符串用 `unknown`。一份模型只对应一项配置。
- `analysis`：mode 为 `quick` / `detailed`；method 为 `static` / `native` / `mixed`；stage 写真实阶段，如 `source`、`elaborated`、`post_synthesis`、`post_fit`、`post_route`；scope 与非空 limitations 说明已读和未验证边界。
- `identity_match`：`unverified` / `historical` / `confirmed`。confirmed 必须有非空 `analysis.identity_evidence` 引用编译输入/运行身份依据。文件哈希当前匹配只说明记录输入没变，不证明旧网表由这些输入编译；只读源码而没有编译产物时保留 unverified 并在 scope 说明静态来源。
- `inputs`：每项 file、sha256；每个非缺失证据的 file 必须纳入其中。构建时重新检查这些字节，过期即失败。
- `evidence`：ID 到定位对象。普通条目含 kind、file、locator（行号、XML 路径、报告章节或 raw clocks 索引）；缺失条目用 `kind=missing`、reason、checked。
- 所有 `status`：`confirmed`（已确认）/ `inferred`（推断）/ `unknown`（未知）。每个节点、每条边、每项频率的 evidence 非空；不同结论不要共享一个泛化状态。

## 节点

`id`、`label`、`kind`、`status`、`evidence` 必填；可加 `instance`、`notes`、`attributes` 原始属性。kind 可用：

| kind | 表达对象 |
|---|---|
| source | 有证据的外部时钟信号来源 |
| clock | 工具定义的运行时钟；不表示已经找到物理原语 |
| pll_output | PLL/MMCM 的单个输出；同一实例多个输出分开建节点 |
| buffer / mux / gate / divider | 实际缓冲 / 多源选择 / 门控 / 分频路径 |
| recovered | 有证据的恢复/收发器用户时钟 |
| consumer | 具体时钟端口或有明确范围的负载汇总 |
| virtual | 无物理目标的时序参考 |
| unknown | 来源/类型未解析的占位节点 |

`frequencies` 数组内每项含 `value_mhz`（正有限数字或 null）、`basis`、`status`、`evidence`；可加 `mode`、`note`（公式、单位、适用条件）。null 必须为 unknown，unknown 值必须为 null；无频率项会显示“频率未知”（consumer 除外）。basis 为：`external_spec` / `ip_configuration` / `constraint` / `tool_timing_model` / `simulation` / `measurement` / `unknown`。冲突值分别保留，不用平均值。周期推导必须确认单位；导入器只对原生 period_ns 计算 `1000/P`。

## 边

每条边必须有 `id`、`source`、`target`、`kind`、`status`、`evidence`；可加 `label` 和 `condition`。condition 写 MUX select、旁路、模式等实际条件，不代表验证了切换安全。

- `derivation`：工具/约束或可复算的主→派生时钟关系，不是电气连接。
- `distribution`：可追溯的时钟连接。多源 MUX 分别连入，不能仅保留默认输入。相同信号别名可放 attributes，避免虚构重复时钟域。
- `feedback`：明确的 PLL/时钟反馈连线；不会参加拓扑排序，仍要独立连接证据。不能把任意环路改标 feedback 来使校验通过。

派生/分配关系合并后必须为 DAG，反馈边单独表示；节点/边 ID 唯一，相同端点/类型/条件不能重复。虚拟节点不允许 distribution/feedback。独立根和孤立节点保留；不假设每个节点都连到某个“系统主时钟”。可在同一模型用不同节点表达时序对象与物理 pin，借 attributes 标注对应关系，不能无证据将它们直接等同。

`query` 为导入器保留的可选原生元数据，含版本、会话、原始 warnings；每个原生节点 attributes 保留原值。没有物理查询证据时不追加虚构分配边。
