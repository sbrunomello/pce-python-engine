import { z } from 'zod';

const API_PREFIX = '/api';

const ApiErrorSchema = z.object({
  detail: z.string().optional(),
});

type HttpMethod = 'GET' | 'POST';

export class ApiError extends Error {
  public readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function apiRequest<TResponse>(
  path: string,
  options: {
    method?: HttpMethod;
    body?: object;
    signal?: AbortSignal;
  } = {},
): Promise<TResponse> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;

    try {
      const payload = ApiErrorSchema.parse(await response.json());
      if (payload.detail) {
        errorMessage = payload.detail;
      }
    } catch {
      // Keep fallback message when response body is not JSON.
    }

    throw new ApiError(errorMessage, response.status);
  }

  return (await response.json()) as TResponse;
}
