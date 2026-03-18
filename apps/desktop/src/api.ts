import { isTauriRuntime } from "./tauri";
import type { PatientDetail, PatientSummary, RetinalImage, StudySession } from "./types";

const baseHeaders = {
  Accept: "application/json",
};

type ApiErrorKind = "network" | "http" | "parse" | "unknown";
type RequestOptions = RequestInit & {
  expectJson?: boolean;
};

type HealthCheckResult = {
  ok: boolean;
  error: ApiError | null;
};

type ErrorPayload = {
  detail?: string;
  message?: string;
};

export type PatientFilters = {
  session_date_from?: string;
  session_date_to?: string;
  laterality?: string;
};

export class ApiError extends Error {
  kind: ApiErrorKind;
  status: number | null;
  detail: string;
  retryable: boolean;

  constructor({
    kind,
    status = null,
    detail,
    retryable,
  }: {
    kind: ApiErrorKind;
    status?: number | null;
    detail: string;
    retryable: boolean;
  }) {
    super(detail);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
    this.retryable = retryable;
  }
}

function apiBaseUrl(): string {
  return isTauriRuntime() ? "http://127.0.0.1:8000" : "/api";
}

function buildQueryString(params: Record<string, string | undefined>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value && value.trim()) {
      searchParams.set(key, value.trim());
    }
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

function normalizeErrorPayload(data: unknown): string | null {
  if (!data || typeof data !== "object") {
    return null;
  }

  const payload = data as ErrorPayload;
  if (typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail.trim();
  }
  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message.trim();
  }
  return null;
}

async function buildHttpError(response: Response): Promise<ApiError> {
  const data = await response.json().catch(() => null);
  const detail = normalizeErrorPayload(data) ?? `Request failed with status ${response.status}`;
  return new ApiError({
    kind: "http",
    status: response.status,
    detail,
    retryable: response.status >= 500 || response.status === 429,
  });
}

function buildRequestError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (error instanceof TypeError) {
    return new ApiError({
      kind: "network",
      detail: "Unable to reach the local API.",
      retryable: true,
    });
  }
  return new ApiError({
    kind: "unknown",
    detail: error instanceof Error ? error.message : "Unexpected request failure",
    retryable: true,
  });
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { expectJson = true, ...requestInit } = options;

  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      headers: requestInit.body instanceof FormData ? baseHeaders : { ...baseHeaders, ...requestInit.headers },
      ...requestInit,
    });

    if (!response.ok) {
      throw await buildHttpError(response);
    }

    if (!expectJson) {
      return undefined as T;
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError({
        kind: "parse",
        detail: "Received an invalid response from the local API.",
        retryable: true,
      });
    }
  } catch (error) {
    throw buildRequestError(error);
  }
}

export function describeApiError(error: unknown, action: string): string {
  const apiError = buildRequestError(error);

  if (apiError.kind === "network") {
    return `${action}. Check that the local API is running, then retry.`;
  }
  if (apiError.status === 404) {
    return `${action}. The requested record is no longer available.`;
  }
  if (apiError.status === 409) {
    return apiError.detail;
  }
  if (apiError.status === 422) {
    return `${action}. Some required values are missing or invalid.`;
  }
  return apiError.detail || action;
}

export async function fetchPatients(query = "", limit = 100): Promise<PatientSummary[]> {
  const search = buildQueryString({ q: query, limit: String(limit) });
  return request<PatientSummary[]>(`/patients${search}`);
}

export async function createPatient(input: {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender_text: string;
}): Promise<PatientSummary> {
  return request<PatientSummary>("/patients", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
}

export async function fetchPatient(
  patientId: string,
  filters: PatientFilters = {},
): Promise<PatientDetail> {
  return request<PatientDetail>(`/patients/${patientId}${buildQueryString(filters)}`);
}

export async function createSession(
  patientId: string,
  input: {
    session_date: string;
    operator_name?: string;
    notes?: string;
  },
): Promise<StudySession> {
  return request<StudySession>(`/patients/${patientId}/sessions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
}

export async function updateSession(
  sessionId: string,
  input: {
    session_date: string;
    operator_name?: string;
    notes?: string;
  },
): Promise<StudySession> {
  return request<StudySession>(`/sessions/${sessionId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
}

export async function importImage(
  sessionId: string,
  input: {
    laterality: string;
    notes?: string;
    file: File;
  },
): Promise<void> {
  const body = new FormData();
  body.append("laterality", input.laterality);
  body.append("notes", input.notes ?? "");
  body.append("file", input.file);

  await request<void>(`/sessions/${sessionId}/images/import`, {
    method: "POST",
    body,
    expectJson: false,
  });
}

export async function updateImage(
  imageId: string,
  input: {
    laterality: string;
    notes?: string;
    captured_at?: string | null;
  },
): Promise<RetinalImage> {
  return request<RetinalImage>(`/images/${imageId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
}

export async function fetchHealth(): Promise<HealthCheckResult> {
  try {
    const response = await fetch(`${apiBaseUrl()}/health`, { headers: baseHeaders });
    if (!response.ok) {
      return { ok: false, error: await buildHttpError(response) };
    }

    const data = (await response.json()) as { status?: string };
    if (data.status !== "ok") {
      return {
        ok: false,
        error: new ApiError({
          kind: "parse",
          detail: "Local API health response was invalid.",
          retryable: true,
        }),
      };
    }
    return { ok: true, error: null };
  } catch (error) {
    return { ok: false, error: buildRequestError(error) };
  }
}

export async function openImageExternally(imageId: string): Promise<void> {
  await request<void>(`/images/${imageId}/open-external`, {
    method: "POST",
    expectJson: false,
  });
}

export function imageFileUrl(imageId: string): string {
  return `${apiBaseUrl()}/images/${imageId}/file`;
}

export function imageThumbnailUrl(imageId: string): string {
  return `${apiBaseUrl()}/images/${imageId}/thumbnail`;
}
