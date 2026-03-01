# Documentação Principal do Projeto — PCE Python Engine

Este documento é a referência central do monorepo **pce-python-engine**. Ele consolida arquitetura, componentes, fluxos funcionais, setup, execução, contratos e operação para facilitar onboarding técnico, manutenção e evolução do sistema.

## 1) Visão geral do monorepo

O projeto implementa uma **Persistent Cognition Engine (PCE)** com extensões de domínio (OS robótica, agente assistente LLM e agente rover), organizada em pacotes desacoplados.

### Pacotes e responsabilidades

- **`pce-core`**: núcleo cognitivo (pipeline EPL → ISI → VEL → SM → DE → AO → AFS), contratos, CCI e API principal FastAPI.
- **`pce-os`**: control-plane de robótica com **Approval Gate**, estado do Digital Twin e plugins de deliberação/adaptação.
- **`agents/llm-assistant`**: plugins do domínio assistant (valor, decisão, adaptação), cliente OpenRouter e UI de assistente.
- **`agents/rover`**: integração com domínio rover (mundo/sensores, bridge, plugins e API/telemetria do agente).
- **`apps/ui-os`**: interface React para operação do PCE-OS (overview, aprovações, twin, agentes, live feed).
- **`worker/loop.py`**: loop contínuo para simulação de deliberação persistente.

## 2) Arquitetura técnica consolidada

A aplicação em runtime é montada no `build_app()` do `pce_api.main`.

### Componentes inicializados no boot

1. `StateManager` (persistência SQLite)
2. `EventProcessingLayer` (validação de evento por schema)
3. `InternalStateIntegrator` (integração de contexto)
4. `ValueEvaluationLayer` (score de aderência a valores)
5. `DecisionEngine` (deliberação base)
6. `ActionOrchestrator` (execução)
7. `AdaptiveFeedbackSystem` (adaptação)
8. `CCIMetric` (métrica de coerência)
9. `PluginRegistry` (roteamento por domínio)
10. Plugins de robótica, assistant e PCE-OS

## 3) Fluxo fim a fim de processamento de evento

O endpoint `POST /events` chama internamente `_run_pipeline()`, que executa este fluxo:

1. **Ingestão/validação**: converte `EventIn` em `PCEEvent` e valida schema.
2. **Recuperação de estado**: carrega snapshot persistido do `StateManager`.
3. **Transcrição operacional**: grava item de `event_ingested` para auditoria/SSE.
4. **Integração de estado (ISI)**: aplica evento ao estado interno.
5. **Memória de evento**: persiste evento em trilha histórica.
6. **Avaliação de valores (VEL/plugins)**: calcula `value_score`.
7. **Leitura de coerência (CCI)**: calcula score e componentes no estado atual.
8. **Deliberação (DE/plugins)**: produz plano de ação com metadados explicáveis.
9. **Approval gate (PCE-OS)**: para ações críticas, cria pendência ao invés de executar.
10. **Execução de ação**: executa imediatamente se não depender de aprovação.
11. **Adaptação (AFS/plugins)**: atualiza estado em função do resultado observado.
12. **Atualização do Twin OS**: aplica evento ao twin quando domínio `os.robotics`.
13. **Persistência final**: salva novo estado e registra memória de ação.
14. **Snapshot CCI pós-ação**: recalcula e persiste histórico de coerência.
15. **Resposta API**: retorna `value_score`, `cci`, componentes, ação e metadados.

## 4) Fluxos específicos por domínio

### 4.1) Domínio PCE-OS (approve-to-execute)

Fluxo operacional de compras:

1. `purchase.requested` entra no pipeline.
2. Plugin de decisão OS pode propor ação que exige aprovação.
3. `ApprovalGate` cria registro em `pending_approvals`.
4. Operador consulta pendências em `GET /os/approvals`.
5. Operador aprova via `POST /os/approvals/{id}/approve`.
6. Sistema materializa evento de aprovação e executa ciclo completo.
7. Twin robótico é atualizado (`budget_remaining`, risco, histórico de compras).

Também existe rejeição (`/reject`) e override (`/v1/os/approvals/{id}/override`).

### 4.2) Domínio Assistant (LLM)

Fluxo principal:

1. UI ou cliente envia `observation.assistant.v1`.
2. Plugin `AssistantDecisionPlugin` seleciona perfil de resposta.
3. Se configurado, chama OpenRouter; em falha, aplica fallback controlado.
4. Evento `feedback.assistant.v1` ajusta memória causal e sinais de adaptação.
5. Estado de memória pode ser limpo por `POST /agents/assistant/control/clear_memory`.

### 4.3) Domínio Rover

- Plugins de valor/decisão/adaptação do rover são registrados no mesmo `PluginRegistry`.
- API inclui rota para limpeza de política (`/agents/rover/control/clear_policy`) e reset de estatísticas (`/agents/rover/control/reset_stats`).
- Integração entre ponte (bridge), sensores/mundo e runtime permite teste de comportamento em ambiente simulado.

## 5) Endpoints principais da API

### Pipeline e estado

- `POST /events` e `POST /v1/events`: entrada de eventos.
- `GET /cci`: CCI atual.
- `GET /cci/history`: histórico de snapshots CCI.
- `GET /state`: estado cognitivo persistido.

### PCE-OS

- `GET /os/robotics/state`: snapshot atual do twin robótico.
- `GET /os/approvals` e `GET /v1/os/approvals`: pendências e histórico de aprovações.
- `POST /os/approvals/{approval_id}/approve`: aprova pendência.
- `POST /os/approvals/{approval_id}/reject`: rejeita pendência.
- `POST /v1/os/approvals/{approval_id}/override`: override administrativo.
- `GET /v1/os/state`: visão agregada de estado/métricas/política.
- `GET /v1/os/agents/transcript`: transcript operacional dos agentes.
- `GET /v1/stream/os`: stream SSE (eventos operacionais em tempo real).

### Controles operacionais

- `POST /agents/rover/control/clear_policy`
- `POST /agents/rover/control/reset_stats`
- `POST /agents/assistant/control/clear_memory`

## 6) Contratos e compliance

O projeto adota validação por contrato para reduzir ambiguidade e garantir rastreabilidade:

- `pce-core/docs/contracts/events.schema.json`: contrato base de eventos.
- `pce-core/docs/contracts/action.schema.json`: contrato base de ações.
- `pce-os/docs/contracts/events.os.schema.json` e `action.os.schema.json`: extensões do domínio OS.

Além disso, políticas do repositório definem padrões de segurança, qualidade e restrições operacionais:

- `policies/SECURITY.md`
- `policies/CODING_STANDARDS.md`
- `policies/DEFINITIONS_OF_DONE.md`
- `policies/NO_BINARIES.md`

## 7) Setup e execução local (recomendado)

### Pré-requisitos

- Python 3.11+
- Node.js 18+ (para UIs)

### Instalação de pacotes Python (modo editável)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e pce-core -e pce-os -e agents/llm-assistant -e agents/rover
```

### Rodar API

```bash
uvicorn pce_api.main:app --reload --port 8080
```

### Rodar suíte de testes

```bash
pytest -q
```

### Rodar UI OS

```bash
cd apps/ui-os
npm i
npm run dev
```

## 8) Fluxo operacional recomendado em produção inicial

1. Validar contratos antes de habilitar novos produtores de eventos.
2. Monitorar CCI e taxa de contradição como SLOs cognitivos.
3. Habilitar approve-to-execute para decisões com impacto financeiro.
4. Registrar feedback explícito (especialmente no domínio assistant) para evolução adaptativa controlada.
5. Utilizar transcript/SSE e trilha de ação para auditoria pós-incidente.

## 9) Mapa de documentação complementar

- Visão arquitetural: `docs/architecture/overview.md`
- Glossário: `docs/architecture/glossary.md`
- Tutorial E2E: `docs/tutorials/tutorial.md`
- Segurança e compliance: `docs/security-compliance.md`
- ADRs: `docs/adrs/`
- README PCE-OS: `pce-os/docs/README.md`
- README UI OS: `apps/ui-os/README.md`

## 10) Checklist de manutenção contínua

- [ ] Novos eventos com schema versionado.
- [ ] Novos plugins registrados com testes unitários.
- [ ] Alterações de fluxo refletidas nesta documentação principal.
- [ ] Endpoints documentados com payload de exemplo.
- [ ] Mudanças com impacto de auditoria acompanhadas de ADR.

---

Se você está chegando agora no projeto, comece por esta ordem: **(1) esta documentação principal → (2) overview da arquitetura → (3) tutorial end-to-end → (4) contratos JSON Schema → (5) testes**.
