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
  tests: z.array(z.record(z.unknown())).default([]),
  simulations: z.array(z.record(z.unknown())).default([]),
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
  summary: z.string().optional(),
});

const ControlStateSchema = z.object({
  twin_snapshot: TwinSchema,
  os_metrics: z.record(z.unknown()),
  policy_state: z.record(z.unknown()),
  last_n_audit_trail: z.array(z.record(z.unknown())),
});

const ApprovalsResponseSchema = z.object({
  items: z.array(ApprovalSchema),
  pending: z.array(ApprovalSchema),
});

const TranscriptItemSchema = z.object({
  cursor: z.number(),
  ts: z.string(),
  kind: z.string(),
  agent: z.string().optional(),
  payload: z.record(z.unknown()),
  correlation_id: z.string(),
  decision_id: z.string().optional(),
});

const TranscriptResponseSchema = z.object({
  cursor: z.number(),
  items: z.array(TranscriptItemSchema),
});

export type RoboticsTwin = z.infer<typeof TwinSchema>;
export type Approval = z.infer<typeof ApprovalSchema>;
export type TranscriptItem = z.infer<typeof TranscriptItemSchema>;

export async function fetchControlState(signal?: AbortSignal) {
  return ControlStateSchema.parse(await apiRequest('/v1/os/state', { signal }));
}

export async function fetchPendingApprovals(signal?: AbortSignal): Promise<Approval[]> {
  const response = ApprovalsResponseSchema.parse(await apiRequest('/v1/os/approvals', { signal }));
  return response.pending;
}

export async function fetchAllApprovals(signal?: AbortSignal): Promise<Approval[]> {
  const response = ApprovalsResponseSchema.parse(await apiRequest('/v1/os/approvals', { signal }));
  return response.items;
}

export async function approveApproval(approvalId: string, actor: string, notes: string): Promise<void> {
  await apiRequest(`/v1/os/approvals/${approvalId}/approve`, { method: 'POST', body: { actor, notes } });
}

export async function rejectApproval(approvalId: string, actor: string, reason: string): Promise<void> {
  await apiRequest(`/v1/os/approvals/${approvalId}/reject`, { method: 'POST', body: { actor, reason } });
}

export async function overrideApproval(approvalId: string, actor: string, notes: string): Promise<void> {
  await apiRequest(`/v1/os/approvals/${approvalId}/override`, { method: 'POST', body: { actor, notes } });
}

export async function fetchTranscriptSince(since: number, signal?: AbortSignal): Promise<{ cursor: number; items: TranscriptItem[] }> {
  return TranscriptResponseSchema.parse(await apiRequest(`/v1/os/agents/transcript?since=${since}`, { signal }));
}

const demoEvents = [
  { event_type: 'project.goal.defined', source: 'ui-demo', payload: { domain: 'os.robotics', correlation_id: 'demo-control-room', goal: 'Build rover v2' } },
  { event_type: 'part.candidate.added', source: 'ui-demo', payload: { domain: 'os.robotics', correlation_id: 'demo-control-room', component_id: 'motor-x1', qty: 2, estimated_unit_cost: 120.0 } },
  { event_type: 'purchase.requested', source: 'ui-demo', payload: { domain: 'os.robotics', correlation_id: 'demo-control-room', purchase_id: 'demo-po-001', projected_cost: 240.0, risk_level: 'MEDIUM' } },
];

export async function sendDemoEvent(): Promise<void> {
  const event = demoEvents[Math.floor(Math.random() * demoEvents.length)];
  await apiRequest('/v1/events', { method: 'POST', body: event });
}
