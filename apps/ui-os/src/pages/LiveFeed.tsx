import { useEffect, useMemo, useState } from 'react';
import { fetchTranscriptSince, type TranscriptItem } from '../api/os';
import { FeedItem } from '../components/FeedItem';

const MAX_ITEMS = 250;

export function LiveFeedPage(): JSX.Element {
  const [items, setItems] = useState<TranscriptItem[]>([]);
  const [cursor, setCursor] = useState(0);
  const [kind, setKind] = useState('all');
  const [agent, setAgent] = useState('all');
  const [correlation, setCorrelation] = useState('');

  useEffect(() => {
    let closed = false;
    let retries = 0;
    let eventSource: EventSource | null = null;
    let pollTimer: number | null = null;

    const append = (incoming: TranscriptItem): void => {
      setItems((prev) => [...prev, incoming].slice(-MAX_ITEMS));
      setCursor((prev) => Math.max(prev, incoming.cursor));
    };

    const catchup = async (): Promise<void> => {
      const data = await fetchTranscriptSince(cursor);
      data.items.forEach(append);
      setCursor(data.cursor);
    };

    const connect = (): void => {
      eventSource = new EventSource('/api/v1/stream/os');
      eventSource.onmessage = () => undefined;
      const onAny = (event: MessageEvent) => {
        const parsed = JSON.parse(event.data) as TranscriptItem;
        append(parsed);
      };
      ['os.event_ingested','os.agent_message','os.actions_proposed','os.approval_created','os.approval_updated','os.state_updated'].forEach((name) => {
        eventSource?.addEventListener(name, onAny);
      });
      eventSource.onerror = () => {
        eventSource?.close();
        if (closed) return;
        retries += 1;
        const backoff = Math.min(5000, 500 * retries);
        window.setTimeout(() => {
          catchup().catch(() => undefined);
          connect();
        }, backoff);
      };
    };

    connect();
    pollTimer = window.setInterval(() => {
      catchup().catch(() => undefined);
    }, 5000);

    return () => {
      closed = true;
      eventSource?.close();
      if (pollTimer) window.clearInterval(pollTimer);
    };
  }, [cursor]);

  const filtered = useMemo(() => items.filter((item) => {
    if (kind !== 'all' && item.kind !== kind) return false;
    if (agent !== 'all' && item.agent !== agent) return false;
    if (correlation && !item.correlation_id.includes(correlation)) return false;
    return true;
  }), [agent, correlation, items, kind]);

  return (
    <section>
      <h2>Live Feed</h2>
      <div className="filters">
        <select aria-label="Filtrar tipo" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="all">All</option>
          <option value="event_ingested">Events</option>
          <option value="agent_message">Agent Messages</option>
          <option value="actions_proposed">Proposed Actions</option>
          <option value="approval_created">Approvals</option>
          <option value="state_updated">State Updates</option>
        </select>
        <select aria-label="Filtrar agente" value={agent} onChange={(e) => setAgent(e.target.value)}>
          <option value="all">All Agents</option>
          <option value="engineering">engineering</option>
          <option value="procurement">procurement</option>
          <option value="finance">finance</option>
          <option value="tests">tests</option>
        </select>
        <input aria-label="Buscar correlation id" placeholder="correlation_id" value={correlation} onChange={(e) => setCorrelation(e.target.value)} />
      </div>
      <ul className="feed-list">{filtered.map((item) => <FeedItem key={item.cursor} item={item} />)}</ul>
    </section>
  );
}
