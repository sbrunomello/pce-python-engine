import { useEffect, useMemo, useState } from 'react';
import { ChatMessageList } from './components/ChatMessageList';
import { Composer } from './components/Composer';
import { FeedbackPanel } from './components/FeedbackPanel';
import { TelemetryPanel } from './components/TelemetryPanel';
import {
  clearAssistantMemory,
  getCci,
  getCciHistory,
  getState,
  isApiError,
  sendFeedback,
  sendObservation,
} from './services/api';
import type { ChatEntry, EventsResponse, TelemetrySnapshot } from './types';

const MAX_MESSAGES = 200;
const STORAGE_KEY = 'assistant_ui_v1';

interface PersistedState {
  sessionId: string;
  messages: ChatEntry[];
  notes: string;
  rating?: number;
  showExplain: boolean;
}

function readPersistedState(): PersistedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { sessionId: 'local-dev', messages: [], notes: '', showExplain: false };
    }
    const parsed = JSON.parse(raw) as PersistedState;
    return {
      sessionId: parsed.sessionId || 'local-dev',
      messages: Array.isArray(parsed.messages) ? parsed.messages.slice(-MAX_MESSAGES) : [],
      notes: parsed.notes || '',
      rating: parsed.rating,
      showExplain: Boolean(parsed.showExplain),
    };
  } catch {
    return { sessionId: 'local-dev', messages: [], notes: '', showExplain: false };
  }
}

function extractTelemetry(event?: EventsResponse): TelemetrySnapshot | undefined {
  if (!event) return undefined;
  const explain = event.metadata?.explain as Record<string, unknown> | undefined;
  const deExplain = explain?.de as Record<string, unknown> | undefined;
  const llmExplain = explain?.llm as Record<string, unknown> | undefined;

  return {
    valueScore: event.value_score,
    cci: event.cci,
    overrideReason: typeof deExplain?.override_reason === 'string' ? deExplain.override_reason : undefined,
    finalProfile: typeof deExplain?.final_profile === 'string' ? deExplain.final_profile : undefined,
    epsilon: typeof deExplain?.epsilon === 'number' ? deExplain.epsilon : event.epsilon,
    model: typeof llmExplain?.model === 'string' ? llmExplain.model : undefined,
    latencyMs: typeof llmExplain?.latency_ms === 'number' ? llmExplain.latency_ms : undefined,
    cciComponents: event.cci_components,
  };
}

function safeAssistantText(response: EventsResponse): string {
  if (typeof response.action === 'string') return response.action;
  const actionPayload = response.action as Record<string, unknown> | undefined;
  return typeof actionPayload?.text === 'string'
    ? actionPayload.text
    : 'Sem texto de resposta no action payload.';
}

export default function App(): JSX.Element {
  const initialState = useMemo(readPersistedState, []);
  const [sessionId, setSessionId] = useState(initialState.sessionId);
  const [messages, setMessages] = useState<ChatEntry[]>(initialState.messages);
  const [showExplain, setShowExplain] = useState(initialState.showExplain);
  const [savedNotes, setSavedNotes] = useState(initialState.notes);
  const [savedRating, setSavedRating] = useState<number | undefined>(initialState.rating);
  const [latestResponse, setLatestResponse] = useState<EventsResponse>();
  const [statusText, setStatusText] = useState('Pronto para enviar eventos.');
  const [isBusy, setIsBusy] = useState(false);
  const [lastError, setLastError] = useState('');
  const [stateSlice, setStateSlice] = useState<Record<string, unknown>>();
  const [cci, setCci] = useState<number>();
  const [cciHistory, setCciHistory] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    const persisted: PersistedState = {
      sessionId,
      messages,
      notes: savedNotes,
      rating: savedRating,
      showExplain,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
  }, [messages, savedNotes, savedRating, sessionId, showExplain]);

  function pushMessage(entry: ChatEntry): void {
    setMessages((prev) => [...prev, entry].slice(-MAX_MESSAGES));
  }

  function handleApiError(error: unknown): void {
    if (isApiError(error)) {
      const detail = error.body ? JSON.stringify(error.body, null, 2) : error.message;
      setLastError(detail);
      setStatusText(`Erro API: ${error.status}`);
      return;
    }
    setLastError((error as Error).message || 'Erro inesperado');
    setStatusText('Erro inesperado.');
  }

  async function handleSendObservation(text: string): Promise<void> {
    setIsBusy(true);
    setLastError('');
    pushMessage({ id: crypto.randomUUID(), role: 'user', text, createdAt: Date.now() });

    try {
      const response = await sendObservation(sessionId, text);
      setLatestResponse(response);
      pushMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        text: safeAssistantText(response),
        createdAt: Date.now(),
        event: response,
      });
      setStatusText('Observação enviada com sucesso.');
    } catch (error) {
      handleApiError(error);
    } finally {
      setIsBusy(false);
    }
  }

  async function handleFeedback(payload: {
    reward: number;
    rating?: number;
    accepted?: boolean;
    notes?: string;
  }): Promise<void> {
    setIsBusy(true);
    setLastError('');
    try {
      const response = await sendFeedback(sessionId, payload);
      setLatestResponse(response);
      setStatusText('Feedback enviado ao AFS.');
    } catch (error) {
      handleApiError(error);
    } finally {
      setIsBusy(false);
    }
  }

  async function withStatus(action: () => Promise<void>, successMessage: string): Promise<void> {
    setIsBusy(true);
    setLastError('');
    try {
      await action();
      setStatusText(successMessage);
    } catch (error) {
      handleApiError(error);
    } finally {
      setIsBusy(false);
    }
  }

  const telemetry = extractTelemetry(latestResponse);

  return (
    <main className="mx-auto grid min-h-screen max-w-[1600px] grid-cols-1 gap-4 p-4 text-slate-100 lg:grid-cols-[2fr_1fr]">
      <section className="flex min-h-[85vh] flex-col gap-4">
        <header className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h1 className="text-lg font-semibold">Assistant UI</h1>
          <p className="text-xs text-slate-400">Teste rápido do domínio assistant com telemetria em tempo real.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <label className="text-xs text-slate-300">
              Session ID
              <input
                value={sessionId}
                onChange={(event) => setSessionId(event.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-slate-300">
              API Base (dev proxy)
              <input
                disabled
                value="/api -> VITE_API_BASE_URL"
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-400"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() =>
                withStatus(async () => {
                  const result = await clearAssistantMemory();
                  setStateSlice(result);
                }, 'Memória do assistant limpa.')
              }
              className="rounded bg-rose-500 px-3 py-2 text-xs font-medium text-white hover:bg-rose-400"
            >
              Clear Assistant Memory
            </button>
            <button
              type="button"
              onClick={() =>
                withStatus(async () => {
                  const response = await getState();
                  const state = response.state;
                  setStateSlice({
                    assistant: (state.assistant as Record<string, unknown>) ?? {},
                    assistant_learning: (state.assistant_learning as Record<string, unknown>) ?? {},
                  });
                }, 'Estado atualizado.')
              }
              className="rounded bg-slate-700 px-3 py-2 text-xs font-medium hover:bg-slate-600"
            >
              Refresh State
            </button>
            <button
              type="button"
              onClick={() =>
                withStatus(async () => {
                  const response = await getCci();
                  setCci(response.cci);
                }, 'CCI atualizado.')
              }
              className="rounded bg-slate-700 px-3 py-2 text-xs font-medium hover:bg-slate-600"
            >
              Get CCI
            </button>
            <button
              type="button"
              onClick={() =>
                withStatus(async () => {
                  const response = await getCciHistory();
                  setCciHistory(response.history);
                }, 'Histórico de CCI atualizado.')
              }
              className="rounded bg-slate-700 px-3 py-2 text-xs font-medium hover:bg-slate-600"
            >
              CCI History
            </button>
            <button
              type="button"
              onClick={() => {
                localStorage.removeItem(STORAGE_KEY);
                setMessages([]);
                setLatestResponse(undefined);
                setSavedNotes('');
                setSavedRating(undefined);
                setStatusText('Histórico da UI limpo.');
              }}
              className="rounded bg-slate-800 px-3 py-2 text-xs font-medium hover:bg-slate-700"
            >
              Clear UI history
            </button>
          </div>
          <p className="mt-2 text-xs text-emerald-300">{statusText}</p>
          {lastError && <pre className="mt-2 overflow-auto rounded bg-rose-950 p-2 text-xs text-rose-200">{lastError}</pre>}
        </header>

        <div className="grid flex-1 grid-rows-[1fr_auto_auto] gap-4">
          <ChatMessageList messages={messages} />
          <Composer disabled={isBusy} onSend={handleSendObservation} />
          <FeedbackPanel
            disabled={isBusy}
            initialNotes={savedNotes}
            initialRating={savedRating}
            onPreferenceChange={(notes, rating) => {
              setSavedNotes(notes);
              setSavedRating(rating);
            }}
            onSend={handleFeedback}
          />
        </div>

        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">metadata.explain</h3>
            <button
              type="button"
              onClick={() => setShowExplain((prev) => !prev)}
              className="rounded border border-slate-700 px-2 py-1 text-xs"
            >
              {showExplain ? 'Ocultar' : 'Mostrar'}
            </button>
          </div>
          {showExplain ? (
            <pre className="max-h-72 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">
              {JSON.stringify(latestResponse?.metadata?.explain ?? {}, null, 2)}
            </pre>
          ) : (
            <p className="text-xs text-slate-400">Ative para inspecionar explain JSON.</p>
          )}
        </section>
      </section>

      <TelemetryPanel telemetry={telemetry} cci={cci} cciHistory={cciHistory} stateSlice={stateSlice} />
    </main>
  );
}
