# AI 论文精读必要信息覆盖审计

审计对象：`nature-paper-card` v1.2.0，固定于上游提交
`4312c49e04c27aac9a719a03be17cf1a15501147`。

## 结论

| 必要信息 | 结果 | 强制覆盖位置 |
|---|---|---|
| 论文解决了什么科学问题 | PASS | `references/card-schema.md` 的 02–05 节要求给出具体问题、重要性、现有方法为何不足、核心痛点及论文洞见。 |
| 每个模块、策略是什么，分别解决什么问题 | PASS | `static/core/workflow.md` 要求逐个分析 central component；`references/card-schema.md` 的 07–08 节固定输出模块功能、必要性、输入输出、支撑证据和移除影响；`static/fragments/paper_type/methods.md` 要求把每个消融映射到单一组件。 |
| previous work 为什么解决不了，而本文为什么能做到 | PASS | `static/core/workflow.md` 强制重建“问题 → 旧方法局限 → 核心洞见 → 设计选择 → 所需证据 → 实验 → 可支持结论”的完整因果链；`references/card-schema.md` 的 03–06 节补充旧路线的优势、局限、痛点成因和本文定位。 |

## AI 领域适配性

`methods` 分析镜头直接覆盖算法、模型、工具、框架和系统论文，并检查：

- 输入、输出、模块、训练要求、外部工具、反馈环和推理成本；
- 核心洞见与实现组件包的区别；
- 消融是否真正隔离单个组件；
- baseline 公平性、backbone 一致性、数据泄漏、算力预算、oracle 输入和端到端状态；
- 数据集同时构成主要贡献时，叠加 `resource` 镜头进行独立审计。

因此它可以覆盖常见 AI/ML/CV/NLP 方法论文，而不是只做摘要复述。

## 证据与边界

- 每个中心结论必须绑定章节、图、表、公式或稳定 source block。
- 作者陈述、外部事实、Agent 分析和研究假设使用不同 provenance 标签。
- 缺少全文或可靠页码时自动降级为结构定位或来源受限模式，并明确写 `Not assessable`，不补造方法、实验或页码。
- 上游自带的结构审计器不能证明科学判断正确，因此仍保留人工核对数值、消融隔离性和因果链强度的质量门。

## 集成检查

- `manifest.yaml` 的全部 `always_load` 路径均已随仓库提供，包括 `../nature-shared/core/terminology-ledger.md`。
- 两个 Python 脚本只处理显式给定的本地文件和输出目录；未发现网络请求、命令注入、秘密读取或删除逻辑。
- PDF 路径需要 Python 3 和 PyMuPDF；JSON source-map 路径以及审计器仅依赖 Python 标准库。
- 上游内容按 Apache License 2.0 分发，许可证和固定版本信息见 `LICENSE` 与 `UPSTREAM.md`。
