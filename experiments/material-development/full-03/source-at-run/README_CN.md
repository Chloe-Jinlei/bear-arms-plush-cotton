# 软体熊双臂穿孔包裹仿真

## 毛绒填充体与棉布材质更新

默认 `config.toml` 使用 `plush_cotton` 材料配置。`assets/`、机械臂动作代码、动作计划、固定底部、抓取与魔术贴逻辑均沿用原版本。下方 `stabilized-dressing-complete-48` 的视频与成功记录属于**原材质的历史结果**，不能作为新材质通过完整流程的证据。

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

## 原版本流程与记录

新场景完成：双臂抓布料前侧两角 → 提起并环绕熊腹部 → 魔术贴实际接触后粘合 → 机械臂换抓熊的手臂 → 分别从两个真实布孔中拉出。

旧仿真的全部既有输出保存在 [bear-velcro-before-arms-20261018](/home/chloe/Documents/Codex/2026-10-17/na-m/outputs/archives/bear-velcro-before-arms-20261018)，含逐文件 SHA-256 清单。旧场景与原启动脚本保留。

## 本次完整录像

- [完整过程（总览与近景）](/home/chloe/Desktop/genesis-local/bear_arms_scene/runs/stabilized-dressing-complete-48/wrapping-process.mp4)
- [桌子左侧](/home/chloe/Desktop/genesis-local/bear_arms_scene/runs/stabilized-dressing-complete-48/wrapping-left-side.mp4)
- [玩偶背后](/home/chloe/Desktop/genesis-local/bear_arms_scene/runs/stabilized-dressing-complete-48/wrapping-rear.mp4)

三个视频来自同一次运行的相同步骤，帧率为 15 FPS，模拟时长 65.67 秒。成功结果位于 `stabilized-dressing-complete-48`；其他运行是保留的开发记录，状态见 `development-runs.json`。

## 打开完整环境并重新运行

```bash
bash /home/chloe/Desktop/genesis-local/run-bear-arms.sh
```

无窗口运行并输出新录像：

```bash
bash /home/chloe/Desktop/genesis-local/run-bear-arms.sh --headless --backend cuda --width 1280 --height 720
```

默认每次创建新的结果目录。使用原有 `/home/chloe/Desktop/genesis-local/.venv` 环境。

## 场景与结果

熊的双臂与躯干属于同一连续软体四面体网格，熊的底部固定。棉布保持原来的 86 × 20 厘米尺寸，两侧带魔术贴；两个孔由删除实际网格面形成。机械臂通过关节控制运动，抓取后采用局部无滑移约束。局部有向体积约束用于抑制夹持处的单元塌陷、翻转，残余数值误差记录在独立检查报告中。

本次运行目录保存三段视频、阶段截图、粒子和关节状态、轨迹日志、报告、源代码及素材快照。`replay-frames.npz` 保存每个视频采样时刻的熊、布料和机械臂状态。`checkpoint-history` 保留同名保存点的早期版本。

`independent-dressing-review.json` 检查固定底部、真实孔口、手臂穿孔、熊掌整体位于孔外、布料与身体的离散穿透采样及粘合保持；`video-validation.json` 记录三个视频的完整解码和帧同步检查。

## 模型范围

这是动作流程仿真。夹持与魔术贴使用接触触发的理想几何约束；一次局部粘接不代表整条魔术贴完全覆盖粘合，也没有标定真实拉力或剥离强度。额外的布料表面接触将当前形变后的熊作为障碍，原生粒子和机械臂接触仍参与计算。检查基于保存状态中的离散采样，不构成连续碰撞检测保证。最终机械臂保持夹住已拉出的熊手臂。
