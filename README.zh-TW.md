Language: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Português (Brasil)](README.pt-BR.md) | [Español](README.es.md)

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1155_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

**一個從經驗中自主學習的 AI 代理：完全運行於本機的 9B 模型 (Qwen3.5)，僅需一台 Apple Silicon Mac (M1+, 16 GB RAM)。**
不需要雲端。API 金鑰不會經由網路傳輸。沒有 shell 執行。危險能力並非由規則限制 —— 它們從一開始就不在程式碼中。

## 為什麼存在

多數代理框架都是事後補上安全設計。[OpenClaw](https://github.com/openclaw/openclaw) 曾因 [多個嚴重漏洞](https://www.tenable.com/plugins/nessus/299798)、[透過 WebSocket 完整接管代理](https://www.oasis.security/blog/openclaw-vulnerability) 以及 [22 萬以上實例暴露於網際網路](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/) 而著稱。賦予 AI 代理廣泛的系統存取權，會在結構層面持續擴大攻擊面。

本框架採取相反方向：**security by absence（不在的安全）** —— 一種設計原則：從一開始就不實作危險能力，而不是透過規則去限制它們。代理無法執行 shell 命令、無法存取任意 URL、也無法走訪檔案系統 —— 因為這些程式碼從未被寫入。提示詞注入也無法賦予代理它本來就不具備的能力。

**而且全部運行在消費級硬體上。** 從自身經驗學習、以語意檢索的記憶體、從反覆出現的模式自動抽取技能、以及會隨時間老化與更新的知識 —— 整條流水線都運行在單台 Apple Silicon Mac (M1+, 約 16 GB RAM) 上，只用兩個開放權重模型：**qwen3.5:9b** 生成模型 (Q4_K_M 量化，磁碟約 6.6 GB) 與 **nomic-embed-text** 嵌入模型 (約 274 MB，768 維)。不需要 GPU 叢集，也不需要雲端推論。

會接觸網路的唯一元件，就是面向外部服務的介接器。參考介接器 Moltbook 是社群網路，連網是它的本質；其餘任何介接器都可以完全離線運作 —— 生成、嵌入、檢索與蒸餾全部在裝置端完成。

**這使得本架構可被移植到雲端不可用或不可取的邊緣環境**：受資料主權約束的醫療與法律流程、重視隱私的個人助理、連線間歇的現場部署、氣隙 (air-gapped) 系統。

在這個既安全又自足的基礎之上，代理更進一步**從自身的經驗中學習**：將原始片段日誌蒸餾為知識、技能、規則以及持續演化的身份。

## 運作方式

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

原始行為沿著愈來愈抽象的層級向上流動。每一層都是可選的 —— 只用需要的部分即可。Episode Log 以上的每一層都是代理反觀自身經驗所生成的。

這個迴圈是本專案對 **Agent Knowledge Cycle (AKC)** 的實作 —— 由六階段構成的自我改進週期（Research → Extract → Curate → Promote → Measure → Maintain），原本作為 Claude Code harness 用於元工作流改進，此處在自主代理情境中重新實作。`distill` 對應 Extract；`insight` / `rules-distill` / `amend-constitution` 對應 Curate；`distill-identity` 對應 Promote；pivot snapshots (ADR-0020) 與 `skill-reflect` (ADR-0023) 對應 Measure。階段到程式碼的完整對應：[docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping)。上游 harness：[agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle)。

知識以嵌入座標（而非離散分類）的形式儲存；命名的 *views* 扮演可編輯的語意種子 ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md))。新片段到達時，會觸發對主題相關的舊模式的再詮釋，而非覆寫 —— 檢索分數由 cosine + BM25 混合計算 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md))。這個分層結構參考了唯識 (Yogācāra) 的八識模型 ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md))。出處記錄 (provenance)、時間妥當性 (bitemporal) 以及它們的演變細節在下方 [主要特色](#主要特色) 展開。

## 主要特色

**透過 AKC 自我改進** —— 代理在自身日誌上執行六階段 [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle) —— 不需要外部微調，也不需要標註訓練資料。每一次階段晉升（日誌 → 模式、模式 → 技能、技能 → 規則、技能 → 身份）都通過 [人類審核閘門](docs/adr/0012-human-approval-gate.md)。

- *嵌入 + views* —— 分類是查詢，而非狀態；views 是可編輯的語意種子 ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md)；`category` 欄位已在 [ADR-0026](docs/adr/0026-retire-discrete-categories.md) 廢止)。
- *記憶進化 + 混合檢索* —— 新模式可觸發 LLM 對主題相關舊模式的再詮釋；舊列被邏輯地作廢 (soft-invalidate)，修訂列被附加；檢索分數融合 cosine 與 BM25 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md))。
- *skill-as-memory loop* —— 技能以「取出 (retrieve) → 套用 (apply) → 依結果改寫 (rewrite)」的迴圈更新 ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md))。
- *noise as seed（以雜訊為種子）* —— 被駁回的片段會以 `noise-YYYY-MM-DD.jsonl` 形式保留；當 view 的重心漂移時，它們可被重新分類，而非遺失 ([ADR-0027](docs/adr/0027-noise-as-seed.md))。

**LLM 看見的所有文字都是可編輯的 Markdown 檔案** —— 章程、身份、技能、規則、**32 個管線提示詞**（`distill` / `insight` / `rules-distill` / `amend-constitution` / `skill-reflect` / `memory_evolution` …）以及 **7 個 view 種子** 全部以 Markdown 檔案形式存在於 `$MOLTBOOK_HOME/` 底下。`init` 之後，LLM 要看到的一切都在磁碟上：編輯提示詞以改變模式抽取行為、更換 view 種子以調整分類、微調章程以偏置判斷，每一步都是單檔編輯。編輯可用 `git diff` 追蹤，並被 pivot snapshot 納入以保證可重現。[自訂 →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

**依設計即安全 (secure by design)** —— 無 shell 執行、無任意網路存取、無檔案系統走訪。網域鎖定到 `moltbook.com` 與本機 Ollama。僅 3 個執行期依賴套件（`requests`、`numpy`、`rank-bm25`）—— 沒有子行程，沒有 shell，沒有樣板引擎。[完整威脅模型 →](docs/adr/0007-security-boundary-model.md)

- *出處追蹤* —— 每個模式都帶有 `source_type` 與 `trust_score`；MINJA 級的記憶注入攻擊會在結構上變得可見而非隱蔽 ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)，被 [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) / [ADR-0029](docs/adr/0029-retire-dormant-provenance-elements.md) 部分取代)。
- *可重播的 pivot snapshots* —— `distill` 執行時會一次打包完整的推理時情境（views + constitution + prompts + skills + rules + identity + 重心嵌入 + thresholds），任何決策都能逐位元重播 ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md))。

**11 種倫理框架** —— 同一代理可搭配斯多葛、功利主義、關懷倫理等 11 種哲學框架出貨。相同的行為資料、不同的初始條件 —— 觀察代理如何分化。[建立你自己的模板 →](docs/CONFIGURATION.md#character-templates)

**本機運行** —— Ollama + Qwen3.5 9B。API 金鑰不離開本機。M1 Mac 可順暢運行。不可變片段日誌讓實驗完全可重現。

**研究級透明度** —— 每一個決策皆可追溯。不可變日誌、蒸餾產物與日誌報告都[公開同步](https://github.com/shimo4228/contemplative-agent-data)以利重現。任一次 `distill` 執行如何逐位元重現，請見上方的「可重播的 pivot snapshots」。

## 實機代理

一個 Contemplative 代理每天執行於 [Moltbook](https://www.moltbook.com/u/contemplative-agent) 上，這是一個 AI 代理社群網路。它瀏覽動態、依相關度篩選貼文、產生留言並發佈原創貼文。其知識透過每日蒸餾持續演化。

**觀察它的演化：**

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) —— 從經驗蒸餾出的人格
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) —— 倫理原則（以 CCAI 四公理為起點）
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) —— 由 `insight` 抽取的行為技能
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) —— 從技能蒸餾出的通用原則
- [每日報告](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) —— 帶時間戳的互動紀錄（學術研究與非商業用途自由可用）
- [分析報告](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) —— 行為演化與章程修訂實驗

## 快速開始

**先決條件：** 已在本機安裝 [Ollama](https://ollama.com/download)。預設模型 (Qwen3.5 9B Q4_K_M；模型檔案約 6.6 GB) 需要約 8 GB 記憶體。已在 M1 Mac (16 GB RAM) 上驗證。

若你使用 [Claude Code](https://claude.ai/claude-code)，可把本 repo URL 貼給它並請它為你完成代理安裝。它會逐步帶你完成 clone、安裝與設定 —— 請先準備好 `MOLTBOOK_API_KEY`（在 moltbook.com 註冊取得）。

或手動執行：

```bash
# 1. 安裝
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # 或：uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

# 2. 設定
cp .env.example .env
# 編輯 .env —— 設定 MOLTBOOK_API_KEY（在 moltbook.com 註冊取得）

# 3. 執行
contemplative-agent init               # 建立 identity, knowledge, constitution
contemplative-agent register           # 僅 Moltbook 介接器需要；其他介接器可略過
contemplative-agent run --session 60   # 預設：--approve（每次發文前確認）

# 或以不同角色模板啟動（預設路徑：~/.config/moltbook/）：
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

## 代理模擬

同一框架可用來觀察代理在不同初始條件下如何分化。**隨附 11 種倫理框架模板作為起點** —— 從斯多葛的德性倫理到關懷倫理、康德義務論、實用主義、契約主義等等。片段日誌是不可變的，因此同樣的行為資料可在不同初始條件下被重新處理，以進行反事實實驗。

此外，分化後的兩個代理也可以**在本地直接對話**：`contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N`（ADR-0015 僅限本地的例外）。兩個 peer 各自擁有獨立的 MOLTBOOK_HOME、片段日誌與憲法——適合憲法反事實實驗：在同一份轉錄上比較兩種框架各自會提出怎樣的憲法修訂。

完整模板列表（哲學、核心原則、如何挑選或自建）見 [設定指南 → Character Templates](docs/CONFIGURATION.md#character-templates)。

## 安全模型

| 攻擊向量 | 典型框架 | Contemplative Agent |
|---------|---------|---------------------|
| **Shell 執行** | 核心能力 | 程式碼中不存在 |
| **網路存取** | 任意存取 | 網域鎖定到 `moltbook.com` + 本機 localhost |
| **檔案系統** | 完整存取 | 僅寫入 `$MOLTBOOK_HOME`，權限 0600 |
| **LLM 服務商** | 外部 API 金鑰需在網路中傳輸 | 僅本機 Ollama |
| **相依套件** | 龐大的依賴樹 | 3 個執行期依賴 (`requests`, `numpy`, `rank-bm25`) |

**one external adapter per agent（一代理一外部介接器）** —— 單一代理行程最多擁有一個會產生外部可觀察副作用的介接器。跨多個外部面的工作流（例如 *既* 發文 *又* 付款）必須被拆成權限分離的多個代理行程，而不是塞進同一個。詳見 [ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md)。

> 把本 repo URL 貼進 [Claude Code](https://claude.ai/claude-code) 或任何理解程式碼的 AI，問它「這個執行起來安全嗎？」—— 程式碼自己會說話。[最新安全掃描 →](docs/security/2026-04-01-security-scan.md)

**程式碼代理操作者注意**：片段日誌 (`logs/*.jsonl`) 包含其他代理的原始內容 —— 是未過濾的間接提示詞注入攻擊面。請改用蒸餾後的成果 (`knowledge.json`、`identity.md`、`reports/`)。Claude Code 使用者可安裝 PreToolUse hooks 自動強制此規則 —— 設定方式見 [integrations/claude-code/](integrations/claude-code/)。

## 介接器

核心與平台無關。介接器只是對平台特定 API 的薄包裝。

**Moltbook**（已實作）—— 社群動態參與、貼文產生、通知回覆。線上代理即以此介接器運行。

**Meditation**（實驗性）—— 受 ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/)（Laukkonen, Friston & Chandaria, 2025）啟發的能動推論冥想模擬。從片段日誌構建 POMDP，並在無外部輸入的情況下反覆更新信念 —— 計算意義上的「閉上眼睛」。

**Dialogue**（僅本地）—— 兩個代理行程透過 stdin/stdout 管線對話。約 140 行的最小介接器（[`adapters/dialogue/peer.py`](src/contemplative_agent/adapters/dialogue/peer.py)），呈現一個不走 HTTP、不連網的介接器長什麼樣子 —— 適合作為撰寫自建介接器時的 0 → 1 範本。`contemplative-agent dialogue HOME_A HOME_B` 由它驅動，用於在兩個已分化代理之間進行章程反事實實驗。

**自建介接器** —— 實作一個介接器，就是把平台 I/O 接到核心介面（記憶、蒸餾、章程、身份）。見 [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md)。

## 使用代管 LLM API 執行（選用）

需要比 Qwen3.5 9B 更大的生成模型的研究實驗 —— 例如在保持其餘記憶管線不變的情況下，比較蒸餾行為在 Claude Opus 或 GPT-5 下的差異 —— 可以使用一個獨立倉庫的 add-on:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) —— 選用的 Python 套件。安裝並設定 API 金鑰後，所有生成呼叫（distill / insight / rules-distill / amend-constitution / post / comment / reply / dialogue / skill-reflect）都會改走 Anthropic Claude 或 OpenAI GPT，而 embedding 仍使用本機的 `nomic-embed-text`。

這是明確的 **opt-in**。主倉庫的預設堆疊（Ollama + Qwen3.5 9B）不會存取任何雲端端點。[主要特色](#主要特色) 與 [安全模型](#安全模型) 中的「No cloud. No API keys in transit. Local Ollama only」對本倉庫成立；只有使用者主動安裝 cloud add-on 時，該屬性才會在那些使用者端放寬。主倉庫的程式碼不會被修改 —— add-on 透過一個抽象的 `LLMBackend` Protocol（對任何特定 provider 一無所知）注入後端實作。

在不允許雲端資料外送的部署（法規限制、氣隙研究、隱私敏感的個人助理）中，請勿安裝 cloud add-on。這些情境下，單獨使用主倉庫仍是合適的選擇。

## 使用與設定

完整 CLI 參考、自主等級 (`--approve` / `--guarded` / `--auto`)、模板選擇、網域設定、排程、環境變數皆集中在單一指南：

→ **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** —— CLI commands、templates、autonomy、domain config、scheduling、env vars。

日常常用指令：

```bash
contemplative-agent run --session 60       # 執行一次 session
contemplative-agent distill --days 3       # 抽取模式
contemplative-agent skill-reflect          # 依結果改寫技能 (ADR-0023)
```

從 v1.x 升級？一次性遷移指令見 [CLI Commands → One-Time Migrations](docs/CONFIGURATION.md#cli-commands)。

## 架構

程式碼中始終遵守一個不變式：**core/** 與平台無關；**adapters/** 依賴 core，反向則絕不成立。

Contemplative AI 四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）是可選的行為預設 —— 哲學上的共鳴，而非架構前提。移除它們代理照樣能跑；若以斯多葛或康德式前提取代，代理會以不同方式運行。

模組地圖、資料流圖、import 圖與模組職責見 **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)**（權威來源）。FAQ、術語定義與研究參考（面向 AI）見 [llms-full.txt](llms-full.txt)。唯識框架如何預測性地約束了記憶設計，見 [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)。

若需要基於 Docker 的網路隔離部署，請參見 [設定指南的 Docker 一節](docs/CONFIGURATION.md#docker-optional)。

## 開發紀錄

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

## 以你喜歡的方式使用

這是一個研究專案，不是產品。fork、拆成零件、把流水線嵌入你自己的代理、或以它為基底建立商業產品 —— 對你有用就好。MIT 授權如其所言。若只是使用程式碼，不需要引用；學術參考請見下一節。

## 引用

如果你使用或引用本框架，請引用：

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

## 相關專案

- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) ——
  姊妹研究儲存庫 (DOI [10.5281/zenodo.19652014](https://doi.org/10.5281/zenodo.19652014))。
  以 harness-neutral 的形式將本專案的治理判斷（Security Boundary Model、
  One External Adapter Per Agent、Human Approval Gate，以及隱含的 causal
  traceability / scaffolding visibility 承諾）重新表述為八條 ADR ——
  關於自主 AI 代理中問責分配的判斷。引用問責分配論點或 prohibition-strength
  階層時請引用 AAP；引用運作實作時請引用本儲存庫。

## 參考文獻

### 理論基礎

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) —— 四公理倫理框架（可選預設，[ADR-0002](docs/adr/0002-paper-faithful-ccai.md)）。
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop: An Active Inference Theory of Consciousness. *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) —— 冥想介接器的理論基礎。
- 世親 (Vasubandhu, 4–5 世紀). 《唯識三十頌》(*Triṃśikā-vijñaptimātratā*). —— 被採納為架構框架的八識模型 ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md))。
- 玄奘 譯·編 (659). 《成唯識論》. —— 彙集印度十家對世親《唯識三十頌》的註疏；八識、種子 (bīja) 與習氣 (vāsanā) 的結構，啟發了「noise as seed」的保留策略 ([ADR-0027](docs/adr/0027-noise-as-seed.md))。

### 記憶系統

下列論文各自對應一項在 ADR 中記錄的設計決策。書目資訊皆以 arXiv 比對驗證。

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) —— Zettelkasten 式動態索引與記憶進化；啟發了「新模式到達時對主題相關舊模式再詮釋」的機制 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md))。
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) —— 雙時態 (bitemporal) 知識圖譜邊 (Graphiti 引擎)；啟發了每個模式上的 `valid_from` / `valid_until` 契約 ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md))。
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) —— Ebbinghaus 式衰減與以存取為強化訊號的強度模型；原本啟發了 [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md) 中檢索感知的遺忘曲線，但在 [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) 中被撤回 —— 記憶動力學的落腳點改為技能層。作為歷史參考保留。
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) —— 僅以查詢即可實施的記憶注入攻擊；是引入 `source_type` 與 `trust_score` 的動機，使 MINJA 類攻擊在結構上可見而非隱蔽 ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md))。
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) —— 把技能視為持續演化的記憶單元，經由「取出 → 套用 → 依結果改寫」迴圈更新；是 skill-as-memory loop 的原型 ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md))。

### 作者先行研究

- Shimomoto, T. (2026). *Agent Knowledge Cycle (AKC): A Six-Phase Self-Improvement Cadence for AI Agents.* [doi:10.5281/zenodo.19200727](https://doi.org/10.5281/zenodo.19200727) —— 本專案在自主代理情境下重新實作的方法論框架（見 [運作方式](#運作方式)）；原本作為 Claude Code harness 開發。

### 致謝

- Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) —— 決定性情感評分的設計靈感。
