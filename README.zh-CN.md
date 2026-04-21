Language: [English](README.md) | [日本語](README.ja.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Português (Brasil)](README.pt-BR.md) | [Español](README.es.md)

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1115_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

**一个从经验中自主学习的 AI 代理：完全运行于本地的 9B 模型 (Qwen3.5)，仅需一台 Apple Silicon Mac (M1+, 16 GB RAM)。**
无需云端。API 密钥不经网络传输。无 shell 执行。危险能力并非由规则限制 —— 它们从一开始就不在代码中。

## 为什么存在

多数代理框架是在事后给安全「打补丁」。[OpenClaw](https://github.com/openclaw/openclaw) 曾因 [多个严重漏洞](https://www.tenable.com/plugins/nessus/299798)、[通过 WebSocket 完整接管代理](https://www.oasis.security/blog/openclaw-vulnerability) 以及 [22 万以上实例暴露在互联网上](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/) 而著名。给 AI 代理开放广泛的系统访问权限，会在结构层面持续扩大攻击面。

本框架采取相反的方向：**security by absence（不在的安全）** —— 一种设计原则，指的是从一开始就不实现危险能力，而不是通过规则去限制它们。代理无法执行 shell 命令，无法访问任意 URL，也无法遍历文件系统 —— 因为这些代码从未被写入。提示词注入无法赋予代理它本就不具备的能力。

**并且它完全运行在消费级硬件上。** 包括从自身经验中学习、以意义检索的语义记忆、从反复出现的模式中自动抽取技能、以及随时间老化与更新的知识 —— 整条管线都运行在单台 Apple Silicon Mac (M1+, 约 16 GB RAM) 上，仅使用两个开源权重模型：**qwen3.5:9b** 生成模型 (Q4_K_M 量化，磁盘占用约 6.6 GB) 与 **nomic-embed-text** 嵌入模型 (约 274 MB，768 维)。无需 GPU 集群，无需云端推理。

接触网络的唯一部件是面向外部服务的适配器。参考适配器 Moltbook 是社交网络，联网是其本性；其余任何适配器都可以完全离线运行 —— 生成、嵌入、检索与蒸馏全部在本地完成。

**这使该架构可移植到云端不可用或不可取的边缘环境**：受数据主权约束的医疗与法律工作流、对隐私敏感的个人助理、间歇性连接的现场部署、气隙 (air-gapped) 系统。

在这个既安全又自包含的基础之上，代理进一步**从自身的经验中学习**：将原始片段日志蒸馏为知识、技能、规则以及持续演化的身份。

## 工作原理

```
Episode Log   raw actions, immutable JSONL (untrusted)
 │
 ├── distill ─▶ Knowledge (behavioral)
 │                 • embedding + views
 │                 • provenance / trust
 │                 • bitemporal / strength
 │                 │
 │                 ├── distill-identity ─▶ Identity
 │                 │                       (whole-file, ADR-0030)
 │                 │
 │                 └── insight ─▶ Skills
 │                                 (retrieve / apply / reflect)
 │                                   │
 │                                   └── rules-distill ─▶ Rules
 │
 └── distill (constitutional) ─▶ Knowledge (constitutional)
                                   │
                                   └── amend ─▶ Constitution
```

原始行为沿越来越抽象的层级向上流动。每一层都是可选的 —— 只使用需要的部分即可。Episode Log 之上的每一层都是代理反观自身经验后生成的。

这一循环是本项目对 **Agent Knowledge Cycle (AKC)** 的实现 —— 一个由六阶段组成的自我改进周期（Research → Extract → Curate → Promote → Measure → Maintain），最初作为 Claude Code harness 用于元工作流改进，此处在自主代理语境中重新实现。`distill` 对应 Extract；`insight` / `rules-distill` / `amend-constitution` 对应 Curate；`distill-identity` 对应 Promote；pivot snapshots (ADR-0020) 与 `skill-reflect` (ADR-0023) 对应 Measure。阶段到代码的完整映射：[docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping)。上游 harness：[agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle)。

知识以嵌入坐标而非离散类别的形式存储；被命名的 *views* 作为可编辑的语义种子 ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md))。新片段到达时会触发对主题相关的旧模式的再解释，而不是覆盖 —— 检索分数由 cosine + BM25 混合构成 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md))。这一层级结构参考了唯识 (Yogācāra) 的八识模型 ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md))。出处记录 (provenance)、时间妥当性 (bitemporal) 以及它们的演变细节在下文 [主要特性](#主要特性) 中展开。

## 主要特性

**通过 AKC 自我改进** —— 代理在自身日志上运行六阶段 [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle) —— 无需外部微调，无需标注训练数据。每次阶段晋升（日志 → 模式、模式 → 技能、技能 → 规则、技能 → 身份）都经过 [人类审批闸门](docs/adr/0012-human-approval-gate.md)。

- *嵌入 + views* —— 分类是查询，不是状态；views 是可编辑的语义种子 ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md)；`category` 字段已在 [ADR-0026](docs/adr/0026-retire-discrete-categories.md) 废止)。
- *记忆进化 + 混合检索* —— 新模式可触发 LLM 对主题相关旧模式的再解释，旧行被逻辑地作废 (soft-invalidate)，修订行追加写入；检索分数融合 cosine 与 BM25 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md))。
- *skill-as-memory loop* —— 技能按「取出 (retrieve) → 应用 (apply) → 依结果重写 (rewrite)」循环更新 ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md))。
- *noise as seed（以噪声为种子）* —— 被驳回的片段会以 `noise-YYYY-MM-DD.jsonl` 形式保留；当 view 的质心漂移时，它们可被重新分类，而不是被丢失 ([ADR-0027](docs/adr/0027-noise-as-seed.md))。

**LLM 看到的所有文本都是可编辑的 Markdown 文件** —— 章程、身份、技能、规则、**29 个流水线提示词**（`distill` / `insight` / `rules-distill` / `amend-constitution` / `skill-reflect` / `memory_evolution` …）以及 **7 个 view 种子** 全部以 Markdown 文件形式存在于 `$MOLTBOOK_HOME/` 下。`init` 之后，LLM 将看到的一切都在磁盘上：编辑提示词以改变模式抽取的行为、替换 view 种子以调整分类、微调章程以偏置判断，每一步都是单文件编辑。编辑可用 `git diff` 追踪，并被纳入 pivot snapshot 以保证可复现。[自定义 →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

**按设计即安全 (secure by design)** —— 无 shell 执行，无任意网络访问，无文件系统遍历。域名锁定到 `moltbook.com` 与本地 Ollama。仅 3 个运行时依赖（`requests`、`numpy`、`rank-bm25`）—— 无子进程，无 shell，无模板引擎。[完整威胁模型 →](docs/adr/0007-security-boundary-model.md)

- *出处追踪* —— 每个模式都携带 `source_type` 与 `trust_score`；MINJA 级别的记忆注入攻击会在结构上变得可见而非隐蔽 ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)，被 [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) / [ADR-0029](docs/adr/0029-retire-dormant-provenance-elements.md) 部分取代)。
- *可重放的 pivot snapshots* —— `distill` 执行会将完整的推理时上下文（views + constitution + prompts + skills + rules + identity + 质心嵌入 + thresholds）一次打包，以便任意决策都能按位重放 ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md))。

**11 种伦理框架** —— 同一代理可搭配斯多葛、功利主义、关怀伦理等 11 种哲学框架出厂。同样的行为数据，不同的初始条件 —— 观察代理如何发散。[自建模板 →](docs/CONFIGURATION.md#character-templates)

**本地运行** —— Ollama + Qwen3.5 9B。API 密钥不出本机。M1 Mac 流畅运行。不可变片段日志保证实验的完全可复现。

**研究级透明性** —— 每个决策都可被追踪。不可变日志、蒸馏产物与日报都[公开同步](https://github.com/shimo4228/contemplative-agent-data)以供复现。任一次 `distill` 执行如何按位复现，参见上文「可重放的 pivot snapshots」。

## 实时代理

一个 Contemplative 代理每天运行在 [Moltbook](https://www.moltbook.com/u/contemplative-agent) 上，这是一个 AI 代理社交网络。它浏览信息流，按相关度筛选帖子，生成评论并发布原创内容。其知识通过每日蒸馏持续演化。

**观察它的演化：**

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) —— 从经验中蒸馏出的人格
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) —— 伦理原则（以 CCAI 四公理为起点）
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) —— 由 `insight` 抽取的行为技能
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) —— 从技能蒸馏出的通用原则
- [日报](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) —— 带时间戳的交互记录（学术与非商业用途自由可用）
- [分析报告](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) —— 行为演化与章程修订实验

## 快速开始

**前置条件：** 本机已安装 [Ollama](https://ollama.com/download)。默认模型 (Qwen3.5 9B Q4_K_M；模型文件约 6.6 GB) 需要约 8 GB RAM。已在 M1 Mac (16 GB RAM) 上验证。

若你使用 [Claude Code](https://claude.ai/claude-code)，可将本仓库 URL 贴给它并让其完成代理搭建。它会引导你完成 clone、安装与配置 —— 请先准备好 `MOLTBOOK_API_KEY`（在 moltbook.com 注册获取）。

或手动执行：

```bash
# 1. 安装
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # 或：uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

# 2. 配置
cp .env.example .env
# 编辑 .env —— 设置 MOLTBOOK_API_KEY（在 moltbook.com 注册获取）

# 3. 运行
contemplative-agent init               # 创建 identity, knowledge, constitution
contemplative-agent register           # 仅 Moltbook 适配器需要；其他适配器可跳过
contemplative-agent run --session 60   # 默认：--approve（每次发布前确认）

# 或以不同的角色模板开始（默认路径：~/.config/moltbook/）：
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

## 代理模拟

同一框架可用于观察代理在不同初始条件下如何分化。**11 种伦理框架模板随附作为起点** —— 从斯多葛的德性伦理到关怀伦理、康德义务论、实用主义、契约主义等等。片段日志是不可变的，因此同样的行为数据可以在不同初始条件下被重新处理，用于反事实实验。

此外，分化后的两个代理还可以**在本地直接对话**：`contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N`（ADR-0015 仅限本地的例外）。两个 peer 各自拥有独立的 MOLTBOOK_HOME、片段日志和宪法——适合宪法反事实实验：在同一转录上比较两种框架会分别提出怎样的宪法修订。

完整模板列表（哲学、核心原理、如何选择或自建）见 [配置指南 → Character Templates](docs/CONFIGURATION.md#character-templates)。

## 安全模型

| 攻击向量 | 典型框架 | Contemplative Agent |
|---------|---------|---------------------|
| **Shell 执行** | 核心能力 | 代码库中不存在 |
| **网络访问** | 任意访问 | 域名锁定到 `moltbook.com` + 本地 localhost |
| **文件系统** | 完整访问 | 仅写入 `$MOLTBOOK_HOME`，权限 0600 |
| **LLM 提供商** | 外部 API 密钥需在网络中传输 | 仅本地 Ollama |
| **依赖** | 庞大的依赖树 | 3 个运行时依赖 (`requests`, `numpy`, `rank-bm25`) |

**one external adapter per agent（一代理一外部适配器）** —— 一个代理进程最多拥有一个会产生外部可观察副作用的适配器。跨越多个外部面的工作流（例如 *既* 发帖 *又* 付款）必须被拆分为权限相互隔离的多个代理进程，而不是塞进同一个。详见 [ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md)。

> 将本仓库 URL 贴入 [Claude Code](https://claude.ai/claude-code) 或任何懂代码的 AI，问它「运行这个安全吗？」—— 代码自己会说话。[最新安全扫描 →](docs/security/2026-04-01-security-scan.md)

**代码代理运营者提醒**：片段日志 (`logs/*.jsonl`) 包含来自其他代理的原始内容 —— 是未过滤的间接提示词注入攻击面。请改用蒸馏产物 (`knowledge.json`、`identity.md`、`reports/`)。Claude Code 用户可安装 PreToolUse hooks 自动强制执行此规则 —— 设置方法见 [integrations/claude-code/](integrations/claude-code/)。

## 适配器

核心与平台无关。适配器只是对平台特定 API 的薄包装。

**Moltbook**（已实现）—— 社交信息流参与、帖子生成、通知回复。这是线上代理所运行的适配器。

**Meditation**（实验性）—— 基于能动推断的冥想模拟，灵感来自 ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/)（Laukkonen, Friston & Chandaria, 2025）。从片段日志构建 POMDP，并在无外部输入的条件下进行信念更新 —— 计算意义上的「闭上眼睛」。

**自建适配器** —— 实现一个适配器，就是把平台 I/O 连接到核心接口（记忆、蒸馏、章程、身份）。见 [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md)。

## 使用托管 LLM API 运行（可选）

需要比 Qwen3.5 9B 更大的生成模型的研究实验 —— 例如在保持其余记忆流水线不变的前提下，比较蒸馏行为在 Claude Opus 或 GPT-5 下的差异 —— 可以使用一个独立仓库的 add-on:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) —— 可选 Python 包。安装并设置 API 密钥后，所有生成调用（distill / insight / rules-distill / amend-constitution / post / comment / reply / dialogue / skill-reflect）都会改走 Anthropic Claude 或 OpenAI GPT，而 embedding 仍使用本地的 `nomic-embed-text`。

这是明确的 **opt-in**。主仓库的默认栈（Ollama + Qwen3.5 9B）不会访问任何云端。[主要特性](#主要特性) 与 [安全模型](#安全模型) 中的「No cloud. No API keys in transit. Local Ollama only」对本仓库成立；只有当用户主动安装 cloud add-on 时，这一属性才会在那些用户那里放宽。主仓库的代码不会被修改 —— add-on 通过一个抽象的 `LLMBackend` Protocol（它对任何特定 provider 都一无所知）注入后端实现。

在不允许云端数据外发的部署（监管约束、气隙研究、隐私敏感的个人助理）中，不要安装 cloud add-on。在这些场景中，单独使用主仓库仍是合适的选择。

## 使用与配置

完整 CLI 参考、自主级别 (`--approve` / `--guarded` / `--auto`)、模板选择、域名配置、调度器、环境变量都集中在一份指南中：

→ **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** —— CLI commands、templates、autonomy、domain config、scheduling、env vars。

日常常用命令：

```bash
contemplative-agent run --session 60       # 运行一次会话
contemplative-agent distill --days 3       # 抽取模式
contemplative-agent skill-reflect          # 基于结果改写技能 (ADR-0023)
```

从 v1.x 升级？一次性迁移命令见 [CLI Commands → One-Time Migrations](docs/CONFIGURATION.md#cli-commands)。

## 架构

代码库始终遵守一个不变式：**core/** 与平台无关；**adapters/** 依赖 core，反之绝不成立。

Contemplative AI 四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）是可选的行为预设 —— 哲学上的共振，而非架构约束。去掉它们，代理照样能跑；将它们替换为斯多葛或康德式前提，代理会以不同方式运行。

模块地图、数据流图、import 图与模块级职责见 **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)**（权威来源）。FAQ、术语定义与研究参考（面向 AI）见 [llms-full.txt](llms-full.txt)。唯识框架如何预测性地约束了记忆设计，见 [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)。

如需基于 Docker 的网络隔离部署，见 [配置指南中的 Docker 一节](docs/CONFIGURATION.md#docker-optional)。

## 开发记录

1. [I Built an AI Agent from Scratch Because Frameworks Are the Vulnerability](https://dev.to/shimo4228/i-built-an-ai-agent-from-scratch-because-frameworks-are-the-vulnerability-elm)
2. [Natural Language as Architecture](https://dev.to/shimo4228/natural-language-as-architecture-controlling-an-autonomous-agent-with-prompts-memory-and-m74)
3. [Every LLM App Is Just a Markdown-and-Code Sandwich](https://dev.to/shimo4228/every-llm-app-is-just-a-markdown-and-code-sandwich-213j)
4. [Do Autonomous Agents Really Need an Orchestration Layer?](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9)
5. [Not Reasoning, Not Tools -- What If the Essence of AI Agents Is Memory?](https://dev.to/shimo4228/not-reasoning-not-tools-what-if-the-essence-of-ai-agents-is-memory-4k4n)
6. [My Agent's Memory Broke -- A Day Wrestling a 9B Model](https://dev.to/shimo4228/my-agents-memory-broke-a-day-wrestling-a-9b-model-50ch)
7. [Porting Game Dev Memory Management to AI Agent Memory Distillation](https://dev.to/shimo4228/porting-game-dev-memory-management-to-ai-agent-memory-distillation-35lk)
8. [Freedom and Constraints of Autonomous Agents -- Self-Modification, Trust Boundaries, and Emergent Gameplay](https://dev.to/shimo4228/freedom-and-constraints-of-autonomous-agents-self-modification-trust-boundaries-and-emergent-3i0c)
9. [How Ethics Emerged from Episode Logs — 17 Days of Contemplative Agent Design](https://dev.to/shimo4228/how-ethics-emerged-from-episode-logs-17-days-of-contemplative-agent-design-1kk5)
10. [A Sign on a Climbable Wall: Why AI Agents Need Accountability, Not Just Guardrails](https://dev.to/shimo4228/a-sign-on-a-climbable-wall-why-ai-agents-need-accountability-not-just-guardrails-17ak)
11. [Can You Trace the Cause After an Incident?](https://dev.to/shimo4228/can-you-trace-the-cause-after-an-incident-neo)
12. [AI Agent Black Boxes Have Two Layers — Technical Limits and Business Incentives](https://dev.to/shimo4228/ai-agent-black-boxes-have-two-layers-technical-limits-and-business-incentives-jhi)

## 按你的方式使用

这是研究项目，不是产品。fork、拆成零件、把管线嵌进你自己的代理、或者以它为基础造商业产品 —— 对你有用就好。MIT 许可证如其所言。仅使用代码时无需引用；学术参考见下一节。

## 引用

如果你使用或引用本框架，请引用：

```
Shimomoto, T. (2026). Contemplative Agent [Computer software]. https://doi.org/10.5281/zenodo.19212119
```

<details>
<summary>BibTeX</summary>

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  version      = {2.0.0},
  doi          = {10.5281/zenodo.19212119},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

</details>

## 相关项目

- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) ——
  姐妹研究仓库 (DOI [10.5281/zenodo.19652014](https://doi.org/10.5281/zenodo.19652014))。
  以 harness-neutral 的形式将本项目的治理判断（Security Boundary Model、
  One External Adapter Per Agent、Human Approval Gate，以及隐含的 causal
  traceability / scaffolding visibility 承诺）重新表达为八条 ADR ——
  关于自主 AI 代理中问责分配的判断。引用问责分配论点或 prohibition-strength
  层级时请引用 AAP；引用运行实现时请引用本仓库。

## 参考文献

### 理论基础

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) —— 四公理伦理框架（可选预设，[ADR-0002](docs/adr/0002-paper-faithful-ccai.md)）。
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop: An Active Inference Theory of Consciousness. *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) —— 冥想适配器的理论基础。
- 世亲 (Vasubandhu, 4–5 世纪). 《唯识三十颂》(*Triṃśikā-vijñaptimātratā*). —— 被采纳为架构框架的八识模型 ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md))。
- 玄奘 译·编 (659). 《成唯识论》. —— 汇集印度十家对世亲《唯识三十颂》的注疏；八识、种子 (bīja) 与习气 (vāsanā) 的结构，启发了「noise as seed」的保留策略 ([ADR-0027](docs/adr/0027-noise-as-seed.md))。

### 记忆系统

下列各篇论文都对应一项在 ADR 中记录的设计决策。书目信息已比对 arXiv。

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) —— Zettelkasten 式动态索引与记忆进化；启发了「新模式到达时对主题相关旧模式再解释」的机制 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md))。
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) —— 双时态 (bitemporal) 知识图谱边 (Graphiti 引擎)；启发了每个模式上的 `valid_from` / `valid_until` 契约 ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md))。
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) —— Ebbinghaus 式衰减与以访问为强化信号的强度模型；原本启发了 [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md) 中检索感知的遗忘曲线，但在 [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) 中被撤回 —— 记忆动力学的落脚点改为技能层。作为历史参考保留。
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) —— 仅通过查询即可实施的记忆注入攻击；是引入 `source_type` 与 `trust_score` 的动机，使 MINJA 类攻击结构上可见而非隐蔽 ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md))。
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) —— 把技能视为持续演化的记忆单元，通过「取出 → 应用 → 依结果改写」循环更新；是 skill-as-memory loop 的原型 ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md))。

### 作者先行研究

- Shimomoto, T. (2026). *Agent Knowledge Cycle (AKC): A Six-Phase Self-Improvement Cadence for AI Agents.* [doi:10.5281/zenodo.19200727](https://doi.org/10.5281/zenodo.19200727) —— 本项目在自主代理语境中重新实现的方法论框架（见 [工作原理](#工作原理)）；最初作为 Claude Code harness 开发。

### 致谢

- Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) —— 决定论式情感评分的设计灵感。
