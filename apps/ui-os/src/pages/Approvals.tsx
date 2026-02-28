import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  approveApproval,
  fetchAllApprovals,
  overrideApproval,
  rejectApproval,
  type Approval,
} from '../api/os';
import { ApprovalDrawer } from '../components/ApprovalDrawer';

export function ApprovalsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Approval | null>(null);

  const approvalsQuery = useQuery({
    queryKey: ['approvals'],
    queryFn: ({ signal }) => fetchAllApprovals(signal),
    refetchInterval: 5000,
  });

  const mutation = useMutation({
    mutationFn: async ({ type, approvalId }: { type: 'approve' | 'reject' | 'override'; approvalId: string }) => {
      if (type === 'approve') return approveApproval(approvalId, 'ui.operator', 'approved from control room');
      if (type === 'override') return overrideApproval(approvalId, 'ui.operator', 'override from control room');
      return rejectApproval(approvalId, 'ui.operator', 'rejected from control room');
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approvals'] }),
  });

  return (
    <section className="split-view">
      <div>
        <h2>Approvals</h2>
        <table className="table">
          <thead>
            <tr><th>ID</th><th>Status</th><th>Cost</th><th>Risk</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {(approvalsQuery.data ?? []).map((approval) => (
              <tr key={approval.approval_id} onClick={() => setSelected(approval)}>
                <td><code>{approval.approval_id}</code></td>
                <td>{approval.status}</td>
                <td>{approval.projected_cost ?? '-'}</td>
                <td>{approval.risk ?? '-'}</td>
                <td>
                  <div className="button-group">
                    <button onClick={() => mutation.mutate({ type: 'approve', approvalId: approval.approval_id })}>Approve</button>
                    <button className="danger" onClick={() => mutation.mutate({ type: 'reject', approvalId: approval.approval_id })}>Reject</button>
                    <button onClick={() => mutation.mutate({ type: 'override', approvalId: approval.approval_id })}>Override</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ApprovalDrawer approval={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
