import type { ChatEntry } from '../types';

interface ChatMessageListProps {
  messages: ChatEntry[];
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString();
}

export function ChatMessageList({ messages }: ChatMessageListProps): JSX.Element {
  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      {messages.length === 0 && (
        <div className="rounded-md border border-dashed border-slate-700 p-4 text-sm text-slate-400">
          Nenhuma mensagem ainda. Envie uma observação para testar o assistant.
        </div>
      )}
      {messages.map((message) => (
        <article
          key={message.id}
          className={`max-w-[88%] rounded-xl px-4 py-3 shadow ${
            message.role === 'user'
              ? 'ml-auto bg-indigo-600 text-white'
              : 'mr-auto bg-slate-800 text-slate-100'
          }`}
        >
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>
          <div className="mt-2 text-right text-[11px] opacity-75">{formatTime(message.createdAt)}</div>
        </article>
      ))}
    </div>
  );
}
