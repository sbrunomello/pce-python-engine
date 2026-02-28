import { z } from 'zod';
import { apiRequest } from './client';

const TwinSchema = z.object({
  phase: z.string(),
  budget_total: z.number(),
  budget_remaining: z.number(),
  risk_level: z.string(),
  components: z.array(z.record(z.unknown())).default([]),
  purchase_history: z.array(z.record(z.unknown())).default([]),
  audit_trail: z.array(z.record(z.unknown())).default([]),
});

const ApprovalSchema = z.object({
  approval_id: z.string(),
  decision_id: z.string().optional(),
  status: z.string(),
  action_type: z.string().optional(),
  projected_cost: z.number().optional(),
  risk: z.string().optional(),
  rationale: z.string().optional(),
  created_at: z.string().optional(),
  metadata: z.record(z.unknown()).optional(),
});

const StateSchema = z.object({
  state: z.record(z.unknown()),
});

const CciSchema = z.object({
  cci: z.number(),
});

const CciHistorySchema = z.object({
  history: z.array(z.record(z.unknown())),
});

const RoboticsStateResponseSchema = z.object({
  robotics_twin: TwinSchema,
});

const ApprovalsResponseSchema = z.object({
  pending: z.array(ApprovalSchema),
});

export type RoboticsTwin = z.infer<typeof TwinSchema>;
export type Approval = z.infer<typeof ApprovalSchema>;

export async function fetchRoboticsState(signal?: AbortSignal): Promise<RoboticsTwin> {
  const response = RoboticsStateResponseSchema.parse(
    await apiRequest('/os/robotics/state', { signal }),
  );
  return response.robotics_twin;
}

export async function fetchPendingApprovals(signal?: AbortSignal): Promise<Approval[]> {
  const response = ApprovalsResponseSchema.parse(await apiRequest('/os/approvals', { signal }));
  return response.pending;
}

export async function approveApproval(
  approvalId: string,
  actor: string,
  notes: string,
): Promise<void> {
  await apiRequest(`/os/approvals/${approvalId}/approve`, {
    method: 'POST',
    body: { actor, notes },
  });
}

export async function rejectApproval(
  approvalId: string,
  actor: string,
  reason: string,
): Promise<void> {
  await apiRequest(`/os/approvals/${approvalId}/reject`, {
    method: 'POST',
    body: { actor, reason },
  });
}

export async function fetchState(signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = StateSchema.parse(await apiRequest('/state', { signal }));
  return response.state;
}

export async function fetchCci(signal?: AbortSignal): Promise<number> {
  const response = CciSchema.parse(await apiRequest('/cci', { signal }));
  return response.cci;
}

export async function fetchCciHistory(signal?: AbortSignal): Promise<Record<string, unknown>[]> {
  const response = CciHistorySchema.parse(await apiRequest('/cci/history', { signal }));
  return response.history;
}
