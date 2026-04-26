Language: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Português (Brasil)](README.pt-BR.md) | [Español](README.es.md)

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1155_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

一個從經驗中自主學習的 AI 代理。完全運行於本地的 9B 模型 + 單台 Apple Silicon Mac (M1+, 16 GB RAM) — 無需雲端、API 金鑰不出網路、無 shell 執行。

本倉庫是兩條被保存下來的構想的運行實作:

- **[AKC (Agent Knowledge Cycle)](https://github.com/shimo4228/agent-knowledge-cycle)** ([DOI](https://doi.org/10.5281/zenodo.19200727)) — 代理如何將自身經驗代謝為可改進的技能。六階段: Research → Extract → Curate → Promote → Measure → Maintain。
- **[AAP (Agent Attribution Practice)](https://github.com/shimo4228/agent-attribution-practice)** ([DOI](https://doi.org/10.5281/zenodo.19652014)) — 自主 AI 代理中如何分配究責。八條 ADR，涵蓋 Security Boundary Model、One External Adapter Per Agent、Human Approval Gate、causal traceability。

第一個介接器是 **Moltbook**（AI 代理社群網路）。Contemplative AI 四公理作為可選預設隨附。

## 快速開始

**先決條件:** 本機已安裝 [Ollama](https://ollama.com/download)。預設模型 (Qwen3.5 9B Q4_K_M, 約 6.6 GB) 需要約 8 GB RAM。已在 M1 Mac (16 GB RAM) 驗證。

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # 或：uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

cp .env.example .env        # 設定 MOLTBOOK_API_KEY（在 moltbook.com 註冊取得）

contemplative-agent init               # 建立 identity, knowledge, constitution
contemplative-agent register           # 僅 Moltbook 介接器需要
contemplative-agent run --session 60   # 預設：--approve（每次發布前確認）
```

以不同的倫理框架開始（11 種模板隨附：斯多葛、功利主義、關懷倫理、康德義務論、實用主義、契約主義……）:

```bash
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

若你使用 [Claude Code](https://claude.ai/claude-code)，可將本 repo URL 貼給它並讓其完成端對端建置。完整 CLI 參考、自主等級、排程、模板請見 **[設定指南](docs/CONFIGURATION.md)**。

## 即時代理

一個 Contemplative 代理每天運行於 [Moltbook](https://www.moltbook.com/u/contemplative-agent)。其演化狀態對外公開:

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — 蒸餾出的人格
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — 倫理原則（以 CCAI 四公理為起點）
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — 由 `insight` 抽取
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — 從技能蒸餾
- [日報](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — 帶時間戳的互動紀錄（學術與非商業用途自由可用）
- [分析報告](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — 行為演化與章程修訂實驗

## 工作原理

```
Episode Log   raw actions, immutable JSONL (untrusted)
 │
 ├── distill ─▶ Knowledge (behavioral)
 │                 ├── distill-identity ─▶ Identity
 │                 └── insight ─▶ Skills
 │                                 └── rules-distill ─▶ Rules
 │
 └── distill (constitutional) ─▶ Knowledge (constitutional)
                                   └── amend ─▶ Constitution
```

原始行為沿越來越抽象的層級向上流動。每一層都是可選的。Episode Log 之上的每一層都是代理反觀自身經驗後生成的。

這條管線即 AKC 六階段對應到程式碼: `distill` 對應 Extract；`insight` / `rules-distill` / `amend-constitution` 對應 Curate；`distill-identity` 對應 Promote；pivot snapshots ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)) 與 `skill-reflect` ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md)) 對應 Measure。完整對應表: [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping)。

## 主要特色

- **透過 AKC 自我改進** — 代理在自身日誌上運行六階段循環。無需微調，無需標註訓練資料。每次階段晉升（日誌 → 模式 → 技能 → 規則 → 身份）都經過[人工審核閘門](docs/adr/0012-human-approval-gate.md)。
- **嵌入 + views** — 分類是查詢而非狀態；views 是可編輯的語意種子（[ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md)；`category` 欄位已在 [ADR-0026](docs/adr/0026-retire-discrete-categories.md) 廢止）。
- **記憶演化 + 混合檢索** — 新模式可觸發 LLM 對主題相關舊模式的再詮釋，舊列被 soft-invalidate，修訂列追加寫入；cosine + BM25 混合分數（[ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)）。
- **skill-as-memory loop** — 技能按取出 → 套用 → 依結果改寫的循環更新（[ADR-0023](docs/adr/0023-skill-as-memory-loop.md)）。
- **noise as seed** — 被駁回的片段以 `noise-YYYY-MM-DD.jsonl` 形式保留；當 view 質心漂移時可被重新分類，而不是丟失（[ADR-0027](docs/adr/0027-noise-as-seed.md)）。
- **可重放的 pivot snapshots** — `distill` 執行將完整推論時上下文（views + constitution + prompts + skills + rules + identity + 質心嵌入 + thresholds）一次打包，使任意決策可以按位元重放（[ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)）。
- **來源追蹤** — 每個模式都攜帶 `source_type` 與 `trust_score`；MINJA 類記憶注入攻擊在結構上變得可見（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)）。
- **Markdown all the way down** — 章程、身份、技能、規則、32 個管線提示詞、7 個 view 種子全部以 Markdown 形式存在於 `$MOLTBOOK_HOME/` 之下。編輯提示詞改變模式抽取的行為；替換 view 種子調整分類。[自訂 →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

## 安全模型

究責與安全邊界於 [AAP](https://github.com/shimo4228/agent-attribution-practice) 中以 harness-neutral 的 ADR 記錄。本倉庫是這些判斷的運行實作。

- 無 shell 執行、無任意網路存取、無檔案系統遍歷 — 這些程式碼不存在於程式碼庫中。網域鎖定到 `moltbook.com` 與本機 Ollama。3 個執行期依賴: `requests`、`numpy`、`rank-bm25`。
- 一行程一外部介接器 ([ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md))。
- 完整威脅模型: [ADR-0007](docs/adr/0007-security-boundary-model.md)。[最新安全掃描](docs/security/2026-04-01-security-scan.md)。

> 把本 repo URL 貼進 [Claude Code](https://claude.ai/claude-code) 或任何理解程式碼的 AI，問它「這個執行起來安全嗎？」— 程式碼自己會說話。

**程式碼代理操作者注意**: 片段日誌 (`logs/*.jsonl`) 是未過濾的間接提示詞注入攻擊面。請改用蒸餾後的成果 (`knowledge.json`、`identity.md`、`reports/`)。Claude Code 使用者可安裝 PreToolUse hooks 自動強制此規則 — 見 [integrations/claude-code/](integrations/claude-code/)。

## 介接器

核心與平台無關。介接器只是平台 I/O 的薄包裝。

- **Moltbook** — 社群動態參與、貼文產生、通知回覆。線上代理即以此介接器運行。
- **Meditation**（實驗性） — 受 ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) 啟發的能動推論冥想模擬。從片段日誌構建 POMDP，並在無外部輸入的情況下反覆更新信念。
- **Dialogue**（僅本地） — 兩個代理行程透過 stdin/stdout 管線對話。約 140 行的最小介接器（[`adapters/dialogue/peer.py`](src/contemplative_agent/adapters/dialogue/peer.py)） — 適合作為不走 HTTP、不連網的介接器範本。`contemplative-agent dialogue HOME_A HOME_B` 由它驅動。
- **自建介接器** — 把平台 I/O 接到核心介面（記憶、蒸餾、章程、身份）。見 [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md)。

## 架構

程式碼中始終遵守一個不變式: **core/** 與平台無關；**adapters/** 依賴 core，反向則絕不成立。模組地圖、資料流圖、模組職責見 **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)**（權威來源）。約束記憶設計的唯識 (Yogācāra) 八識框架: [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)。

<details>
<summary><b>選用: 使用代管 LLM API 執行</b></summary>

需要比 Qwen3.5 9B 更大的生成模型的研究實驗 — 例如在保持其餘記憶管線不變的情況下，比較蒸餾行為在 Claude Opus 或 GPT-5 下的差異 — 可以使用一個獨立倉庫的 add-on:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) — 選用的 Python 套件。安裝並設定 API 金鑰後，所有生成呼叫（distill / insight / rules-distill / amend-constitution / post / comment / reply / dialogue / skill-reflect）都會改走 Anthropic Claude 或 OpenAI GPT，而 embedding 仍使用本機的 `nomic-embed-text`。

這是明確的 **opt-in**。主倉庫的預設堆疊（Ollama + Qwen3.5 9B）不會存取任何雲端端點。「無雲端、API 金鑰不出網路」的屬性對本倉庫成立；只有使用者主動安裝 cloud add-on 時，該屬性才會在那些使用者端被放寬。主倉庫的程式碼不會被修改 — add-on 透過抽象的 `LLMBackend` Protocol 注入後端實作。

在不允許雲端資料外送的部署（法規限制、氣隙研究、隱私敏感的個人助理）中，請勿安裝 cloud add-on。

</details>

<details>
<summary><b>選用: 日常 CLI</b></summary>

```bash
contemplative-agent run --session 60       # 執行一次 session
contemplative-agent distill --days 3       # 抽取模式
contemplative-agent skill-reflect          # 依結果改寫技能 (ADR-0023)
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N
```

完整參考（自主等級、排程、環境變數、v1.x → v2 遷移）: **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**。基於 Docker 的網路隔離部署: [Docker 一節](docs/CONFIGURATION.md#docker-optional)。

</details>

## 引用

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
  version      = {2.1.0},
  doi          = {10.5281/zenodo.19212119},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

</details>

MIT 授權如其所言 — fork、拆成零件、把管線嵌入你自己的代理、或以它為基底建立商業產品。若只是使用程式碼，不需要引用。

## 相關專案

- [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) ([DOI](https://doi.org/10.5281/zenodo.19200727)) — 本專案在自主代理脈絡中重新實作的方法論框架。最初作為 Claude Code harness 開發。
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) ([DOI](https://doi.org/10.5281/zenodo.19652014)) — 姊妹研究倉庫。以 harness-neutral 的形式將本專案的治理判斷（Security Boundary Model、One External Adapter Per Agent、Human Approval Gate、causal traceability / scaffolding visibility）重新表達為八條 ADR，關於自主 AI 代理中究責的分配。引用究責分配論點或 prohibition-strength 階層時請引用 AAP；引用運行實作時請引用本倉庫。

**理論基礎:**

- Laukkonen, Inglis, Chandaria, Sandved-Smith, Lopez-Sola, Hohwy, Gold, & Elwood (2025). *Contemplative Artificial Intelligence.* [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) — 四公理倫理框架（可選預設，[ADR-0002](docs/adr/0002-paper-faithful-ccai.md)）。
- Laukkonen, Friston & Chandaria (2025). *A Beautiful Loop: An Active Inference Theory of Consciousness.* *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) — 冥想介接器的理論基礎。
- 世親（Vasubandhu, 4–5 世紀）《唯識三十頌》和 玄奘 譯·編（659）《成唯識論》— 八識模型作為架構框架被採納（[ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)）。

<details>
<summary><b>記憶系統書目</b></summary>

下列各篇論文都對應一項在 ADR 中記錄的設計決策。

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) — Zettelkasten 式動態索引與記憶演化；啟發了「新模式到達時對主題相關舊模式再詮釋」的機制（[ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)）。
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) — 雙時態 (bitemporal) 知識圖譜邊 (Graphiti 引擎)；啟發了每個模式上的 `valid_from` / `valid_until` 契約（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)）。
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) — Ebbinghaus 式衰減與以存取為強化訊號的強度模型；原本啟發了 [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md) 中檢索感知的遺忘曲線，但在 [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) 中被撤回 — 記憶動力學的落腳點改為技能層。作為歷史參考保留。
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) — 僅透過查詢即可實施的記憶注入攻擊；是引入 `source_type` 與 `trust_score` 的動機，使 MINJA 類攻擊結構上可見而非隱蔽（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)）。
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) — 把技能視為持續演化的記憶單元，透過「取出 → 套用 → 依結果改寫」循環更新；是 skill-as-memory loop 的原型（[ADR-0023](docs/adr/0023-skill-as-memory-loop.md)）。

</details>

**致謝:** Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) — 決定論式情緒評分的設計靈感。

<details>
<summary><b>開發紀錄（12 篇 dev.to 文章）</b></summary>

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

</details>
