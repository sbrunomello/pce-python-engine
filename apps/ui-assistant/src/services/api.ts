import type {
  ApiErrorBody,
  CciHistoryResponse,
  CciResponse,
  EventsResponse,
  FeedbackPayload,
  StateResponse,
} from '../types';

const API_ROOT = '/api';

class ApiError extends Error {
  status: number;
  body?: ApiErrorBody;

  constructor(message: string, status: number, body?: ApiErrorBody) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

async function request<TResponse>(path: string, init?: RequestInit): Promise<TResponse> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => undefined)) as ApiErrorBody | undefined;
    throw new ApiError(`API error (${response.status})`, response.status, body);
  }

  return (await response.json()) as TResponse;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function sendObservation(sessionId: string, text: string): Promise<EventsResponse> {
  return request<EventsResponse>('/events', {
    method: 'POST',
    body: JSON.stringify({
      event_type: 'observation.assistant.v1',
      source: 'assistant-ui',
      payload: {
        domain: 'assistant',
        session_id: sessionId,
        text,
        tags: ['observation', 'assistant'],
        context: { channel: 'ui' },
      },
    }),
  });
}

export function sendFeedback(sessionId: string, payload: FeedbackPayload): Promise<EventsResponse> {
  return request<EventsResponse>('/events', {
    method: 'POST',
    body: JSON.stringify({
      event_type: 'feedback.assistant.v1',
      source: 'assistant-ui',
      payload: {
        domain: 'assistant',
        session_id: sessionId,
        reward: payload.reward,
        rating: payload.rating,
        accepted: payload.accepted,
        notes: payload.notes,
        tags: ['feedback', 'assistant'],
      },
    }),
  });
}

export function clearAssistantMemory(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/agents/assistant/control/clear_memory', {
    method: 'POST',
  });
}

export function getState(): Promise<StateResponse> {
  return request<StateResponse>('/state');
}

export function getCci(): Promise<CciResponse> {
  return request<CciResponse>('/cci');
}

export function getCciHistory(): Promise<CciHistoryResponse> {
  return request<CciHistoryResponse>('/cci/history');
}
