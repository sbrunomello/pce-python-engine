# PCE-OS v0 (robótica)

## Arquitetura real do v0

O PCE-OS v0 implementa um **control-plane de robótica com aprovação humana obrigatória**:

- **Digital Twin** (`pce_os.robotics_twin`) com budget, risco, componentes e trilha de auditoria.
- **Approval Gate** (`pce_os.pending_approvals`) para fluxo approve-to-execute.
- **Plugins de domínio** (Value, Decision, Adaptation) para deliberação e adaptação.
- **Endpoints de controle** no FastAPI:
  - `GET /os/robotics/state`
  - `GET /os/approvals`
  - `POST /os/approvals/{id}/approve`
  - `POST /os/approvals/{id}/reject`

> No v0 **não existem conectores externos** (Slack/Jira/GitHub/executor real). A aprovação humana no endpoint materializa o fato da compra no simulador (`purchase.completed`).

## Semântica approve-to-execute (v0)

1. `purchase.requested` cria pendência em `pending_approvals`.
2. `approve` resolve pendência e gera evento `purchase.completed`.
3. Twin aplica `purchase.completed` e baixa `budget_remaining` sem permitir saldo negativo.
4. Se o orçamento for insuficiente no `approve`, o sistema rejeita a aprovação com `409 insufficient_budget_for_purchase`.
5. `reject` gera `purchase.rejected` (sem baixa de budget).

## Configuração única do PCE-OS

O PCE-OS agora usa **um único arquivo de configuração** em `pce-os/config/os_config.json`.

- Todos os valores de configuração do domínio OS ficam nesse arquivo.
- O campo `openrouter.api_key` é entregue vazio por padrão e deve ser preenchido manualmente no ambiente de execução seguro.
- O restante dos valores já vem com defaults produtivos para execução local.

Exemplo:

```json
{
  "openrouter": {
    "api_key": "",
    "model": "openai/gpt-4o-mini",
    "base_url": "https://openrouter.ai/api/v1/chat/completions"
  }
}
```

## Demo local

### 1) Enviar cenário OS

Use os eventos de `pce.examples.scenarios.os_demo_events()` para `POST /events` (um a um).

### 2) Ver pendências

`GET /os/approvals`

### 3) Aprovar uma pendência

`POST /os/approvals/{id}/approve`

### 4) Observar twin

`GET /os/robotics/state`

---

## Exemplos de curl no Windows

### PowerShell

```powershell
# Envia pedido de compra
curl.exe -X POST "http://127.0.0.1:8080/events" `
  -H "Content-Type: application/json" `
  -d '{"event_type":"purchase.requested","source":"os-demo","payload":{"domain":"os.robotics","tags":["purchase"],"projected_cost":250.0,"risk_level":"MEDIUM"}}'

# Lista pendências
curl.exe "http://127.0.0.1:8080/os/approvals"

# Aprova (substitua <APPROVAL_ID>)
curl.exe -X POST "http://127.0.0.1:8080/os/approvals/<APPROVAL_ID>/approve" `
  -H "Content-Type: application/json" `
  -d '{"actor":"operador","notes":"aprovado"}'

# Consulta twin atualizado
curl.exe "http://127.0.0.1:8080/os/robotics/state"
```

### CMD

```cmd
curl -X POST "http://127.0.0.1:8080/events" -H "Content-Type: application/json" -d "{\"event_type\":\"purchase.requested\",\"source\":\"os-demo\",\"payload\":{\"domain\":\"os.robotics\",\"tags\":[\"purchase\"],\"projected_cost\":250.0,\"risk_level\":\"MEDIUM\"}}"
curl "http://127.0.0.1:8080/os/approvals"
curl -X POST "http://127.0.0.1:8080/os/approvals/<APPROVAL_ID>/approve" -H "Content-Type: application/json" -d "{\"actor\":\"operador\",\"notes\":\"aprovado\"}"
curl "http://127.0.0.1:8080/os/robotics/state"
```

## Contratos

- **Fonte de verdade de eventos**: `pce-core/docs/contracts/events.schema.json`.
- Contratos auxiliares do domínio OS:
  - `pce-os/docs/contracts/events.os.schema.json`
  - `pce-os/docs/contracts/action.os.schema.json`
