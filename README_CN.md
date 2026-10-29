# 软体熊双臂穿孔包裹仿真

## 毛绒填充体与棉布材质更新

默认 `config.toml` 使用 `plush_cotton` 材料配置。`assets/`、机械臂动作代码、动作计划、固定底部、抓取与魔术贴逻辑均沿用原版本。下方 `stabilized-dressing-complete-48` 的视频与成功记录属于**原材质的历史结果**，不能作为新材质通过完整流程的证据。

**当前状态：材质修改已完成，一次完整录像运行完成；独立验收与严格材料健康检查尚未全部通过，也不能保证重复运行都成功。** 具体结果和未解决问题见“新材质完整运行”一节。

- 熊保留 0.49 kg 质量和原有连续四面体网格，加入可压缩填充体的体积响应；压缩与膨胀采用不同刚度，内部边比表面边柔软。沿边耗散处理局部形变，质量加权刚体速度拟合后的剩余速度耗散处理非刚体振动；后者是非局部的内部耗散近似。新增阻尼保留自由节点集合的整体平移、旋转与动量，并保持固定/抓取节点速度不变。
- 布料保留 180 g/m² 面密度、原尺寸和两个真实袖孔，采用具有有限平坦态梯度的 XPBD 弯曲约束；弯曲刚度按相邻三角形几何换算。在原拉伸约束后增加经纬向 2%、斜向 10% 的伸长限幅目标，近似织物受拉后的增硬；限幅不阻止折叠或压缩。有限次迭代和后续碰撞仍可能留下超限残差，不能把目标值当成实测保证。空气阻力按每个节点代表的面积计算。
- 只在当前场景安装修正，不修改已安装的 Genesis。原生 PBD 类型仍用于资产导入、碰撞和显示；类型名称 `Elastic` 并不代表仍采用原体积响应。

这些是未经过具体玩偶或布样实验标定的材料近似，不能当作真实棉花、聚酯填充或某一棉织物的实测参数。原有理想夹持、局部魔术贴、单向附加布/熊表面屏障与 1/s 全局稳定阻力仍保留，限制见文末。内部阻尼没有替代原有这些机制。

从本目录重新运行（默认自动选择可用后端，每次创建新结果目录）：

```bash
bash run-wrap.sh --headless
```

CPU 离屏运行：

```bash
LIBGL_ALWAYS_SOFTWARE=1 QD_NUM_THREADS=2 bash run-wrap.sh --headless --backend cpu
```

复现原材质时添加 `--config configs/original.toml`。不要用原材质的中途检查点恢复新材质验证；新材料需要从初始状态重新模拟。

体积和弯曲修正采用 [XPBD](https://mmacklin.com/xpbd.pdf) 的累计约束乘子，每个物理子步清零一次；这避免同一子步的额外接触投影反复增加材料刚度。拉伸仍沿用 Genesis 原约束，因此整个模型并非完全与迭代数无关。真实布料的非线性和方向性需要样本测量，参见 [Wang 等，2011](https://jamesobrien.com/papers/Wang-DDE-2011-08/index.html)。

### 材料对照验证

使用相同原网格、质量和积分设置，对原版和新版分别进行 250 步独立测试：前腹 12 mm 位移控制压入、后背对向支撑、释放，以及布料两角悬垂。支撑只存在于这个测试夹具，主场景固定点没有改变。

| 测量值 | 原材质 | 新材质 |
| --- | ---: | ---: |
| 熊释放末段 RMS 速度 | 0.02891 m/s | 0.002440 m/s |
| 末段局部压痕峰谷幅度 | 0.505 mm | 0.084 mm |
| 该夹具下曾翻转的四面体最大数量 | 1 | 0 |
| 悬垂布料最大局部边伸长 | 19.72% | 10.20% |
| 悬垂末态 P95 绝对边应变 | 3.33% | 2.13% |

结果见 [材料比较报告](validation/material_probe/comparison.json) 与 [曲线图](validation/material_probe/comparison.png)。新版尾段振动速度降低 91.6%，表示该测试的卸载耗散改善；相同位移控制不能单独标定刚度，也不能把这些百分比直接外推到完整穿衣动作。原有对角边拉伸约束仍保留，斜向 10% 限幅不等同于完整的纱线滑移或各向异性剪切模型。

在 Genesis 环境中复现（结果目录必须尚不存在）：

运行材质模型需要现有的 Genesis 1.4.3 环境；对照曲线脚本还需要 `matplotlib`，录像检查需要系统中的 `ffmpeg` 和 `ffprobe`。本机验证使用 `/home/chloe/Desktop/genesis-local/.venv/bin/python`，已具备这些依赖。

```bash
python validation/probe_materials.py --profile both --output runs/material-probe-check
python validation/check_material_response.py --output /tmp/material-response-check.json
python validation/check_bending.py --runtime --output /tmp/bending-check.json
python validation/check_membrane.py --output /tmp/membrane-check.json
python validation/check_material_scope.py
```

`probe_materials.py` 输出关键帧、粒子轨迹和曲线；加 `--no-render` 可跳过截图。三个小型求解器检查分别覆盖阻尼的刚体运动不变性/动量守恒/耗能、体积乘子累计、弯曲梯度，以及棉布投影的固定点和压缩保持。`check_material_scope.py` 比对 GitHub 基准提交 `abe0008c9331e1d3d875c73916008af7d612186b`，核对全部资产与动作文件逐字节一致、仅材料配置变化。

修改范围检查需要包含上述基准提交的 Git 工作副本；解压不含 `.git` 的源码包时，可以查看已保存的 `validation/material_scope.json`。对照测试当时使用的脚本和配置原样保存在 `validation/material_probe/source-at-test/`，清单记录了与当前复现脚本的差异。

### 新材质完整运行

本次从初始状态重新模拟至 71.97 秒，使用 Genesis 1.4.3、CPU、2 个计算线程及软件离屏渲染。主流程退出码为 0，`report.json` 的状态为 `passed`；两只熊爪完整穿过真实孔口，布料已解除机器人附着，底座保持固定，魔术贴仍有实际接触粘接。材料参数、动作代码和资产与保存的运行快照逐项一致。

- [新材质完整录像](runs/plush-cotton-complete-01/wrapping-process.mp4)
- [左侧录像](runs/plush-cotton-complete-01/wrapping-left-side.mp4)、[背后录像](runs/plush-cotton-complete-01/wrapping-rear.mp4)
- [独立动作验收](validation/full_run/independent-dressing-review.json)、[保存状态健康检查](validation/full_run/material-health.json)、[逐帧健康检查](validation/full_run/replay-health.json)、[同名阶段材料比较](validation/full_run/material-stage-comparison.json)

三个录像各 1080 帧、15 FPS、72 秒，采样自同一次模拟的相同步骤。为节省本机磁盘空间，交付视频重新编码为 H.264 CRF 20，保留分辨率、帧数和时序；粒子状态、截图和回放数组原样保存。原录像与交付录像的哈希和检查结果分别保存在运行目录中。源码 ZIP 包不包含视频与逐帧数组，完整运行资料位于上面的 `runs/plush-cotton-complete-01/`。

需要保留的限制：

1. 原样运行的独立验收 **23/24 项通过**。唯一失败项为头部水平位移 5.171 cm，超过原来的 5 cm 阈值 1.71 mm；原材质为 1.504 cm。新头部垂直下降约 4.06 mm，形状保持，主要变化发生在双臂被拉出并由夹爪保持之后；不能据此推断释放夹爪后的平衡姿态。阈值没有放宽。
2. **严格零网格翻转检查失败。** 1080 个回放帧中 220 帧存在局部翻转，单帧最多 2 个，涉及全部 7623 个四面体中的 4 个。最终仍有 2 个翻转，负体积绝对值合计约占初始总体积的 0.001158%。原有动作验收允许低于 0.01% 的残余负体积，因此主流程完成不能代表严格物理健康。全部检查状态数值有限，底座最大漂移约 3e-8 m。
3. **棉布伸长目标不是全程保证。** 最终边伸长 P95 为 1.029%、最大 11.134%（原成功运行最终最大 15.15%），但穿左袖期间单条边瞬时伸长达到 51.898%。这处于袖口和手指接触附近；材料投影之后的接触等约束仍会修改节点。不能宣称完整过程已满足低伸长棉布模型。修复需要材料、接触和粘接约束共同收敛，不能简单在最后强制缩短边、忽略新穿透。[求解顺序诊断](validation/cotton-solver-diagnosis.json) 保留了证据与建议。
4. **重复运行成功率未保证。** 相同源代码和参数的另一次 CPU 无渲染运行，在 52.66 秒被原左臂抓取规划检查拦住；浮点求解与后续接触分支的微小差异会改变抓取可行性。失败运行和候选检查保存在 [repeatability_failure](validation/repeatability_failure/context.json)，没有放宽原碰撞阈值或修改动作来绕过失败。

同口径逐帧对比：全程最大的帧内 P95 布料伸长从 8.235% 降至 5.389%，最终局部最大伸长降低；但全程单边峰值从 35.165% 升至 51.898%，超过 30% 伸长的帧占比从 3.65% 增至 8.33%。因此不能称布料在每个阶段都改善。两次运行的交互轨迹与时长不同，也不能把这些差异当作严格单变量实验。详见 [逐帧对比](validation/full_run/cloth-replay-comparison.json)。

本次更新有效降低了独立测试中的熊回弹振动；它仍是带已知接触求解限制的材料近似。上述未通过项均保留在报告中。

## 原版本流程与历史记录

原场景完成：双臂抓布料前侧两角 → 提起并环绕熊腹部 → 魔术贴实际接触后粘合 → 机械臂换抓熊的手臂 → 分别从两个真实布孔中拉出。

旧仿真的全部既有输出保存在 [bear-velcro-before-arms-20261018](/home/chloe/Documents/Codex/2026-10-17/na-m/outputs/archives/bear-velcro-before-arms-20261018)，含逐文件 SHA-256 清单。旧场景与原启动脚本保留。

## 原版本历史录像

- [完整过程（总览与近景）](/home/chloe/Desktop/genesis-local/bear_arms_scene/runs/stabilized-dressing-complete-48/wrapping-process.mp4)
- [桌子左侧](/home/chloe/Desktop/genesis-local/bear_arms_scene/runs/stabilized-dressing-complete-48/wrapping-left-side.mp4)
- [玩偶背后](/home/chloe/Desktop/genesis-local/bear_arms_scene/runs/stabilized-dressing-complete-48/wrapping-rear.mp4)

三个视频来自同一次运行的相同步骤，帧率为 15 FPS，模拟时长 65.67 秒。成功结果位于 `stabilized-dressing-complete-48`；其他运行是保留的开发记录，状态见 `development-runs.json`。

## 原版本环境入口

以下是原项目的历史入口，会运行原目录中的代码。运行当前毛绒/棉布更新版本，请使用本文顶部的本目录命令。

```bash
bash /home/chloe/Desktop/genesis-local/run-bear-arms.sh
```

无窗口运行并输出新录像：

```bash
bash /home/chloe/Desktop/genesis-local/run-bear-arms.sh --headless --backend cuda --width 1280 --height 720
```

默认每次创建新的结果目录。使用原有 `/home/chloe/Desktop/genesis-local/.venv` 环境。

## 原版本场景与结果

熊的双臂与躯干属于同一连续软体四面体网格，熊的底部固定。棉布保持原来的 86 × 20 厘米尺寸，两侧带魔术贴；两个孔由删除实际网格面形成。机械臂通过关节控制运动，抓取后采用局部无滑移约束。局部有向体积约束用于抑制夹持处的单元塌陷、翻转，残余数值误差记录在独立检查报告中。

本次运行目录保存三段视频、阶段截图、粒子和关节状态、轨迹日志、报告、源代码及素材快照。`replay-frames.npz` 保存每个视频采样时刻的熊、布料和机械臂状态。`checkpoint-history` 保留同名保存点的早期版本。

`independent-dressing-review.json` 检查固定底部、真实孔口、手臂穿孔、熊掌整体位于孔外、布料与身体的离散穿透采样及粘合保持；`video-validation.json` 记录三个视频的完整解码和帧同步检查。

## 模型范围

这是动作流程仿真。夹持与魔术贴使用接触触发的理想几何约束；一次局部粘接不代表整条魔术贴完全覆盖粘合，也没有标定真实拉力或剥离强度。额外的布料表面接触将当前形变后的熊作为障碍，原生粒子和机械臂接触仍参与计算。检查基于保存状态中的离散采样，不构成连续碰撞检测保证。最终机械臂保持夹住已拉出的熊手臂。
