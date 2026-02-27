export interface EventRequest {
  event_type: 'observation.assistant.v1' | 'feedback.assistant.v1';
  source: string;
  payload: Record<string, unknown>;
}

export interface AssistantActionPayload {
  type?: string;
  text?: string;
  [key: string]: unknown;
}

export interface EventsResponse {
  event_id: string;
  value_score?: number;
  cci?: number;
  cci_components?: Record<string, number>;
  action_type?: string;
  action?: AssistantActionPayload | string;
  metadata?: {
    explain?: Record<string, unknown>;
    [key: string]: unknown;
  };
  success: boolean;
  epsilon?: number;
  assistant_learning?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface FeedbackPayload {
  reward: number;
  rating?: number;
  accepted?: boolean;
  notes?: string;
}

export interface ApiErrorBody {
  detail?: unknown;
  [key: string]: unknown;
}

export interface CciResponse {
  cci: number;
}

export interface CciHistoryResponse {
  history: Array<Record<string, unknown>>;
}

export interface StateResponse {
  state: Record<string, unknown>;
}

export interface ChatEntry {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  createdAt: number;
  event?: EventsResponse;
}

export interface TelemetrySnapshot {
  valueScore?: number;
  cci?: number;
  overrideReason?: string;
  finalProfile?: string;
  epsilon?: number;
  model?: string;
  latencyMs?: number;
  cciComponents?: Record<string, number>;
}
