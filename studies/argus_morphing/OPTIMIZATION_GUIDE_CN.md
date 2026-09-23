# ARGUS 优化框架使用说明

## 1. 当前框架是否完整

当前框架已经形成闭环：

1. 使用 5 个展向控制点定义连续变形量 `A(eta)/c`。
2. 自动修改 OpenVSP 精细化机翼模型。
3. 用 VSPAERO 将每个方案精确配平到同一个 `CL`。
4. 提取 `CD`、`CDi`、根部弯矩和气动力矩代理值。
5. 用高斯过程代理模型学习已有精确样本。
6. 用可配置算法提出下一批设计。
7. 将候选送回 VSPAERO 精确验证。
8. 每轮记录真实改善量，并输出可编辑 SVG 收敛图。

统一入口是：

```text
scripts/18_run_user_optimization.py
```

主要配置文件是：

```text
config/optimization_user_config.json
```

## 2. 最简单的使用方法

在 PowerShell 中进入项目目录：

```powershell
cd studies\argus_morphing
```

先检查配置，不运行 OpenVSP：

```powershell
python scripts\18_run_user_optimization.py --dry-run
```

正式运行配置中的全部外层迭代：

```powershell
python scripts\18_run_user_optimization.py
```

只运行 2 次外层迭代：

```powershell
python scripts\18_run_user_optimization.py --iterations 2
```

只生成下一轮候选参数，不调用 OpenVSP：

```powershell
python scripts\18_run_user_optimization.py --no-evaluate
```

程序支持断点续算。再次运行相同配置时，会从
`iteration_history.csv` 中最后完成的迭代继续。

## 3. 外层迭代与内层迭代

这是最容易混淆的地方。

### 外层迭代

配置：

```json
"iterations": {
  "max_iterations": 5,
  "batch_size": 3
}
```

含义：

- 最多执行 5 轮真实优化。
- 每轮新增 3 个 OpenVSP/VSPAERO 工况。
- 因此最多新增 `5 x 3 = 15` 个昂贵的真实样本。

### 内层迭代

配置：

```json
"algorithm": {
  "inner_max_iterations": 60,
  "population_size": 12
}
```

这些迭代只调用快速代理模型，不运行 VSPAERO。提高它们通常只增加几秒到
几十秒，不会产生 120 个真实气动工况。

## 4. 修改设计变量

```json
"design_variables": {
  "control_etas": [0.6, 0.6875, 0.775, 0.8625, 0.95],
  "amplitude_bounds_over_c": [0.0, 0.04],
  "max_adjacent_delta": 0.02,
  "x_h_over_c": 0.62
}
```

- `control_etas`：展向控制点位置。
- `amplitude_bounds_over_c`：各控制点允许的变形量范围。
- `max_adjacent_delta`：相邻控制点最大变形量差，用于限制展向突变。
- `x_h_over_c`：弦向开始变形的位置。

改变控制点数量后，框架会自动适应，但已有样本维数将不再匹配。此时建议建立
新的输出目录或重新生成初始 DOE。

## 5. 修改目标函数

### 仅最小化诱导阻力

```json
"objective": {
  "metric": "CDi",
  "direction": "minimize",
  "root_bending_weight": 0.0,
  "torque_weight": 0.0
}
```

### 最小化总阻力

将：

```json
"metric": "CD"
```

### 气动与结构加权目标

```json
"objective": {
  "metric": "CDi",
  "direction": "minimize",
  "root_bending_weight": 0.02,
  "torque_weight": 0.01
}
```

内部标量目标为：

```text
score =
  aerodynamic metric
  + root_bending_weight * bending_increase_percent / 1000
  + torque_weight * abs(torque_proxy) / 1e6
```

无论选择何种权重，CSV 中仍保留所有原始物理量。

## 6. 修改约束

```json
"constraints": {
  "root_bending": {
    "enabled": true,
    "maximum_percent": 7.0,
    "penalty": 100.0
  },
  "hinge_torque_proxy": {
    "enabled": true,
    "maximum_abs_Nm": 1100.0,
    "penalty": 0.0001
  }
}
```

- `enabled=false`：关闭该约束。
- `maximum_percent`：允许的半翼根弯矩增量。
- `maximum_abs_Nm`：允许的气动力矩代理绝对值。
- `penalty`：代理模型搜索阶段违反约束的惩罚强度。

最终可行性使用精确 VSPAERO 结果判断，不使用代理预测冒充最终结果。

## 7. 更换算法

### Differential Evolution

```json
"algorithm": {
  "name": "differential_evolution",
  "population_size": 15,
  "inner_max_iterations": 120,
  "tolerance": 1e-7,
  "polish": true
}
```

适合正式优化，鲁棒但内层搜索略慢。

### Random Search

```json
"algorithm": {
  "name": "random_search",
  "random_search_samples": 100000
}
```

适合调试目标函数与约束。它简单、透明，也方便与其他算法比较。

新增算法的位置：

```text
src/argus_morphing/optimization_framework.py
```

函数：

```python
propose_batch(...)
```

可以在这里接入 `SLSQP`、`CMA-ES`、`NSGA-II` 或其他算法。新算法只需返回
一个控制点数组列表。

## 8. 探索与利用

```json
"surrogate": {
  "exploration_weight": 0.25
}
```

候选选择使用类似 lower confidence bound 的形式：

```text
predicted objective - exploration_weight * prediction uncertainty
```

- `0.0`：完全利用当前代理预测。
- 较大值：更愿意探索不确定区域。
- 首轮建议使用 `0.1` 到 `0.5`。

## 9. 提前停止

```json
"iterations": {
  "minimum_absolute_improvement": 1e-6,
  "early_stop_patience": 2
}
```

如果连续 2 轮真实目标改善小于 `1e-6`，优化自动停止。

这里比较的是精确 VSPAERO 结果，不是代理模型预测。

## 9.1 快速并行搜索模式

默认运行设置已经针对本机 Ryzen 9 3900X（12 核 24 线程、64 GB 内存）
调整为：

```json
"runtime": {
  "workers": 4,
  "trim_mode": "fast",
  "fast_trim_alpha_low": 1.0,
  "fast_trim_alpha_high": 2.5,
  "fast_trim_alpha_points": 2,
  "search_cl_tolerance": 0.0002
}
```

含义：

- 同时评估最多 4 个候选设计。
- 每个 VSPAERO 进程保持单线程，避免候选之间争抢 CPU。
- 每个候选先在同一个 VSPAERO sweep 中计算两个迎角。
- 用线性 `CL-alpha` 关系预测配平迎角。
- 再运行一次最终载荷工况。
- 搜索阶段允许 `CL` 误差不超过 `2e-4`。

在当前模型的 `opt_s011` 基准测试中：

- 原逐点配平约 49.8 秒/候选，5 次 VSPAERO execution。
- 快速严格配平约 37.9 秒/候选。
- 快速搜索模式约 28.3 秒/候选，2 次 VSPAERO execution。
- `CDi` 相对严格结果误差约 0.087%。
- 根弯矩增量误差约 0.042 个百分点。

完整外层迭代也已验证：

- 3 个候选、4 个 worker 时，3 个候选均并行完成且无失败重试。
- 单个候选平均约 28.6 秒。
- 整轮程序墙钟时间约 56.7 秒，其中迭代记录时间约 54.2 秒。
- 修复临时文件冲突前，两轮分别约需 123.4 秒和 109.7 秒。
- 当前搜索阶段最优样本为 `usr_i003_c03`；正式交付前仍需严格复算。

每个并行子进程会在自己的候选目录中运行，避免 OpenVSP/VSPAERO 的辅助
文件在共享工作目录中发生冲突。若仍出现并行失败，主程序会保留断点并自动
串行重试。

因此快速模式适合中间迭代。最终选中的最优方案应使用严格模式复算：

```powershell
<OPENVSP_PYTHON> scripts\15_run_optimization_samples.py `
  --workers 2 `
  --trim-mode iterative `
  --force
```

注意：该命令会严格复算所有样本目录。若只希望复算一个最终候选，可以使用
`--worker --case-dir <候选目录>`。

## 10. 每轮输出

运行目录：

```text
outputs/optimization/user_optimization/
```

重要文件：

- `iteration_history.csv`：每轮样本数、优化前后最优值和改善量。
- `mean_candidate_evaluation_seconds`：该轮每个候选的平均求解时间。
- `total_vspaero_executions`：该轮实际调用的 VSPAERO 求解次数。
- `iteration_XXX_cases.json`：每轮控制点设计。
- `iteration_XXX_generate.log`：OpenVSP 模型生成日志。
- `iteration_XXX_evaluate.log`：VSPAERO 求解日志。
- `iteration_convergence.svg`：最优精确目标随外层迭代变化。
- `iteration_improvement.svg`：每轮带来的改善百分比。
- `current_exact_design_space.svg`：当前可行与不可行样本。
- `current_best_design.json`：当前最优可行设计。

SVG 中的文字仍是文本元素，可以在 Inkscape、Illustrator 或 PowerPoint
转换为形状后编辑。

## 11. 代码结构

```text
scripts/18_run_user_optimization.py
```

负责流程控制、迭代、调用 OpenVSP、记录历史和绘图。

```text
src/argus_morphing/optimization_framework.py
```

负责目标函数、约束判断、代理模型和候选搜索。

```text
scripts/04_generate_representative_cases.py
```

负责把控制点变形量写入 OpenVSP 机翼。

```text
scripts/15_run_optimization_samples.py
```

负责精确固定升力配平、VSPAERO 分段载荷和结果汇总。

## 12. 推荐的第一次自行运行

先将配置改为：

```json
"iterations": {
  "max_iterations": 1,
  "batch_size": 2
}
```

运行 `--dry-run`，确认配置正确，然后正式运行。这样只新增 2 个真实工况，
便于确认目录、日志和图表符合你的习惯，再逐渐增加迭代次数。

## 13. 当前限制

- 当前代理输入只包含 5 个展向变形控制点。
- `x_h/c` 暂时固定为 0.62。
- 力矩是 VLM 概念级代理值，不是执行器最终额定扭矩。
- 若改变控制点数量、飞行工况或网格，建议重新建立初始样本。
- 最终设计仍需更高保真 CFD、结构模型或试验验证。


