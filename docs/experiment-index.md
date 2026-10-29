# 实验与结果索引

本索引区分最终完整运行、失败重复、中断运行、材料对照和未采用候选。所有原始报告保持原状；`passed` 仅表示对应脚本的检查通过，不表示所有物理检查均通过。

最终选定参数：熊内部边柔度 **0.01 m/N**、表面边柔度 **0.001 m/N**、形状阻尼 **20 s⁻¹**、轴向阻尼 **40 s⁻¹**，布膜每次 **24 sweeps**。

## 最终交付与验收边界

- 最终交付：[runs/plush-cotton-complete-01](../runs/plush-cotton-complete-01/)。原始完整运行：[full-03](../experiments/material-development/full-03/)。二者 `report.json` 哈希相同。
- 完整运行 `report.status=passed`，退出码 0，7197 步、总仿真时间 **71.97 s**；日志 **71.47 s** 是进入 `thread_arms` 阶段的时刻。
- 原样独立验收 **23/24** 项通过：头部水平位移 **51.7102 mm** 超过 **50 mm** 阈值。严格保存状态和录像采样零翻转检查均失败。不能将其描述为全部物理健康检查通过。
- 相同冻结源码的 `full-03-physics` 无渲染重复失败，应与最终完成运行同时保留，不能视为成功复现。

## 目录分类

下表目录均相对仓库根目录。源码核对仅覆盖原报告记录的哈希；详细逐文件结果见 [experiment-index.json](experiment-index.json)。

| 结果目录 | 分类与状态 | 用途、限制 | 源码证据 |
|---|---|---|---|
| `experiments/material-development/full-03` | selected_completed_dressing_run / passed | 最终选定的完整穿衣运行：report passed、exit 0；独立验收23/24，头位移51.7102mm超过50mm，且严格零翻转检查失败。 | 32/32 项匹配；`experiments/material-development/full-03/source-at-run` |
| `experiments/material-development/full-03-physics` | failed_repeat / failed | 相同源文件与参数的独立 --no-render 重复；52.66s左侧找不到可通过真实布孔的可达抓取，exit 1，未完成。 | 32/32 项匹配；`experiments/material-development/full-02-source` |
| `experiments/material-development/full-02` | interrupted_run / starting | 同最终参数的早一次全流程，工具长会话终止；report保留starting，最后checkpoint16.35s，日志至step1700，不能视为完成。 | 32/32 项匹配；`experiments/material-development/full-02-source` |
| `experiments/material-development/shape-20` | selected_material_benchmark / passed | 最终 .01/shape20/edge40/膜24 的对向支撑压缩释放与布悬垂小实验，passed；不是穿衣流程。 | 16/16 项匹配；`experiments/material-development/shape-probe-source` |
| `experiments/material-development/local-original` | original_material_control / failed | 最终对照采用的原材料、对向支撑夹具；完成测试，但1个瞬时倒置使no_inverted_tetrahedra失败。 | 13/13 项匹配；`experiments/material-development/local-probe-source` |
| `experiments/material-development/shape-8` | unselected_candidate / passed | 内部柔度.01、shape阻尼8/s候选，bench passed；未采用。 | 16/16 项匹配；`experiments/material-development/shape-probe-source` |
| `experiments/material-development/candidate-003` | unselected_candidate / passed | 内部柔度.003、shape20/s候选，bench passed；未采用，实际配置为tested-config.toml。 | 16/16 项匹配；`experiments/material-development/candidate-003-source` |
| `experiments/material-development/local-40` | unselected_candidate / passed | 对向支撑：内部柔度.003、轴向40/s、shape0、膜4，bench passed；未采用。 | 16/16 项匹配；`experiments/material-development/local-probe-source` |
| `experiments/material-development/local-1600` | unselected_candidate / passed | 对向支撑：内部柔度.003、轴向1600/s、shape0、膜4，bench passed；未采用。 | 16/16 项匹配；`experiments/material-development/local-probe-source` |
| `experiments/material-development/local-soft-interior` | unselected_candidate / passed | 对向支撑：内部柔度.03、轴向40/s、shape0、膜4，bench passed；未采用。 | 16/16 项匹配；`experiments/material-development/local-probe-source` |
| `experiments/material-development/damping-400` | unselected_candidate_early_protocol / passed | 早期单侧腹部压入：内部柔度.003、轴向400/s、shape0、无膜限幅，bench passed；未采用。 | 15/15 项匹配；`experiments/material-development/probe-source` |
| `experiments/material-development/damping-1600` | unselected_candidate_early_protocol / passed | 早期单侧腹部压入：内部柔度.003、轴向1600/s、shape0、无膜限幅，bench passed；未采用。 | 15/15 项匹配；`experiments/material-development/probe-source` |
| `experiments/material-development/membrane-12` | component_diagnostic / 无独立状态 | 布膜12sweeps的2.5秒悬垂诊断，非最终24sweeps。 | `experiments/material-development/membrane-sweep-source` |
| `experiments/material-development/membrane-24` | component_diagnostic / 无独立状态 | 布膜24sweeps的2.5秒悬垂诊断，用于选择迭代次数；不是完整动作。 | `experiments/material-development/membrane-sweep-source` |
| `experiments/material-development/membrane-diagnostic-24` | component_diagnostic / 无独立状态 | 24sweeps逐阶段残差诊断，包含额外一次投影的离线度量。 | `experiments/material-development/membrane-sweep-source` |
| `experiments/material-development/membrane-small` | component_diagnostic / true | 四点布片小测试，passed=true；验证质量中心、固定点及压缩不受限。 | 无完整独立快照 |
| `experiments/material-development/membrane-final-small` | component_diagnostic / 无独立状态 | 仅保留生成的四粒子布网格；目录无独立结果报告，不能认定为通过。 | 无完整独立快照 |
| `experiments/early-tests/bear-material-original-01` | original_control_early_protocol / failed | 早期单侧夹具原材料对照，完成但1个倒置使检查失败；不同于最终对向夹具。 | 10/10 项匹配；无完整独立快照 |
| `experiments/early-tests/bear-material-plush-04` | unselected_candidate_early_protocol / passed | 早期单侧夹具：内部柔度.003、轴向40/s、shape0、无膜限幅，bench passed；非最终材料。 | 14/15 项匹配；`experiments/early-tests/bear-material-source-04`；不匹配：validation/probe_materials.py |
| `experiments/early-tests/bear-baseline-100` | early_setup_check / failed | 原材料构建烟测，质量检查断言bear mass changed导致失败，未开始有效100步测试。 | 无完整独立快照 |
| `experiments/early-tests/bear-baseline-100-tolerant` | early_setup_check / passed | 调整质量数值容差后的原材料1秒/100步烟测，passed；未执行穿衣动作。 | 无完整独立快照 |
| `experiments/early-tests/bear-runtime-check` | early_setup_check / 无独立状态 | 只保留临时网格等构建产物，无独立报告可确认成功。 | 无完整独立快照 |
| `runs/plush-cotton-smoke-03` | material_setup_smoke / passed | 早期新材料100步烟测，构建与变形检查；不是完整动作，参数以独立report为准。 | 无独立完整源码快照 |

## 快照与可复现性说明

- `full-03`、`full-03-physics`、`full-02` 的配置、实现与资产均对应 `full-02-source`；核对的 **32 项哈希全部匹配**。`full-03/source-at-run` 也保留了完整运行快照。
- `damping-400/1600` → `probe-source`（各15项）；`local-original` → `local-probe-source`（13项）；其他 `local-*` → 同快照（各16项）；`shape-8/20` → `shape-probe-source`（各16项）；`candidate-003` → `candidate-003-source`（16项）。这些是各自bench所记录依赖，不代表都包含完整穿衣工程。
- `candidate-003` 实际运行配置保存在 `candidate-003/tested-config.toml`，其哈希匹配报告中的原 `/tmp/bear-candidate-internal-003.toml`。不要用候选快照内另一份默认配置替代它。
- `bear-material-plush-04` 仅 **14/15** 项匹配：当时的 `validation/probe_materials.py` 后来被修改，在已查快照中未找到原哈希版本。保留原始结果，但标为部分源码快照。
- `bear-material-original-01` 只记录9个资产和 `pbd_adapter.py` 的10项哈希；虽可匹配归档中的同内容文件，但没有原测试脚本的完整冻结证据。
- `membrane-*` 诊断保留了测试脚本与部分材料模块，但脚本读取当时仓库配置，报告没有完整源码哈希清单，不能声称精确历史依赖已全部冻结。`membrane-final-small` 无独立报告。
- 归档复制已经实体化 `assets` 软链接；部分原测试脚本和报告仍保留历史绝对路径，作为来源记录。跨机器运行需另行指向归档资源。
- `full-02-source` 内的 `results-summary.json`、`installation.json`、`development-runs.json` 属于旧 `stabilized-dressing-complete-48` 元信息，不能用作新版验收结论。

## 对照、重复内容与诊断

- `final-material-comparison` 使用 `local-original` 与 `shape-20`；其 `comparison.json` 与 `validation/material_probe/comparison.json` 相同。这才是最终材料bench对照。
- `bear-material-comparison-04` 使用早期单侧夹具的 `bear-material-original-01` 与 `bear-material-plush-04`，不能与最终对向支撑夹具直接混作同一实验。目录中的 `original` / `plush_cotton` 是原软链接实体化副本。
- `shape-20/report.json`、`local-original/report.json` 已分别收录为 `validation/material_probe/plush-cotton-report.json`、`original-report.json`；原始实验目录还保留轨迹与网格。
- `full-03-physics/report.json` 也收录在 `validation/repeatability_failure/report.json`。它是失败重复，不是另一套材料参数。
- `cloth-stage-diagnostic.json`、`cloth-contact-diagnostic.json`、`cotton-solver-diagnosis.json` 与 `experiments/diagnostics` 为离线分析，不计为新完成运行。
- `runs/plush-cotton-smoke-03` 是通过的100步构建/变形烟测，不是完整穿衣动作。

## 构建尝试日志

以下原 `/tmp` 日志已原样保存于 `experiments/early-tests/logs/`。它们不是额外成功结果：

- `bear-material-smoke-01.log`：`edge_start` 私有接口使用错误。
- `bear-material-smoke-02.log`：build预热阶段配置时序错误。
- `bear-material-smoke-03.log`：烟测通过，对应已交付 `runs/plush-cotton-smoke-03`。
- `bear-material-full-01.log`：早期运动时磁盘空间耗尽；没有可在本索引中认定为完整的结果/源码快照。

编译缓存、临时缓存不是实验结果。候选bench通过也不代表其材料已被采用，更不代表已通过完整动作回归。
