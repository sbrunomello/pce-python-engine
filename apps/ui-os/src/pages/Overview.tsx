import { useQuery } from '@tanstack/react-query';
import { fetchControlState, sendDemoEvent } from '../api/os';
import { KPICard } from '../components/KPICard';
import { useToast } from '../components/Toast';

export function OverviewPage(): JSX.Element {
  const { showToast } = useToast();
  const stateQuery = useQuery({
    queryKey: ['control-state'],
    queryFn: ({ signal }) => fetchControlState(signal),
    refetchInterval: 5000,
  });

  const metrics = stateQuery.data?.os_metrics ?? {};

  async function onSendDemoEvent(): Promise<void> {
    try {
      await sendDemoEvent();
      showToast('Demo event enviado.', 'success');
    } catch (error) {
      console.error(error);
      showToast('Falha ao enviar demo event.', 'error');
    }
  }

  return (
    <section>
      <header className="header-row">
        <div>
          <h2>Control Room Overview</h2>
          <p>KPIs principais do PCE-OS.</p>
        </div>
        {import.meta.env.DEV ? <button onClick={onSendDemoEvent}>Send Demo Event</button> : null}
      </header>

      {stateQuery.isLoading ? <p>Carregando...</p> : null}

      <div className="card-grid">
        <KPICard title="Budget Remaining" value={String(metrics.budget_remaining ?? '-')} />
        <KPICard title="Risk Level" value={String(metrics.risk_level ?? '-')} />
        <KPICard title="Approval Rate" value={String(metrics.approval_rate ?? '-')} />
        <KPICard title="CCI" value={String(metrics.cci ?? '-')} />
      </div>
    </section>
  );
}
