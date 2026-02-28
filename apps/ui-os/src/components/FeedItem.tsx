import type { TranscriptItem } from '../api/os';

export function FeedItem({ item }: { item: TranscriptItem }): JSX.Element {
  return (
    <li className="feed-item">
      <div className="feed-head">
        <strong>{item.kind}</strong>
        <span>#{item.cursor}</span>
      </div>
      <small>
        corr=<code>{item.correlation_id}</code> dec=<code>{item.decision_id ?? '-'}</code>
      </small>
      {item.agent ? <small>agent: {item.agent}</small> : null}
      <code>{JSON.stringify(item.payload)}</code>
    </li>
  );
}
