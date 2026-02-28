import { useMemo, useState } from 'react';

interface FeedbackPanelProps {
  disabled: boolean;
  initialNotes: string;
  initialRating?: number;
  onSend: (payload: { reward: number; rating?: number; accepted?: boolean; notes?: string }) => Promise<void>;
  onPreferenceChange: (notes: string, rating?: number) => void;
}

export function FeedbackPanel({
  disabled,
  initialNotes,
  initialRating,
  onSend,
  onPreferenceChange,
}: FeedbackPanelProps): JSX.Element {
  const [reward, setReward] = useState(1);
  const [notes, setNotes] = useState(initialNotes);
  const [rating, setRating] = useState<number | undefined>(initialRating);

  const accepted = useMemo(() => reward > 0, [reward]);

  async function submitFeedback(): Promise<void> {
    onPreferenceChange(notes, rating);
    await onSend({ reward, rating, accepted, notes });
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">Feedback rápido (AFS)</h3>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => setReward(1)}
          className={`rounded px-3 py-1.5 text-sm ${reward > 0 ? 'bg-emerald-500 text-white' : 'bg-slate-800 text-slate-300'}`}
        >
          👍 +1
        </button>
        <button
          type="button"
          onClick={() => setReward(-1)}
          className={`rounded px-3 py-1.5 text-sm ${reward < 0 ? 'bg-rose-500 text-white' : 'bg-slate-800 text-slate-300'}`}
        >
          👎 -1
        </button>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3">
        <label className="text-xs text-slate-300">
          Rating (1..5)
          <select
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
            value={rating ?? ''}
            onChange={(event) =>
              setRating(event.target.value ? Number.parseInt(event.target.value, 10) : undefined)
            }
          >
            <option value="">-</option>
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-300">
          Notes
          <input
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
            placeholder="Ex: não seja prolixo"
          />
        </label>
      </div>
      <button
        type="button"
        onClick={submitFeedback}
        disabled={disabled}
        className="mt-3 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Send feedback
      </button>
    </section>
  );
}
