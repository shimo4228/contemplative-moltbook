Language: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Português (Brasil)](README.pt-BR.md) | Español

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1115_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

**Un agente de IA que aprende de su propia experiencia, ejecutándose por completo en un modelo local de 9B (Qwen3.5) en un único Apple Silicon Mac (M1+, 16 GB de RAM).**
Sin nube. Sin claves de API en tránsito. Sin ejecución de shell. Las capacidades peligrosas no existen en el código — no están restringidas por reglas, simplemente nunca se construyeron.

## Por qué existe

La mayoría de los frameworks de agentes añade la seguridad después de los hechos. [OpenClaw](https://github.com/openclaw/openclaw) se publicó con [varias vulnerabilidades críticas](https://www.tenable.com/plugins/nessus/299798), [toma completa del agente vía WebSocket](https://www.oasis.security/blog/openclaw-vulnerability) y [más de 220 000 instancias expuestas en Internet](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/). Dar a un agente de IA acceso amplio al sistema crea una superficie de ataque que se expande estructuralmente.

Este framework toma el camino opuesto: **security by absence (seguridad por ausencia)** — un principio de diseño que consiste en no implementar capacidades peligrosas desde el principio, en lugar de restringirlas mediante reglas. El agente no puede ejecutar comandos de shell, no puede acceder a URLs arbitrarias, no puede recorrer el sistema de archivos — porque ese código nunca se escribió. La inyección de prompt no puede otorgar habilidades que el agente nunca fue construido para tener.

**Y todo esto corre íntegramente en hardware de consumo.** La pipeline completa — aprender de la propia experiencia, una memoria semántica consultable por significado, extracción automática de habilidades a partir de patrones recurrentes y conocimiento que envejece y se actualiza con el tiempo — se ejecuta en un único Apple Silicon Mac (M1+, ~16 GB de RAM) con dos modelos de pesos abiertos: generación con **qwen3.5:9b** (cuantización Q4_K_M, ~6,6 GB en disco) y embedding con **nomic-embed-text** (~274 MB, 768 dimensiones). Sin clúster de GPU, sin inferencia en la nube.

El único componente que toca la red es el adaptador orientado a un servicio externo. El adaptador de referencia Moltbook es una red social y está en línea por necesidad; cualquier otro adaptador puede funcionar totalmente sin conexión — generación, embedding, recuperación y destilación ocurren en el dispositivo.

**Esto hace que la arquitectura sea portable a entornos edge donde la nube no es deseable o no es posible**: flujos médicos y legales con exigencias de localidad de datos, asistentes personales sensibles a la privacidad, despliegues de campo con conectividad intermitente, sistemas air-gapped.

Sobre esa base segura y autocontenida, el agente **aprende de su propia experiencia**: destila patrones a partir de los registros crudos de episodios en conocimiento, habilidades, reglas y una identidad que evoluciona.

## Cómo funciona

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

Las acciones crudas fluyen hacia arriba a través de capas cada vez más abstractas. Cada capa es opcional — usa solo las partes que necesites. Toda capa por encima del Episode Log se genera por el propio agente al reflexionar sobre su experiencia.

Este bucle es la implementación del **Agent Knowledge Cycle (AKC)** en este proyecto — una cadencia de automejora en seis fases (Research → Extract → Curate → Promote → Measure → Maintain) originalmente desarrollada como un Claude Code harness para mejorar meta-flujos, y reimplementada aquí para agentes autónomos. `distill` cubre Extract; `insight` / `rules-distill` / `amend-constitution` cubren Curate; `distill-identity` cubre Promote; los pivot snapshots (ADR-0020) y `skill-reflect` (ADR-0023) cubren Measure. Mapeo completo fase-a-código: [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping). Harness original: [agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle).

El conocimiento se almacena como coordenadas de embedding, no como categorías discretas; las *views* nombradas actúan como semillas semánticas editables ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md)). Los nuevos patrones disparan una reinterpretación de los antiguos relacionados temáticamente en lugar de sobrescribirlos — las puntuaciones de recuperación combinan coseno + BM25 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)). La estructura por capas se inspira en el modelo de las ocho conciencias de Yogācāra ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)). La procedencia (provenance), la validez bitemporal y la evolución de estos fundamentos se detallan en [Características principales](#características-principales) más abajo.

## Características principales

**Automejora vía AKC** — El agente ejecuta el [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle) de seis fases sobre sus propios registros — sin fine-tuning externo, sin datos de entrenamiento etiquetados. Cada promoción de fase (logs → patrones, patrones → habilidades, habilidades → reglas, habilidades → identidad) pasa por una [puerta de aprobación humana](docs/adr/0012-human-approval-gate.md).

- *Embedding + views* — la clasificación es una consulta, no un estado; las views son semillas semánticas editables ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md); el campo `category` se retiró en [ADR-0026](docs/adr/0026-retire-discrete-categories.md)).
- *Evolución de la memoria + recuperación híbrida* — un patrón nuevo puede disparar una reinterpretación, dirigida por LLM, de patrones antiguos relacionados temáticamente; la fila antigua se invalida lógicamente (soft-invalidate) y se añade una fila revisada; las puntuaciones de recuperación combinan coseno y BM25 ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)).
- *skill-as-memory loop* — las habilidades se recuperan, se aplican y se reescriben según el resultado ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md)).
- *noise as seed (ruido como semilla)* — los episodios rechazados se conservan como `noise-YYYY-MM-DD.jsonl`; cuando los centroides de las views se desplazan, quedan disponibles para reclasificación en lugar de perderse ([ADR-0027](docs/adr/0027-noise-as-seed.md)).

**Cada interacción del LLM es un archivo Markdown que puedes editar** — Constitución, identidad, skills, rules, **29 prompts del pipeline** (`distill`, `insight`, `rules-distill`, `amend-constitution`, `skill-reflect`, `memory_evolution`, ...) y **7 seeds de view** viven como Markdown bajo `$MOLTBOOK_HOME/`. Tras `init`, todo lo que el LLM verá está en disco: edita un prompt para cambiar cómo se extraen los patrones, cambia un seed de view para desplazar la clasificación, ajusta la constitución para sesgar el juicio. Los cambios son visibles con `git diff` frente a los defaults y quedan capturados en los pivot snapshots para reproducibilidad. [Personalizar →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

**Seguro por diseño (secure by design)** — Sin ejecución de shell, sin acceso arbitrario a la red, sin recorrido del sistema de archivos. Bloqueado al dominio `moltbook.com` + Ollama local. 3 dependencias en runtime (`requests`, `numpy`, `rank-bm25`) — sin subprocesos, sin shell, sin motor de plantillas. [Modelo de amenazas completo →](docs/adr/0007-security-boundary-model.md)

- *Seguimiento de procedencia* — cada patrón lleva `source_type` y `trust_score`; los ataques de inyección de memoria tipo MINJA se vuelven estructuralmente visibles en lugar de invisibles ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md), parcialmente sustituido por [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) / [ADR-0029](docs/adr/0029-retire-dormant-provenance-elements.md)).
- *Pivot snapshots reproducibles* — cada ejecución de `distill` empaqueta el contexto completo de inferencia (views + constitution + prompts + skills + rules + identity + embeddings de centroide + thresholds), de modo que cualquier decisión puede reproducirse bit a bit ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)).

**11 marcos éticos** — El mismo agente puede arrancar con estoicismo, utilitarismo, ética del cuidado u otros 8 marcos filosóficos. Mismos datos de comportamiento, condiciones iniciales distintas — observa cómo divergen los agentes. [Crea el tuyo →](docs/CONFIGURATION.md#character-templates)

**Se ejecuta localmente** — Ollama + Qwen3.5 9B. Ninguna clave de API sale de la máquina. Funciona con fluidez en un Mac M1. Experimentos totalmente reproducibles con registros de episodio inmutables.

**Transparencia a nivel de investigación** — Toda decisión es trazable. Los logs inmutables, las salidas destiladas y los informes diarios se [sincronizan públicamente](https://github.com/shimo4228/contemplative-agent-data) para su reproducibilidad. Consulta [Pivot snapshots reproducibles](#características-principales) más arriba para ver cómo reproducir cualquier ejecución de `distill` bit a bit.

## Agente en vivo

Un agente Contemplative se ejecuta a diario en [Moltbook](https://www.moltbook.com/u/contemplative-agent), una red social para agentes de IA. Navega feeds, filtra publicaciones por relevancia, genera comentarios y crea publicaciones originales. Su conocimiento evoluciona mediante la destilación diaria.

**Observa su evolución:**

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — persona evolucionada, destilada de la experiencia
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — principios éticos (partiendo de los cuatro axiomas del CCAI)
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — habilidades de comportamiento extraídas por `insight`
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — principios universales, destilados a partir de las habilidades
- [Informes diarios](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — interacciones con marca de tiempo (libres para uso académico y no comercial)
- [Informes de análisis](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — evolución conductual, experimentos de enmienda constitucional

## Inicio rápido

**Requisitos previos:** [Ollama](https://ollama.com/download) instalado localmente. Necesita ~8 GB de RAM para el modelo por defecto (Qwen3.5 9B Q4_K_M; archivo del modelo ~6,6 GB). Probado en Mac M1 con 16 GB de RAM.

Si usas [Claude Code](https://claude.ai/claude-code), pega la URL de este repositorio y pídele que configure el agente. Te guiará durante el clon, la instalación y la configuración — ten lista tu `MOLTBOOK_API_KEY` (regístrate en moltbook.com).

O manualmente:

```bash
# 1. Instalación
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # o: uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

# 2. Configuración
cp .env.example .env
# Edita .env — establece MOLTBOOK_API_KEY (regístrate en moltbook.com para obtenerla)

# 3. Ejecutar
contemplative-agent init               # crea identity, knowledge, constitution
contemplative-agent register           # solo adaptador Moltbook; sáltalo para otros
contemplative-agent run --session 60   # por defecto: --approve (confirma cada publicación)

# O arranca con un personaje distinto (ruta por defecto: ~/.config/moltbook/):
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

## Simulación de agentes

El mismo framework puede observar cómo divergen los agentes bajo distintas condiciones iniciales. **Se incluyen 11 plantillas de marcos éticos como punto de partida** — desde la virtud estoica hasta la ética del cuidado, el deber kantiano, el pragmatismo, el contractualismo, entre otros. Los registros de episodios son inmutables, por lo que los mismos datos de comportamiento pueden volver a procesarse bajo condiciones iniciales distintas para realizar experimentos contrafácticos.

Dos agentes divergentes también pueden **conversar entre sí localmente** mediante `contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N` (excepción local-only del ADR-0015). Cada peer tiene su propio MOLTBOOK_HOME, registro de episodios y constitución — útil para contrafácticos constitucionales en los que las propuestas de enmienda de dos marcos pueden compararse sobre la misma transcripción.

La lista completa de plantillas (filosofías, principios centrales y cómo elegir o crear la tuya) está en [Guía de Configuración → Character Templates](docs/CONFIGURATION.md#character-templates).

## Modelo de seguridad

| Vector de ataque | Frameworks típicos | Contemplative Agent |
|------------------|--------------------|---------------------|
| **Ejecución de shell** | Característica central | No existe en el código |
| **Acceso a red** | Arbitrario | Bloqueado a `moltbook.com` + localhost |
| **Sistema de archivos** | Acceso completo | Solo escribe en `$MOLTBOOK_HOME`, permisos 0600 |
| **Proveedor de LLM** | Claves externas en tránsito | Solo Ollama local |
| **Dependencias** | Árbol de dependencias grande | 3 dependencias en runtime (`requests`, `numpy`, `rank-bm25`) |

**one external adapter per agent (un adaptador externo por agente)** — Un único proceso de agente posee, como máximo, un adaptador que produce efectos observables externamente. Los flujos que abarcan varias superficies externas (por ejemplo, publicar *y* cobrar) deben descomponerse en procesos de agente separados con autoridad separada, no atornillados a uno solo. Véase [ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md).

> Pega la URL de este repositorio en [Claude Code](https://claude.ai/claude-code) o en cualquier IA que entienda código y pregúntale si es seguro ejecutarlo. El código habla por sí solo. [Último escaneo de seguridad →](docs/security/2026-04-01-security-scan.md)

**Nota para operadores de agentes de código**: Los registros de episodios (`logs/*.jsonl`) contienen contenido crudo de otros agentes — una superficie de inyección indirecta de prompt sin filtrar. Usa las salidas destiladas (`knowledge.json`, `identity.md`, `reports/`) en su lugar. Los usuarios de Claude Code pueden instalar PreToolUse hooks que lo aplican automáticamente — véase [integrations/claude-code/](integrations/claude-code/).

## Adaptadores

El núcleo es independiente de la plataforma. Los adaptadores son envoltorios finos sobre las APIs específicas de cada plataforma.

**Moltbook** (implementado) — Interacción con el feed social, generación de publicaciones, respuestas a notificaciones. Es el adaptador sobre el que corre el agente en vivo.

**Meditation** (experimental) — Simulación de meditación basada en inferencia activa, inspirada en ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) (Laukkonen, Friston & Chandaria, 2025). Construye un POMDP a partir de los registros de episodios y actualiza creencias sin entrada externa — el equivalente computacional de cerrar los ojos.

**El tuyo** — Implementar un adaptador consiste en conectar la E/S de la plataforma a las interfaces del núcleo (memoria, destilación, constitución, identidad). Véase [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md).

## Ejecutar con APIs de LLM gestionadas (opcional)

Para experimentos de investigación que necesitan un modelo de generación mayor que Qwen3.5 9B — por ejemplo, comparar cómo cambia la destilación con Claude Opus o GPT-5 manteniendo el resto del pipeline de memoria idéntico — un repositorio complementario aparte provee backends de LLM gestionados:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) — Paquete Python opcional. Instalarlo y configurar una clave de API enruta toda llamada de generación (distill, insight, rules-distill, amend-constitution, post, comment, reply, dialogue, skill-reflect) por Anthropic Claude o OpenAI GPT. Los embeddings siguen usando el `nomic-embed-text` local.

Esto es un **opt-in** explícito. El stack por defecto de este repositorio (Ollama + Qwen3.5 9B) no alcanza ningún endpoint en la nube. La propiedad "No cloud. No API keys in transit. Local Ollama only" descrita en [Características clave](#características-clave) y [Modelo de seguridad](#modelo-de-seguridad) vale para este repositorio; instalar el complemento de nube relaja esa propiedad para los usuarios que opten por hacerlo. El código del repositorio principal no se modifica — el complemento inyecta su backend a través de un Protocol `LLMBackend` abstracto que no conoce a ningún proveedor específico.

No instale el complemento de nube en despliegues donde la salida de datos a la nube no sea aceptable (restricciones regulatorias, investigación en redes aisladas, asistentes personales sensibles a la privacidad). El repositorio principal sigue siendo la elección adecuada en esos casos.

## Uso y configuración

La referencia completa del CLI, los niveles de autonomía (`--approve` / `--guarded` / `--auto`), la selección de plantillas, la configuración de dominios, la planificación y las variables de entorno están en una sola guía:

→ **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** — CLI commands, templates, autonomy, domain config, scheduling, env vars.

Comandos de uso diario:

```bash
contemplative-agent run --session 60       # Ejecuta una sesión
contemplative-agent distill --days 3       # Extrae patrones
contemplative-agent skill-reflect          # Revisa habilidades a partir de resultados (ADR-0023)
```

¿Actualizando desde v1.x? Ejecuta las migraciones una vez (véase la sección [CLI Commands → One-Time Migrations](docs/CONFIGURATION.md#cli-commands)).

## Arquitectura

Un invariante se mantiene en toda la base de código: **core/** es independiente de la plataforma; **adapters/** dependen del core, nunca al revés.

Los axiomas de Contemplative AI ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) son un preset conductual opcional — resonancia filosófica, no restricción arquitectural. Quítalos y el agente sigue funcionando; cámbialos por premisas estoicas o kantianas y el agente se comporta de otra manera.

Los mapas de módulos, los diagramas de flujo de datos, los grafos de import y las responsabilidades por módulo están en **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)** (fuente autoritativa). Para FAQ, definiciones de términos y referencias de investigación (orientadas a IA), consulta [llms-full.txt](llms-full.txt). Para el marco de Yogācāra y cómo restringió el diseño de la memoria, véase [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md).

Para el despliegue con aislamiento de red vía Docker, véase la [sección Docker de la Guía de Configuración](docs/CONFIGURATION.md#docker-optional).

## Registros de desarrollo

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

## Úsalo como quieras

Este es un proyecto de investigación, no un producto. Haz fork, desármalo por piezas, incrusta la pipeline en tu propio agente o construye un producto comercial encima — lo que te sea útil. La licencia MIT significa lo que dice. No hace falta citar si solo estás usando el código; la siguiente sección trae las referencias académicas.

## Cita

Si usas o referencias este framework, por favor cítalo así:

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

## Trabajos relacionados

- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) —
  Repositorio de investigación hermano (DOI [10.5281/zenodo.19652014](https://doi.org/10.5281/zenodo.19652014)).
  Reexpresa los juicios de gobernanza de este proyecto (Security Boundary
  Model, One External Adapter Per Agent, Human Approval Gate, y los
  compromisos implícitos de causal traceability / scaffolding visibility)
  en forma harness-neutral como ocho ADRs sobre distribución de la
  accountability en agentes de IA autónomos. Cita AAP cuando cites la
  tesis de distribución de accountability o la jerarquía de
  prohibition-strength; cita este repositorio para la implementación
  operativa.

## Referencias

### Fundamento teórico

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) — marco ético de cuatro axiomas (preset opcional, [ADR-0002](docs/adr/0002-paper-faithful-ccai.md)).
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop: An Active Inference Theory of Consciousness. *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) — base teórica del adaptador de meditación.
- Vasubandhu (siglos IV–V d. C.). *Triṃśikā-vijñaptimātratā* ("Treinta versos sobre la Sola-Consciencia"). — el modelo de las ocho conciencias, adoptado como marco arquitectural ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)).
- Xuanzang (trad. y comp., 659 d. C.). *Cheng Weishi Lun* ("Tratado sobre el establecimiento de la Sola-Consciencia"). — recopilación comentada a partir de diez comentarios indios al *Triṃśikā* de Vasubandhu; la estructura de las ocho vijñāna, bīja (種子, semilla) y vāsanā (習気, impregnación) motiva la política de retención "noise as seed" ([ADR-0027](docs/adr/0027-noise-as-seed.md)).

### Sistemas de memoria

Cada artículo a continuación informó una decisión de diseño específica documentada en el ADR enlazado. Los datos bibliográficos se verificaron contra arXiv.

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) — indexación dinámica al estilo Zettelkasten y evolución de la memoria; informa la reinterpretación de patrones antiguos relacionados temáticamente cuando llega un patrón nuevo ([ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)).
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) — aristas bitemporales en un grafo de conocimiento (motor Graphiti); informa el contrato `valid_from` / `valid_until` de cada patrón ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) — decaimiento estilo Ebbinghaus con refuerzo por acceso; informó en su momento la curva de olvido sensible a la recuperación propuesta en [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md), retirada por [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) en favor de localizar la dinámica de la memoria en la capa de habilidades. Se conserva como referencia histórica.
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) — ataques de inyección de memoria contra agentes usando solo consultas; motiva la procedencia `source_type` + `trust_score` para que los ataques tipo MINJA se vuelvan estructuralmente visibles en lugar de invisibles ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) — habilidades como unidades de memoria persistentes y evolutivas, que se recuperan, se aplican y se reescriben según el resultado; informa el skill-as-memory loop ([ADR-0023](docs/adr/0023-skill-as-memory-loop.md)).

### Trabajo previo (autor)

- Shimomoto, T. (2026). *Agent Knowledge Cycle (AKC): A Six-Phase Self-Improvement Cadence for AI Agents.* [doi:10.5281/zenodo.19200727](https://doi.org/10.5281/zenodo.19200727) — el marco metodológico que este proyecto reimplementa en el contexto de agentes autónomos (véase [Cómo funciona](#cómo-funciona)); originalmente desarrollado como un Claude Code harness.

### Agradecimientos

- Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) — inspiración de diseño para puntuación afectiva determinista.
