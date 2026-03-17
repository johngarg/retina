import { isTauriRuntime } from "./tauri";
import type { PatientDetail, PatientSummary, StudySession } from "./types";

const baseHeaders = {
  Accept: "application/json",
};

function apiBaseUrl(): string {
  return isTauriRuntime() ? "http://127.0.0.1:8000" : "/api";
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(data.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function fetchPatients(query = ""): Promise<PatientSummary[]> {
  const search = query ? `?q=${encodeURIComponent(query)}` : "";
  const response = await fetch(`${apiBaseUrl()}/patients${search}`, { headers: baseHeaders });
  return parse<PatientSummary[]>(response);
}

export async function createPatient(input: {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender_text: string;
}): Promise<PatientSummary> {
  const response = await fetch(`${apiBaseUrl()}/patients`, {
    method: "POST",
    headers: {
      ...baseHeaders,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
  return parse<PatientSummary>(response);
}

export async function fetchPatient(patientId: string): Promise<PatientDetail> {
  const response = await fetch(`${apiBaseUrl()}/patients/${patientId}`, { headers: baseHeaders });
  return parse<PatientDetail>(response);
}

export async function createSession(
  patientId: string,
  input: {
    session_date: string;
    operator_name?: string;
    notes?: string;
  },
): Promise<StudySession> {
  const response = await fetch(`${apiBaseUrl()}/patients/${patientId}/sessions`, {
    method: "POST",
    headers: {
      ...baseHeaders,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
  return parse<StudySession>(response);
}

export async function importImage(
  sessionId: string,
  input: {
    laterality: string;
    image_type: string;
    notes?: string;
    file: File;
  },
): Promise<void> {
  const body = new FormData();
  body.append("laterality", input.laterality);
  body.append("image_type", input.image_type);
  body.append("notes", input.notes ?? "");
  body.append("file", input.file);

  const response = await fetch(`${apiBaseUrl()}/sessions/${sessionId}/images/import`, {
    method: "POST",
    body,
  });
  await parse(response);
}

export async function fetchHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl()}/health`, { headers: baseHeaders });
    if (!response.ok) {
      return false;
    }
    const data = await response.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

export function imageFileUrl(imageId: string): string {
  return `${apiBaseUrl()}/images/${imageId}/file`;
}

export function imageThumbnailUrl(imageId: string): string {
  return `${apiBaseUrl()}/images/${imageId}/thumbnail`;
}
