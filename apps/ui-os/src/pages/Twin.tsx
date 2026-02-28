import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchCciHistory, fetchRoboticsState } from '../api/os';
import { JsonViewer } from '../components/JsonViewer';
import { useToast } from '../components/Toast';

export function TwinPage(): JSX.Element {
  const { showToast } = useToast();

  const twinQuery = useQuery({
    queryKey: ['robotics-state'],
    queryFn: ({ signal }) => fetchRoboticsState(signal),
  });

  const cciHistoryQuery = useQuery({
    queryKey: ['cci-history'],
    queryFn: ({ signal }) => fetchCciHistory(signal),
  });

  useEffect(() => {
    if (!(twinQuery.error || cciHistoryQuery.error)) {
      return;
    }

    console.error('Failed to load twin data', {
      twinError: twinQuery.error,
      cciHistoryError: cciHistoryQuery.error,
    });
    showToast('Falha ao carregar Twin.', 'error');
  }, [cciHistoryQuery.error, showToast, twinQuery.error]);

  return (
    <section>
      <header>
        <h2>Digital Twin</h2>
        <p>Estado completo do robotics_twin com visão rápida dos campos mais relevantes.</p>
      </header>

      {twinQuery.isLoading ? (
        <p>Carregando twin...</p>
      ) : (
        <>
          <div className="card-grid">
            <article className="card">
              <h3>Budget Remaining</h3>
              <strong>{twinQuery.data?.budget_remaining.toFixed(2) ?? '0.00'}</strong>
            </article>
            <article className="card">
              <h3>Components</h3>
              <strong>{twinQuery.data?.components.length ?? 0}</strong>
            </article>
            <article className="card">
              <h3>Purchases</h3>
              <strong>{twinQuery.data?.purchase_history.length ?? 0}</strong>
            </article>
            <article className="card">
              <h3>CCI History Points</h3>
              <strong>{cciHistoryQuery.data?.length ?? 0}</strong>
            </article>
          </div>

          <h3>robotics_twin JSON</h3>
          <JsonViewer value={twinQuery.data ?? {}} />
        </>
      )}
    </section>
  );
}
