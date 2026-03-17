import type { PatientDetail, PatientSummary, StudySession } from "./types";

const baseHeaders = {
  Accept: "application/json",
};

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(data.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function fetchPatients(query = ""): Promise<PatientSummary[]> {
  const search = query ? `?q=${encodeURIComponent(query)}` : "";
  const response = await fetch(`/api/patients${search}`, { headers: baseHeaders });
  return parse<PatientSummary[]>(response);
}

export async function createPatient(input: {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender_text: string;
}): Promise<PatientSummary> {
  const response = await fetch("/api/patients", {
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
  const response = await fetch(`/api/patients/${patientId}`, { headers: baseHeaders });
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
  const response = await fetch(`/api/patients/${patientId}/sessions`, {
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

  const response = await fetch(`/api/sessions/${sessionId}/images/import`, {
    method: "POST",
    body,
  });
  await parse(response);
}
