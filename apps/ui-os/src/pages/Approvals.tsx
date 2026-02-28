import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import { approveApproval, fetchPendingApprovals, rejectApproval, type Approval } from '../api/os';
import { useToast } from '../components/Toast';

type ModalMode = 'approve' | 'reject';

export function ApprovalsPage(): JSX.Element {
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null);
  const [mode, setMode] = useState<ModalMode>('approve');
  const [actor, setActor] = useState('');
  const [notes, setNotes] = useState('');

  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const approvalsQuery = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: ({ signal }) => fetchPendingApprovals(signal),
  });

  const mutation = useMutation({
    mutationFn: async () => {
      if (!selectedApproval) {
        return;
      }

      if (mode === 'approve') {
        return approveApproval(selectedApproval.approval_id, actor.trim(), notes.trim());
      }

      return rejectApproval(selectedApproval.approval_id, actor.trim(), notes.trim());
    },
    onSuccess: () => {
      showToast('Approval atualizada com sucesso.', 'success');
      queryClient.invalidateQueries({ queryKey: ['pending-approvals'] });
      queryClient.invalidateQueries({ queryKey: ['robotics-state'] });
      closeModal();
    },
    onError: (error) => {
      console.error('Failed to resolve approval', error);
      if (error instanceof ApiError && error.status === 409) {
        showToast('insufficient_budget_for_purchase', 'error');
        return;
      }
      showToast('Falha ao resolver approval.', 'error');
    },
  });

  const sortedApprovals = useMemo(
    () => (approvalsQuery.data ? [...approvalsQuery.data] : []),
    [approvalsQuery.data],
  );

  function openModal(nextMode: ModalMode, approval: Approval): void {
    setMode(nextMode);
    setSelectedApproval(approval);
    setActor('');
    setNotes('');
  }

  function closeModal(): void {
    setSelectedApproval(null);
    setActor('');
    setNotes('');
  }

  function onConfirm(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!actor.trim()) {
      showToast('O campo actor é obrigatório.', 'error');
      return;
    }
    if (!notes.trim()) {
      showToast(mode === 'approve' ? 'O campo notes é obrigatório.' : 'O campo reason é obrigatório.', 'error');
      return;
    }
    mutation.mutate();
  }

  return (
    <section>
      <header>
        <h2>Approvals</h2>
        <p>Fluxo de approve/reject para ações pendentes.</p>
      </header>

      {approvalsQuery.isLoading ? (
        <p>Carregando approvals...</p>
      ) : sortedApprovals.length === 0 ? (
        <p>Nenhuma approval pendente.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Ação</th>
              <th>Risco</th>
              <th>Custo</th>
              <th>Criado em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {sortedApprovals.map((approval) => (
              <tr key={approval.approval_id}>
                <td>{approval.approval_id}</td>
                <td>{approval.action_type ?? '-'}</td>
                <td>{approval.risk ?? '-'}</td>
                <td>{approval.projected_cost ?? '-'}</td>
                <td>{approval.created_at ?? '-'}</td>
                <td>
                  <div className="button-group">
                    <button type="button" onClick={() => openModal('approve', approval)}>
                      Approve
                    </button>
                    <button type="button" className="danger" onClick={() => openModal('reject', approval)}>
                      Reject
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedApproval && (
        <div className="modal-backdrop" role="presentation" onClick={closeModal}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h3>{mode === 'approve' ? 'Approve request' : 'Reject request'}</h3>
            <p>
              Approval ID: <code>{selectedApproval.approval_id}</code>
            </p>
            <form onSubmit={onConfirm}>
              <label>
                Actor
                <input value={actor} onChange={(event) => setActor(event.target.value)} placeholder="operador" />
              </label>
              <label>
                {mode === 'approve' ? 'Notes' : 'Reason'}
                <textarea
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder={mode === 'approve' ? 'aprovado' : 'motivo da rejeição'}
                />
              </label>
              <div className="button-group">
                <button type="button" onClick={closeModal}>
                  Cancelar
                </button>
                <button type="submit" disabled={mutation.isPending}>
                  {mutation.isPending ? 'Enviando...' : 'Confirmar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
