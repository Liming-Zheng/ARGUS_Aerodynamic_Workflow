# ARGUS 气动优化代码交接说明

这是 ARGUS 外翼变形项目的**整理版交接仓库**。它保留了当前仍有用的
OpenVSP/VSPAERO 建模、计算、优化与审计代码，以及经过最终核查的结果表、
代表性 `.vsp3` 几何和复现说明；没有把约 1.6 GB 的全部中间计算文件直接
复制进 GitHub。

## 建议先读什么

1. 英文主说明 [`README.md`](README.md)
2. 方法说明 [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)
3. 最终结果与局限 [`docs/RESULTS_AND_LIMITATIONS.md`](docs/RESULTS_AND_LIMITATIONS.md)
4. 审计与错误修正 [`docs/AUDIT_AND_CORRECTIONS.md`](docs/AUDIT_AND_CORRECTIONS.md)
5. 接手者运行手册 [`docs/HANDOVER.md`](docs/HANDOVER.md)
6. Windows/Ubuntu/macOS 配置 [`docs/CROSS_PLATFORM_SETUP.md`](docs/CROSS_PLATFORM_SETUP.md)
7. 结构耦合接口 [`docs/STRUCTURAL_COUPLING.md`](docs/STRUCTURAL_COUPLING.md)
8. 更换优化算法 [`docs/EXTENDING_OPTIMIZATION.md`](docs/EXTENDING_OPTIMIZATION.md)

## 最重要的结论

- 不能仅凭当前气动结果宣布 twist 或 trailing-edge morphing 是普遍最优。
- 早期巡航结果受人为设定的根部弯矩限制显著影响。
- 晚期巡航中，两种连续变形方案的远场诱导阻力收益几乎相同。
- 低速下 trailing-edge 比 twist 好约 0.115 drag counts，低于现有配对网格
  RANS 的有效分辨能力。
- 最终选型应主要由驱动力、行程、能耗、质量、蒙皮应变、扭转刚度、结构
  集成和失效模式决定。

## 接手时必须注意

- 最终排名使用 `CDiw`，不要继续使用旧表中的 near-field `CDi` 排名。
- 旧的 1050 N m “hinge moment” 约束已撤回，它不是局部执行器铰链力矩。
- `Mach 0.10` 的低速结果不能直接作为巡航执行器载荷。
- 发布到公开 GitHub 前，必须确认 NASA 几何、合作方数据和图片的再发布权限，
  并由项目负责人选择许可证。

## 后续人员如何继续

仓库新增了 `src/argus_workflow` 顶层接口，把几何生成、气动计算、结构/执行器
计算和优化算法分开。Marco 的结构程序可以通过 `interfaces/` 中的 JSON
请求/结果格式接入；Alexander 或其他研究者可以保留同一套精确分析流程，
只替换搜索算法或目标函数。`examples/structural_coupling` 和
`examples/custom_optimizer` 都可以在没有 OpenVSP 的情况下先验证接口。

Python 编排层使用相对路径、`pathlib` 和参数列表，CI 会在 Windows、Ubuntu
和 macOS 上测试。OpenVSP/VSPAERO 在新系统上仍需单独安装，并先复现仓库中
的 baseline，确认科学结果一致后再开展新优化。

本仓库是在 TU Delft 开展 ARGUS 项目工作期间形成的公开科研软件仓库。
仓库原创代码和文档使用 BSD-3-Clause 许可证；NASA 来源资料、OpenVSP、
几何、标识和其他第三方内容不因此被重新授权，具体范围见
[NOTICE.md](NOTICE.md)。

项目地址：
[Liming-Zheng/ARGUS_Aerodynamic_Workflow](https://github.com/Liming-Zheng/ARGUS_Aerodynamic_Workflow)
。任何人都可以通过 HTTPS 读取和 clone；有写权限的协作者可以配置 GitHub
SSH key 后使用 SSH 地址 push。SSH 是身份认证方式，并不是读取公开仓库的
必要条件。外部贡献者建议 fork 后提交 pull request，直接写权限仍由仓库
所有者控制。

安装和运行步骤以英文 [`README.md`](README.md) 为准。


