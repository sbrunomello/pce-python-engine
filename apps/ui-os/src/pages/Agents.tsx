import { useQuery } from '@tanstack/react-query';
import { fetchTranscriptSince } from '../api/os';

const AGENTS = ['engineering', 'procurement', 'finance', 'tests'];

export function AgentsPage(): JSX.Element {
  const transcriptQuery = useQuery({
    queryKey: ['agents-transcript'],
    queryFn: () => fetchTranscriptSince(0),
    refetchInterval: 5000,
  });

  return (
    <section>
      <h2>Agents</h2>
      <div className="card-grid">
        {AGENTS.map((agent) => {
          const messages = (transcriptQuery.data?.items ?? []).filter((item) => item.agent === agent).slice(-5);
          return (
            <article className="card" key={agent}>
              <h3>{agent}</h3>
              <p>Health: {messages.length > 0 ? 'active' : 'idle'}</p>
              <small>last activity: {messages[messages.length - 1]?.ts ?? '-'}</small>
              <ul>
                {messages.map((message) => (
                  <li key={message.cursor}><code>{message.kind}</code> #{message.cursor}</li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </section>
  );
}
