import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchCci, fetchPendingApprovals, fetchRoboticsState, fetchState } from '../api/os';
import { useToast } from '../components/Toast';

function findEventHistory(state: Record<string, unknown>): unknown[] {
  const candidates = [
    state.history,
    state.event_history,
    state.events,
    (state.pce_os as Record<string, unknown> | undefined)?.history,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }

  return [];
}

export function OverviewPage(): JSX.Element {
  const { showToast } = useToast();

  const twinQuery = useQuery({
    queryKey: ['robotics-state'],
    queryFn: ({ signal }) => fetchRoboticsState(signal),
  });

  const approvalsQuery = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: ({ signal }) => fetchPendingApprovals(signal),
  });

  const stateQuery = useQuery({
    queryKey: ['core-state'],
    queryFn: ({ signal }) => fetchState(signal),
  });

  const cciQuery = useQuery({
    queryKey: ['cci'],
    queryFn: ({ signal }) => fetchCci(signal),
  });

  useEffect(() => {
    if (!(twinQuery.error || approvalsQuery.error || stateQuery.error || cciQuery.error)) {
      return;
    }

    console.error('Failed to load overview data', {
      twinError: twinQuery.error,
      approvalsError: approvalsQuery.error,
      stateError: stateQuery.error,
      cciError: cciQuery.error,
    });
    showToast('Falha ao carregar overview.', 'error');
  }, [approvalsQuery.error, cciQuery.error, showToast, stateQuery.error, twinQuery.error]);

  const events = stateQuery.data ? findEventHistory(stateQuery.data).slice(-10).reverse() : [];

  return (
    <section>
      <header>
        <h2>Overview</h2>
        <p>Resumo operacional do domínio OS robótica.</p>
      </header>

      {twinQuery.isLoading ? (
        <p>Carregando Digital Twin...</p>
      ) : (
        <div className="card-grid">
          <article className="card">
            <h3>Budget Remaining</h3>
            <strong>{twinQuery.data?.budget_remaining.toFixed(2) ?? '0.00'}</strong>
          </article>
          <article className="card">
            <h3>Budget Total</h3>
            <strong>{twinQuery.data?.budget_total.toFixed(2) ?? '0.00'}</strong>
          </article>
          <article className="card">
            <h3>Risk Level</h3>
            <strong>{twinQuery.data?.risk_level ?? '-'}</strong>
          </article>
          <article className="card">
            <h3>Phase</h3>
            <strong>{twinQuery.data?.phase ?? '-'}</strong>
          </article>
          <article className="card">
            <h3>CCI</h3>
            <strong>{typeof cciQuery.data === 'number' ? cciQuery.data.toFixed(3) : '-'}</strong>
          </article>
        </div>
      )}

      <div className="panel-row">
        <section className="panel">
          <h3>Pendências de aprovação</h3>
          {approvalsQuery.isLoading ? (
            <p>Carregando...</p>
          ) : approvalsQuery.data && approvalsQuery.data.length > 0 ? (
            <ul>
              {approvalsQuery.data.map((approval) => (
                <li key={approval.approval_id}>
                  <strong>{approval.approval_id}</strong>
                  <span>
                    {approval.action_type ?? 'sem ação'} · risco {approval.risk ?? 'N/A'} · custo{' '}
                    {approval.projected_cost ?? 0}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>Nenhuma approval pendente.</p>
          )}
        </section>

        <section className="panel">
          <h3>Mini feed (últimos 10 eventos)</h3>
          {events.length === 0 ? (
            <p>Sem histórico de eventos disponível em /state.</p>
          ) : (
            <ul>
              {events.map((event, idx) => (
                <li key={idx} className="event-row">
                  <code>{JSON.stringify(event)}</code>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </section>
  );
}
