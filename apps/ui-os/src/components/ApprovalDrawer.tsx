import type { Approval } from '../api/os';

export function ApprovalDrawer({ approval, onClose }: { approval: Approval | null; onClose: () => void }): JSX.Element | null {
  if (!approval) {
    return null;
  }

  return (
    <aside className="drawer" aria-label="Approval details">
      <div className="drawer-head">
        <h3>Approval Details</h3>
        <button onClick={onClose}>Fechar</button>
      </div>
      <p><strong>ID:</strong> <code>{approval.approval_id}</code></p>
      <p><strong>Decision:</strong> <code>{approval.decision_id ?? '-'}</code></p>
      <p><strong>Status:</strong> {approval.status}</p>
      <p><strong>Projected cost:</strong> {approval.projected_cost ?? '-'}</p>
      <p><strong>Risk:</strong> {approval.risk ?? '-'}</p>
      <pre>{JSON.stringify(approval.metadata ?? {}, null, 2)}</pre>
    </aside>
  );
}
