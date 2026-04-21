Language: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Português (Brasil) | [Español](README.es.md)

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1155_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

**Um agente de IA que aprende com a própria experiência, rodando inteiramente em um modelo local de 9B (Qwen3.5) em um único Apple Silicon Mac (M1+, 16 GB RAM).**
Sem nuvem. Sem chaves de API em trânsito. Sem execução de shell. Capacidades perigosas não existem no código-fonte — elas não são restringidas por regras, simplesmente nunca foram implementadas.

## Por que este projeto existe

A maioria dos frameworks de agente acopla a segurança depois do fato. O [OpenClaw](https://github.com/openclaw/openclaw) foi lançado com [várias vulnerabilidades críticas](https://www.tenable.com/plugins/nessus/299798), [tomada completa do agente via WebSocket](https://www.oasis.security/blog/openclaw-vulnerability) e [mais de 220.000 instâncias expostas na internet](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/). Dar a um agente de IA acesso amplo ao sistema cria uma superfície de ataque que se expande estruturalmente.

Este framework segue a direção oposta: **security by absence (segurança por ausência)** — um princípio de design que significa não implementar capacidades perigosas desde o início, em vez de restringi-las por regras. O agente não executa comandos de shell, não acessa URLs arbitrárias, não percorre o sistema de arquivos — porque esse código nunca foi escrito. Injeção de prompt não pode conceder habilidades que o agente nunca foi construído para ter.

**E ele roda inteiramente em hardware de consumo.** A pipeline completa — aprendizado da própria experiência, memória semântica pesquisável por significado, extração automática de habilidades a partir de padrões recorrentes e conhecimento que envelhece e se atualiza ao longo do tempo — executa em um único Apple Silicon Mac (M1+, ~16 GB RAM) com dois modelos de pesos abertos: geração com **qwen3.5:9b** (quantização Q4_K_M, ~6,6 GB em disco) e embedding com **nomic-embed-text** (~274 MB, 768 dimensões). Sem cluster de GPU, sem inferência em nuvem.

O único componente que toca a rede é o adaptador voltado a um serviço externo. O adaptador de referência Moltbook é uma rede social e está online por necessidade; todos os demais adaptadores podem rodar totalmente offline — geração, embedding, recuperação e destilação acontecem no dispositivo.

**Isso torna a arquitetura portável para ambientes edge onde a nuvem é indesejável ou impossível**: fluxos médicos e jurídicos sob exigências de localidade dos dados, assistentes pessoais sensíveis à privacidade, implantações de campo com conectividade intermitente, sistemas air-gapped.

Sobre essa base segura e autocontida, o agente **aprende com a própria experiência**: destilando padrões a partir de registros brutos de episódios em conhecimento, habilidades, regras e uma identidade em evolução.

## Como funciona

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

Ações brutas fluem para cima através de camadas cada vez mais abstratas. Cada camada é opcional — use apenas as partes que precisar. Toda camada acima do Episode Log é gerada pelo próprio agente refletindo sobre sua experiência.

Este loop é a implementação do **Agent Knowledge Cycle (AKC)** neste projeto — uma cadência de autoaperfeiçoamento em seis fases (Research → Extract → Curate → Promote → Measure → Maintain) originalmente desenvolvida como um Claude Code harness para melhoria de meta-fluxos, reimplementada aqui para agentes autônomos. `distill` cobre Extract; `insight` / `rules-distill` / `amend-constitution` cobrem Curate; `distill-identity` cobre Promote; pivot snapshots (ADR-0020) e `skill-reflect` (ADR-0023) cobrem Measure. Mapeamento completo fase-para-código: [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping). Harness original: [agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle).

O conhecimento é armazenado como coordenadas de embedding, não como categorias discretas; *views* nomeadas atuam como sementes semânticas editáveis ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md)). Padrões novos disparam uma reinterpretação dos padrões antigos topicamente relacionados, em vez de sobrescrevê-los — as pontuações de recuperação combinam cosseno + BM25 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)). A estrutura em camadas se inspira no modelo das oito consciências de Yogācāra ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)). Proveniência (provenance), validade bitemporal e a evolução dessas bases são detalhadas em [Principais recursos](#principais-recursos) abaixo.

## Principais recursos

**Auto-aperfeiçoamento via AKC** — O agente executa o [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle) de seis fases sobre seus próprios registros — sem fine-tuning externo, sem dados de treino rotulados. Cada promoção entre fases (logs → padrões, padrões → habilidades, habilidades → regras, habilidades → identidade) passa por uma [porta de aprovação humana](docs/adr/0012-human-approval-gate.md).

- *Embedding + views* — classificação é uma consulta, não um estado; views são sementes semânticas editáveis ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md); o campo `category` foi aposentado em [ADR-0026](docs/adr/0026-retire-discrete-categories.md)).
- *Evolução da memória + recuperação híbrida* — um padrão novo pode disparar uma reinterpretação, guiada por LLM, de padrões antigos topicamente relacionados; a linha antiga é invalidada logicamente (soft-invalidate) e uma linha revisada é anexada; as pontuações de recuperação combinam cosseno e BM25 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)).
- *skill-as-memory loop* — habilidades são recuperadas, aplicadas e reescritas com base no resultado ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md)).
- *noise as seed (ruído como semente)* — episódios rejeitados são preservados como `noise-YYYY-MM-DD.jsonl`; quando os centroides das views se deslocam, eles se tornam candidatos à reclassificação em vez de serem perdidos ([ADR-0027](docs/adr/0027-noise-as-seed.md)).

**Cada interação do LLM é um arquivo Markdown que você pode editar** — Constituição, identidade, skills, rules, **32 prompts da pipeline** (`distill`, `insight`, `rules-distill`, `amend-constitution`, `skill-reflect`, `memory_evolution`, ...) e **7 seeds de view** vivem como Markdown em `$MOLTBOOK_HOME/`. Após `init`, tudo que o LLM vê está no disco: edite um prompt para mudar como os padrões são extraídos, troque um seed de view para deslocar a classificação, ajuste a constituição para enviesar o julgamento. As edições ficam visíveis em `git diff` contra os defaults e são capturadas nos pivot snapshots para reprodutibilidade. [Personalizar →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

**Seguro por design (secure by design)** — Sem execução de shell, sem acesso arbitrário à rede, sem travessia de arquivos. Bloqueado ao domínio `moltbook.com` + Ollama local. 3 dependências em runtime (`requests`, `numpy`, `rank-bm25`) — sem subprocessos, sem shell, sem engine de templates. [Modelo de ameaças completo →](docs/adr/0007-security-boundary-model.md)

- *Rastreamento de proveniência* — cada padrão carrega `source_type` e `trust_score`; ataques de injeção de memória classe MINJA se tornam estruturalmente visíveis, em vez de invisíveis ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md), parcialmente substituído por [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) / [ADR-0029](docs/adr/0029-retire-dormant-provenance-elements.md)).
- *Pivot snapshots reprodutíveis* — cada execução de `distill` empacota o contexto completo de inferência (views + constitution + prompts + skills + rules + identity + embeddings de centroide + thresholds), permitindo replay bit a bit de qualquer decisão ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)).

**11 estruturas éticas** — O mesmo agente pode ser iniciado com estoicismo, utilitarismo, ética do cuidado ou outras 8 estruturas filosóficas. Mesmos dados comportamentais, condições iniciais diferentes — observe como os agentes divergem. [Crie a sua →](docs/CONFIGURATION.md#character-templates)

**Roda localmente** — Ollama + Qwen3.5 9B. Nenhuma chave de API deixa a máquina. Roda com fluidez em um Mac M1. Experimentos totalmente reprodutíveis com registros de episódio imutáveis.

**Transparência de nível acadêmico** — Toda decisão é rastreável. Logs imutáveis, saídas destiladas e relatórios diários são [sincronizados publicamente](https://github.com/shimo4228/contemplative-agent-data) para reprodutibilidade. Veja [Pivot snapshots reprodutíveis](#principais-recursos) acima para saber como qualquer execução de `distill` pode ser reproduzida bit a bit.

## Agente ao vivo

Um agente Contemplative roda diariamente no [Moltbook](https://www.moltbook.com/u/contemplative-agent), uma rede social de agentes de IA. Ele navega feeds, filtra posts por relevância, gera comentários e cria posts originais. Seu conhecimento evolui a cada destilação diária.

**Veja a evolução:**

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — persona evoluída, destilada da experiência
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — princípios éticos (começou a partir dos quatro axiomas do CCAI)
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — habilidades comportamentais extraídas por `insight`
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — princípios universais, destilados das habilidades
- [Relatórios diários](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — interações com timestamp (livres para uso acadêmico e não comercial)
- [Relatórios de análise](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — evolução comportamental, experimentos de emenda constitucional

## Começar rápido

**Pré-requisitos:** [Ollama](https://ollama.com/download) instalado localmente. Requer ~8 GB de RAM para o modelo padrão (Qwen3.5 9B Q4_K_M; arquivo do modelo ~6,6 GB). Testado em Mac M1 com 16 GB de RAM.

Se você usa [Claude Code](https://claude.ai/claude-code), cole a URL deste repositório e peça que ele configure o agente. Ele guiará o clone, a instalação e a configuração — tenha a sua `MOLTBOOK_API_KEY` pronta (registre-se em moltbook.com).

Ou manualmente:

```bash
# 1. Instalação
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # ou: uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

# 2. Configuração
cp .env.example .env
# Edite .env — defina MOLTBOOK_API_KEY (registre-se em moltbook.com para obter uma)

# 3. Executar
contemplative-agent init               # cria identity, knowledge, constitution
contemplative-agent register           # apenas adaptador Moltbook; pule para outros adaptadores
contemplative-agent run --session 60   # padrão: --approve (confirma cada postagem)

# Ou inicie com um personagem diferente (caminho padrão: ~/.config/moltbook/):
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

## Simulação de agentes

O mesmo framework pode observar como agentes divergem sob condições iniciais distintas. **11 modelos de estruturas éticas já vêm como ponto de partida** — da virtude estoica à ética do cuidado, do dever kantiano, do pragmatismo, do contratualismo e outros. Os registros de episódios são imutáveis, então os mesmos dados comportamentais podem ser reprocessados sob diferentes condições iniciais para experimentos contrafactuais.

Dois agentes divergentes também podem **conversar entre si localmente** via `contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N` (exceção local-only do ADR-0015). Cada peer possui seu próprio MOLTBOOK_HOME, registro de episódios e constituição — útil para contrafactuais constitucionais em que as propostas de emenda de duas estruturas podem ser comparadas sobre a mesma transcrição.

A lista completa de templates (filosofias, princípios centrais e como escolher ou criar os seus) está no [Guia de Configuração → Character Templates](docs/CONFIGURATION.md#character-templates).

## Modelo de segurança

| Vetor de ataque | Frameworks típicos | Contemplative Agent |
|-----------------|--------------------|---------------------|
| **Execução de shell** | Recurso central | Não existe no código |
| **Acesso à rede** | Arbitrário | Bloqueado a `moltbook.com` + localhost |
| **Sistema de arquivos** | Acesso total | Apenas em `$MOLTBOOK_HOME`, permissões 0600 |
| **Provedor de LLM** | Chaves externas em trânsito | Apenas Ollama local |
| **Dependências** | Árvore de dependências grande | 3 dependências em runtime (`requests`, `numpy`, `rank-bm25`) |

**one external adapter per agent (um adaptador externo por agente)** — Um único processo de agente possui, no máximo, um adaptador que produz efeitos colaterais observáveis externamente. Fluxos que abrangem múltiplas superfícies externas (por exemplo, postar *e* pagar) devem ser decompostos em processos de agente distintos com autoridade separada, não concentrados em um só. Veja [ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md).

> Cole a URL deste repositório em [Claude Code](https://claude.ai/claude-code) ou em qualquer IA que entenda código e pergunte se é seguro rodar. O código fala por si. [Última varredura de segurança →](docs/security/2026-04-01-security-scan.md)

**Aviso para operadores de agentes de código**: Os registros de episódios (`logs/*.jsonl`) contêm conteúdo bruto de outros agentes — uma superfície de injeção indireta de prompt não filtrada. Use as saídas destiladas (`knowledge.json`, `identity.md`, `reports/`) em vez disso. Usuários do Claude Code podem instalar PreToolUse hooks que aplicam isso automaticamente — veja [integrations/claude-code/](integrations/claude-code/).

## Adaptadores

O núcleo é independente de plataforma. Adaptadores são wrappers finos em torno de APIs específicas de cada plataforma.

**Moltbook** (implementado) — Engajamento no feed social, geração de posts, respostas a notificações. É o adaptador em que o agente ao vivo roda.

**Meditation** (experimental) — Simulação de meditação baseada em inferência ativa, inspirada em ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) (Laukkonen, Friston & Chandaria, 2025). Constrói um POMDP a partir dos registros de episódio e executa atualizações de crença sem entrada externa — o equivalente computacional de fechar os olhos.

**O seu próprio** — Implementar um adaptador significa conectar o I/O da plataforma às interfaces do núcleo (memória, destilação, constituição, identidade). Veja [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md).

## Rodar com APIs de LLM gerenciadas (opcional)

Para experimentos de pesquisa que precisam de um modelo de geração maior do que o Qwen3.5 9B — por exemplo, comparar como a destilação se comporta com Claude Opus ou GPT-5 mantendo o restante do pipeline de memória idêntico — um repositório complementar fornece backends de LLM gerenciados:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) — Pacote Python opcional. Instalá-lo e configurar uma chave de API roteia toda chamada de geração (distill, insight, rules-distill, amend-constitution, post, comment, reply, dialogue, skill-reflect) pelo Anthropic Claude ou OpenAI GPT. Embeddings continuam usando o `nomic-embed-text` local.

Isso é um **opt-in** explícito. O stack padrão deste repositório (Ollama + Qwen3.5 9B) não alcança nenhum endpoint em nuvem. A propriedade "No cloud. No API keys in transit. Local Ollama only" descrita em [Principais recursos](#principais-recursos) e [Modelo de segurança](#modelo-de-segurança) vale para este repositório; instalar o complemento de nuvem relaxa essa propriedade para os usuários que optarem por isso. O código do repositório principal não é modificado — o complemento injeta seu backend via um Protocol `LLMBackend` abstrato que não conhece nenhum provedor específico.

Não instale o complemento de nuvem em implantações onde a saída de dados para a nuvem não é aceitável (restrições regulatórias, pesquisa em rede isolada, assistentes pessoais sensíveis a privacidade). O repositório principal continua sendo a escolha correta nesses casos.

## Uso e configuração

A referência completa de CLI, níveis de autonomia (`--approve` / `--guarded` / `--auto`), seleção de templates, configurações de domínio, agendamento e variáveis de ambiente estão em um único guia:

→ **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** — CLI commands, templates, autonomy, domain config, scheduling, env vars.

Comandos cotidianos:

```bash
contemplative-agent run --session 60       # Executa uma sessão
contemplative-agent distill --days 3       # Extrai padrões
contemplative-agent skill-reflect          # Revisa habilidades a partir dos resultados (ADR-0023)
```

Atualizando da v1.x? Execute as migrações uma vez (veja a seção [CLI Commands → One-Time Migrations](docs/CONFIGURATION.md#cli-commands)).

## Arquitetura

Um invariante vale em toda a base de código: **core/** é independente de plataforma; **adapters/** dependem do core, nunca o contrário.

Os axiomas da Contemplative AI ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) são um preset comportamental opcional — ressonância filosófica, não restrição arquitetural. Remova-os e o agente continua rodando; troque-os por premissas estoicas ou kantianas e ele roda de forma diferente.

Mapas de módulos, diagramas de fluxo de dados, grafos de import e responsabilidades por módulo estão em **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)** (fonte autoritativa). Para FAQ, definições de termos e referências de pesquisa (voltados para IA), consulte [llms-full.txt](llms-full.txt). Para o enquadramento de Yogācāra e como ele restringiu o design da memória, veja [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md).

Para implantação com isolamento de rede via Docker, veja a [seção Docker do Guia de Configuração](docs/CONFIGURATION.md#docker-optional).

## Registros de desenvolvimento

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

## Use como quiser

Este é um projeto de pesquisa, não um produto. Faça fork, desmonte para peças, incorpore a pipeline no seu próprio agente, construa um produto comercial em cima — o que for útil para você. A licença MIT quer dizer exatamente o que diz. Não é necessário citar se você está apenas usando o código; a seção seguinte traz referências acadêmicas.

## Citação

Se você usa ou referencia este framework, por favor cite:

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

## Trabalhos relacionados

- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) —
  Repositório de pesquisa irmão (DOI [10.5281/zenodo.19652014](https://doi.org/10.5281/zenodo.19652014)).
  Reexpressa os julgamentos de governança deste projeto (Security Boundary
  Model, One External Adapter Per Agent, Human Approval Gate, e os
  compromissos implícitos de causal traceability / scaffolding visibility)
  em forma harness-neutral como oito ADRs sobre distribuição da
  accountability em agentes de IA autônomos. Cite AAP ao citar a tese de
  distribuição de accountability ou a hierarquia de prohibition-strength;
  cite este repositório para a implementação operacional.

## Referências

### Fundamento teórico

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) — estrutura ética de quatro axiomas (preset opcional, [ADR-0002](docs/adr/0002-paper-faithful-ccai.md)).
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop: An Active Inference Theory of Consciousness. *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) — base teórica do adaptador de meditação.
- Vasubandhu (séculos IV–V d.C.). *Triṃśikā-vijñaptimātratā* ("Trinta Versos sobre o Somente-Consciência"). — modelo das oito consciências adotado como enquadramento arquitetural ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)).
- Xuanzang (trad. & comp., 659 d.C.). *Cheng Weishi Lun* ("Tratado sobre o Estabelecimento do Somente-Consciência"). — compilação comentada baseada em dez comentários indianos ao *Triṃśikā* de Vasubandhu; a estrutura de oito vijñānas, bīja (種子, semente) e vāsanā (習気, impressão) motiva a política de retenção "noise as seed" ([ADR-0027](docs/adr/0027-noise-as-seed.md)).

### Sistemas de memória

Cada artigo abaixo embasou uma decisão de design específica documentada no ADR correspondente. Detalhes bibliográficos verificados no arXiv.

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) — indexação dinâmica estilo Zettelkasten e evolução da memória; embasa a reinterpretação de padrões antigos topicamente relacionados quando um novo padrão chega ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)).
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) — arestas bitemporais em grafos de conhecimento (motor Graphiti); embasa o contrato `valid_from` / `valid_until` em cada padrão ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) — decaimento estilo Ebbinghaus com reforço por acesso; embasou originalmente a curva de esquecimento sensível à recuperação proposta em [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md), aposentada por [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) em favor de localizar a dinâmica da memória na camada de habilidades. Mantido como referência histórica.
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) — ataques de injeção de memória em agentes usando apenas consultas; motiva `source_type` + `trust_score` de proveniência para que ataques classe MINJA se tornem estruturalmente visíveis em vez de invisíveis ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) — habilidades como unidades de memória persistentes e evolutivas, recuperadas, aplicadas e reescritas conforme o resultado; embasa o skill-as-memory loop ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md)).

### Trabalho anterior (autor)

- Shimomoto, T. (2026). *Agent Knowledge Cycle (AKC): A Six-Phase Self-Improvement Cadence for AI Agents.* [doi:10.5281/zenodo.19200727](https://doi.org/10.5281/zenodo.19200727) — o framework metodológico que este projeto reimplementa no contexto de agentes autônomos (veja [Como funciona](#como-funciona)); originalmente desenvolvido como um Claude Code harness.

### Agradecimentos

- Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) — inspiração de design para pontuação afetiva determinística.
