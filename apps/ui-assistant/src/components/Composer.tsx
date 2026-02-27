import { useState, type FormEvent } from 'react';

interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => Promise<void>;
}

export function Composer({ disabled, onSend }: ComposerProps): JSX.Element {
  const [text, setText] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }
    setText('');
    await onSend(trimmed);
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={handleSubmit}>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Digite uma observação para o assistant..."
        className="min-h-24 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400"
      />
      <button
        type="submit"
        disabled={disabled}
        className="self-end rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {disabled ? 'Enviando...' : 'Enviar'}
      </button>
    </form>
  );
}
