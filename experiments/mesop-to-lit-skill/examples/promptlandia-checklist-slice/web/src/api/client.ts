// Typed fetch wrappers with a single error-envelope handler (§3.5). Every
// non-OK response is normalized to an ApiClientError carrying {code, message}.

import type { ApiError, ChecklistResponse } from './types';

export class ApiClientError extends Error {
  code: string;
  status: number;
  constructor(status: number, err: ApiError) {
    super(err.message);
    this.name = 'ApiClientError';
    this.code = err.code;
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, init);
  } catch (e) {
    // Network/transport failure -> uniform shape.
    throw new ApiClientError(0, {
      code: 'network_error',
      message: e instanceof Error ? e.message : 'Network error',
    });
  }

  const data = await resp.json().catch(() => null);

  if (!resp.ok) {
    const envelope = (data && (data as { error?: ApiError }).error) || {
      code: 'unknown_error',
      message: `Request failed (${resp.status})`,
    };
    throw new ApiClientError(resp.status, envelope);
  }
  return data as T;
}

export function checklist(prompt: string): Promise<ChecklistResponse> {
  return request<ChecklistResponse>('/api/checklist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
}

export const client = { checklist };
