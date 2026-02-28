import pce_api.main as api_main
from fastapi.testclient import TestClient
from pce.sm.manager import StateManager


def test_v1_state_and_transcript_endpoints(tmp_path) -> None:
    db = tmp_path / 'state.db'
    sm = StateManager(f'sqlite:///{db}')
    sm.save_state({})
    app = api_main.build_app(state_manager=sm)
    client = TestClient(app)

    resp = client.post(
        '/v1/events',
        json={
            'event_type': 'budget.updated',
            'source': 'test',
            'payload': {'domain': 'os.robotics', 'correlation_id': 'corr-1', 'tags': ['budget'], 'budget_total': 400.0, 'budget_remaining': 400.0},
        },
    )
    assert resp.status_code == 200

    state_resp = client.get('/v1/os/state')
    assert state_resp.status_code == 200
    body = state_resp.json()
    assert 'twin_snapshot' in body
    assert 'os_metrics' in body

    transcript_resp = client.get('/v1/os/agents/transcript?since=0')
    assert transcript_resp.status_code == 200
    transcript = transcript_resp.json()
    assert transcript['cursor'] >= 1
    assert any(item['correlation_id'] == 'corr-1' for item in transcript['items'])


def test_override_endpoint(tmp_path) -> None:
    db = tmp_path / 'state.db'
    sm = StateManager(f'sqlite:///{db}')
    sm.save_state({})
    app = api_main.build_app(state_manager=sm)
    client = TestClient(app)

    client.post(
        '/v1/events',
        json={
            'event_type': 'purchase.requested',
            'source': 'test',
            'payload': {
                'domain': 'os.robotics',
                'tags': ['purchase'],
                'projected_cost': 50.0,
                'risk_level': 'MEDIUM',
                'correlation_id': 'corr-override',
            },
        },
    )
    approval_id = client.get('/v1/os/approvals').json()['pending'][0]['approval_id']

    override_resp = client.post(
        f'/v1/os/approvals/{approval_id}/override',
        json={'actor': 'qa', 'notes': 'force continue'},
    )
    assert override_resp.status_code == 200
    items = client.get('/v1/os/approvals').json()['items']
    assert any(item['approval_id'] == approval_id and item['status'] == 'overridden' for item in items)
