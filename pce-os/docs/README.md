# PCE-OS v0 (robótica)

## Demo rápido

1. Inicie a API FastAPI (`agents/llm-assistant/api/main.py`).
2. Envie os eventos do cenário `pce.examples.scenarios.os_demo_events()` para `POST /events`.
3. Verifique pendências com `GET /os/approvals`.
4. Aprove com `POST /os/approvals/{id}/approve` enviando `{"actor": "seu_nome", "notes": "ok"}`.
5. Consulte o twin em `GET /os/robotics/state`.

## Observações

- v0 é **approve-to-execute**: ações de compra ficam pendentes até aprovação humana.
- Estado persistido em `state["pce_os"]["robotics_twin"]`.
- TODO v1: conectores externos (Slack/Jira/GitHub), simulação avançada, novos domínios.
