import type { TelemetrySnapshot } from '../types';

interface TelemetryPanelProps {
  telemetry?: TelemetrySnapshot;
  cci?: number;
  cciHistory: Array<Record<string, unknown>>;
  stateSlice?: Record<string, unknown>;
}

function Field({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-sm text-slate-100">{value}</div>
    </div>
  );
}

export function TelemetryPanel({ telemetry, cci, cciHistory, stateSlice }: TelemetryPanelProps): JSX.Element {
  return (
    <aside className="flex h-full flex-col gap-3 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">Telemetry</h3>
      <div className="grid grid-cols-2 gap-2">
        <Field label="value_score" value={telemetry?.valueScore?.toFixed(3) ?? '-'} />
        <Field label="cci" value={(telemetry?.cci ?? cci)?.toFixed?.(3) ?? '-'} />
        <Field label="override_reason" value={telemetry?.overrideReason ?? '-'} />
        <Field label="final_profile" value={telemetry?.finalProfile ?? '-'} />
        <Field label="epsilon" value={telemetry?.epsilon?.toFixed(3) ?? '-'} />
        <Field label="model" value={telemetry?.model ?? '-'} />
        <Field label="latency_ms" value={telemetry?.latencyMs?.toFixed(0) ?? '-'} />
      </div>

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">CCI components</h4>
        <pre className="max-h-44 overflow-auto rounded border border-slate-800 bg-slate-900 p-2 text-xs text-slate-200">
          {JSON.stringify(telemetry?.cciComponents ?? {}, null, 2)}
        </pre>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">State slice</h4>
        <pre className="max-h-44 overflow-auto rounded border border-slate-800 bg-slate-900 p-2 text-xs text-slate-200">
          {JSON.stringify(stateSlice ?? {}, null, 2)}
        </pre>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">CCI history</h4>
        <pre className="max-h-44 overflow-auto rounded border border-slate-800 bg-slate-900 p-2 text-xs text-slate-200">
          {JSON.stringify(cciHistory.slice(-20), null, 2)}
        </pre>
      </div>
    </aside>
  );
}
