import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import {
  archivePatient,
  ApiError,
  type PatientFilters,
  createPatient,
  createSession,
  describeApiError,
  exportBackup,
  fetchHealth,
  fetchPatient,
  fetchPatients,
  imageFileUrl,
  imageThumbnailUrl,
  importImage,
  openImageExternally,
  restoreBackup,
  unarchivePatient,
  updateImage,
  updatePatient,
  updateSession,
} from "./api";
import { ensureBackendStarted, isTauriRuntime, waitForBackendHealth } from "./tauri";
import type { PatientDetail, PatientSummary, RetinalImage, StudySession } from "./types";

type PatientForm = {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender_text: string;
};

type SessionForm = {
  session_date: string;
  operator_name: string;
  notes: string;
};

type UploadForm = {
  laterality: string;
  notes: string;
  file: File | null;
};

type ImageEditForm = {
  laterality: string;
  captured_at: string;
  notes: string;
};

type EyeSide = "left" | "right";
type EyeUploadForms = Record<EyeSide, UploadForm>;
type SessionFilters = {
  session_date_from: string;
  session_date_to: string;
  laterality: string;
};
type BootState = "checking" | "starting" | "ready" | "error";
type WorkspaceView = "sessions" | "viewer";
type LoadStatus = "idle" | "loading" | "ready" | "error";
type LoadState = {
  status: LoadStatus;
  message: string | null;
};
type NoticeTone = "error" | "success" | "info";
type Notice = {
  tone: NoticeTone;
  message: string;
} | null;

const initialPatientForm: PatientForm = {
  first_name: "",
  last_name: "",
  date_of_birth: "",
  gender_text: "F",
};

const initialSessionForm = (): SessionForm => ({
  session_date: new Date().toISOString().slice(0, 10),
  operator_name: "",
  notes: "",
});

const makeUploadForm = (laterality: string): UploadForm => ({
  laterality,
  notes: "",
  file: null,
});

const initialEyeUploadForms = (): EyeUploadForms => ({
  left: makeUploadForm("left"),
  right: makeUploadForm("right"),
});

const initialSessionFilters = (): SessionFilters => ({
  session_date_from: "",
  session_date_to: "",
  laterality: "",
});

function buildSessionDraft(session: StudySession): SessionForm {
  return {
    session_date: session.session_date,
    operator_name: session.operator_name ?? "",
    notes: session.notes ?? "",
  };
}

function toDateTimeLocal(value: string | null): string {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hours = `${date.getHours()}`.padStart(2, "0");
  const minutes = `${date.getMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function buildImageDraft(image: RetinalImage): ImageEditForm {
  return {
    laterality: image.laterality,
    captured_at: toDateTimeLocal(image.captured_at),
    notes: image.notes ?? "",
  };
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString();
}

function formatDateTime(dateTime: string): string {
  return new Date(dateTime).toLocaleString();
}

function eyeImages(session: StudySession, eye: EyeSide): RetinalImage[] {
  return session.images.filter((image) => image.laterality === eye);
}

function otherImages(session: StudySession): RetinalImage[] {
  return session.images.filter((image) => image.laterality !== "left" && image.laterality !== "right");
}

function countImages(sessions: StudySession[]): number {
  return sessions.reduce((total, session) => total + session.images.length, 0);
}

function normalizePatientFilters(filters: SessionFilters, includeArchivedPatients: boolean): PatientFilters {
  return {
    session_date_from: filters.session_date_from || undefined,
    session_date_to: filters.session_date_to || undefined,
    laterality: filters.laterality || undefined,
    include_archived: includeArchivedPatients ? "true" : undefined,
  };
}

function hasActiveSessionFilters(filters: SessionFilters): boolean {
  return Boolean(filters.session_date_from || filters.session_date_to || filters.laterality);
}

const PATIENT_LIST_LIMIT = 100;

function isNetworkApiError(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "network";
}

function App() {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [selectedPatient, setSelectedPatient] = useState<PatientDetail | null>(null);
  const [selectedImage, setSelectedImage] = useState<RetinalImage | null>(null);
  const [search, setSearch] = useState("");
  const [includeArchivedPatients, setIncludeArchivedPatients] = useState(false);
  const [sessionFilters, setSessionFilters] = useState<SessionFilters>(initialSessionFilters);
  const [patientForm, setPatientForm] = useState<PatientForm>(initialPatientForm);
  const [patientDraft, setPatientDraft] = useState<PatientForm>(initialPatientForm);
  const [sessionForm, setSessionForm] = useState<SessionForm>(initialSessionForm);
  const [sessionDrafts, setSessionDrafts] = useState<Record<string, SessionForm>>({});
  const [sessionUploads, setSessionUploads] = useState<Record<string, EyeUploadForms>>({});
  const [imageDrafts, setImageDrafts] = useState<Record<string, ImageEditForm>>({});
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("sessions");
  const [patientListState, setPatientListState] = useState<LoadState>({
    status: "loading",
    message: null,
  });
  const [patientDetailState, setPatientDetailState] = useState<LoadState>({
    status: "idle",
    message: null,
  });
  const [notice, setNotice] = useState<Notice>(null);
  const [bootState, setBootState] = useState<BootState>("checking");
  const [bootMessage, setBootMessage] = useState("Checking backend availability...");
  const [connectionMessage, setConnectionMessage] = useState("Local API status unknown.");
  const [archiveConfirmPatientId, setArchiveConfirmPatientId] = useState<string | null>(null);
  const restoreInputRef = useRef<HTMLInputElement | null>(null);

  function reportRequestFailure(error: unknown, action: string, target: "list" | "detail" | "notice") {
    const message = describeApiError(error, action);
    if (target === "list") {
      setPatientListState({ status: "error", message });
    } else if (target === "detail") {
      setPatientDetailState({ status: "error", message });
    } else {
      setNotice({ tone: "error", message });
    }

    if (isNetworkApiError(error)) {
      setConnectionMessage("Local API unreachable. Retry after the backend is available again.");
    }
  }

  function reportRequestSuccess(message?: string) {
    setConnectionMessage("Local API connected.");
    if (message) {
      setNotice({ tone: "success", message });
    }
  }

  async function refreshPatients(
    nextQuery = search,
    preferredPatientId?: string,
    nextIncludeArchived = includeArchivedPatients,
  ) {
    setPatientListState({ status: "loading", message: null });
    try {
      const result = await fetchPatients(nextQuery, PATIENT_LIST_LIMIT, nextIncludeArchived);
      setPatients(result);
      setPatientListState({ status: "ready", message: null });
      setConnectionMessage("Local API connected.");
      const nextSelectedId =
        preferredPatientId && result.some((patient) => patient.id === preferredPatientId)
          ? preferredPatientId
          : selectedPatientId && result.some((patient) => patient.id === selectedPatientId)
            ? selectedPatientId
            : result[0]?.id ?? null;
      setSelectedPatientId(nextSelectedId);
    } catch (err) {
      reportRequestFailure(err, "Unable to load patients", "list");
    }
  }

  async function refreshPatient(
    patientId: string,
    preferredImageId?: string | null,
    filters: SessionFilters = sessionFilters,
  ): Promise<boolean> {
    setPatientDetailState({ status: "loading", message: null });
    try {
      const detail = await fetchPatient(patientId, normalizePatientFilters(filters, includeArchivedPatients));
      setSelectedPatient(detail);
      setPatientDetailState({ status: "ready", message: null });
      setConnectionMessage("Local API connected.");
      setSessionDrafts((current) => {
        const next = { ...current };
        for (const session of detail.sessions) {
          next[session.id] = buildSessionDraft(session);
        }
        return next;
      });
      setSessionUploads((current) => {
        const next = { ...current };
        for (const session of detail.sessions) {
          next[session.id] = next[session.id] ?? initialEyeUploadForms();
        }
        return next;
      });

      const allImages = detail.sessions.flatMap((session) => session.images);
      const nextSelectedImage =
        (preferredImageId
          ? allImages.find((image) => image.id === preferredImageId)
          : null) ??
        (selectedImage ? allImages.find((image) => image.id === selectedImage.id) : null) ??
        allImages[0] ??
        null;
      setSelectedImage(nextSelectedImage);
      return true;
    } catch (err) {
      reportRequestFailure(err, "Unable to load patient detail", "detail");
      return false;
    }
  }

  async function bootstrapApp() {
    setBootState("checking");
    setBootMessage("Checking backend availability...");
    setNotice(null);
    setConnectionMessage("Checking local API availability...");
    let startupDetail: string | null = null;

    const health = await fetchHealth();
    if (health.ok) {
      setBootState("ready");
      setConnectionMessage("Local API connected.");
      await refreshPatients();
      return;
    }

    if (isTauriRuntime()) {
      setBootState("starting");
      setBootMessage("Starting the local API...");
      try {
        const result = await ensureBackendStarted();
        startupDetail = result.detail;
        setBootMessage(result.detail);
      } catch (err) {
        setBootState("error");
        setBootMessage(err instanceof Error ? err.message : "Unable to start the backend process.");
        setConnectionMessage("Local API startup failed.");
        return;
      }
    } else {
      setBootState("error");
      setBootMessage(
        health.error
          ? describeApiError(health.error, "Backend is not running")
          : "Backend is not running. Start the API on http://127.0.0.1:8000 and retry.",
      );
      setConnectionMessage("Local API offline.");
      return;
    }

    const healthAttempts = isTauriRuntime() ? 120 : 40;
    const isHealthy = await waitForBackendHealth(async () => (await fetchHealth()).ok, healthAttempts, 500);
    if (!isHealthy) {
      setBootState("error");
      setBootMessage(
        startupDetail
          ? `Backend did not become healthy in time. ${startupDetail}`
          : "Backend did not become healthy in time. Check the desktop logs and retry.",
      );
      setConnectionMessage("Local API startup timed out.");
      return;
    }

    setBootState("ready");
    setBootMessage("Backend is ready.");
    setConnectionMessage("Local API connected.");
    await refreshPatients();
  }

  useEffect(() => {
    void bootstrapApp();
  }, []);

  useEffect(() => {
    if (bootState !== "ready") {
      return;
    }

    if (!selectedPatientId) {
      setSelectedPatient(null);
      setPatientDetailState({ status: "idle", message: null });
      return;
    }
    void refreshPatient(selectedPatientId, undefined, sessionFilters);
  }, [bootState, selectedPatientId, includeArchivedPatients]);

  useEffect(() => {
    if (!selectedImage) {
      return;
    }
    setImageDrafts((current) => ({
      ...current,
      [selectedImage.id]: buildImageDraft(selectedImage),
    }));
  }, [selectedImage]);

  useEffect(() => {
    setArchiveConfirmPatientId(null);
  }, [selectedPatientId]);

  useEffect(() => {
    if (!selectedPatient) {
      setPatientDraft(initialPatientForm);
      return;
    }
    setPatientDraft({
      first_name: selectedPatient.first_name,
      last_name: selectedPatient.last_name,
      date_of_birth: selectedPatient.date_of_birth,
      gender_text: selectedPatient.gender_text ?? "",
    });
  }, [selectedPatient]);

  async function onCreatePatient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    try {
      const created = await createPatient(patientForm);
      setPatientForm(initialPatientForm);
      await refreshPatients(search, created.id);
      reportRequestSuccess("Patient created.");
      setWorkspaceView("sessions");
    } catch (err) {
      reportRequestFailure(err, "Unable to create patient", "notice");
    }
  }

  async function onCreateSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPatientId) {
      return;
    }
    setNotice(null);
    try {
      const created = await createSession(selectedPatientId, sessionForm);
      setSessionForm(initialSessionForm());
      const refreshed = await refreshPatient(selectedPatientId);
      if (refreshed) {
        setSessionUploads((current) => ({ ...current, [created.id]: initialEyeUploadForms() }));
        reportRequestSuccess("Visit created.");
        setWorkspaceView("sessions");
      }
    } catch (err) {
      reportRequestFailure(err, "Unable to create session", "notice");
    }
  }

  async function onSavePatient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPatientId) {
      return;
    }

    setNotice(null);
    try {
      await updatePatient(selectedPatientId, patientDraft);
      await refreshPatients(search, selectedPatientId);
      if (await refreshPatient(selectedPatientId, selectedImage?.id ?? null)) {
        reportRequestSuccess("Patient details saved.");
      }
    } catch (err) {
      reportRequestFailure(err, "Unable to update patient", "notice");
    }
  }

  async function onArchivePatient() {
    if (!selectedPatientId || !selectedPatient) {
      return;
    }
    setArchiveConfirmPatientId(selectedPatientId);
  }

  async function onConfirmArchivePatient() {
    if (!selectedPatientId || !selectedPatient) {
      return;
    }

    setNotice(null);
    try {
      await archivePatient(selectedPatientId);
      setArchiveConfirmPatientId(null);
      setSelectedPatientId(null);
      setSelectedPatient(null);
      setSelectedImage(null);
      await refreshPatients(search);
      reportRequestSuccess("Patient archived.");
    } catch (err) {
      reportRequestFailure(err, "Unable to archive patient", "notice");
    }
  }

  async function onUnarchivePatient() {
    if (!selectedPatientId) {
      return;
    }

    setNotice(null);
    try {
      await unarchivePatient(selectedPatientId);
      await refreshPatients(search, selectedPatientId, true);
      if (await refreshPatient(selectedPatientId, selectedImage?.id ?? null)) {
        reportRequestSuccess("Patient restored to the active list.");
      }
    } catch (err) {
      reportRequestFailure(err, "Unable to restore patient", "notice");
    }
  }

  async function onSaveSession(event: FormEvent<HTMLFormElement>, sessionId: string) {
    event.preventDefault();
    if (!selectedPatientId) {
      return;
    }

    const draft = sessionDrafts[sessionId];
    if (!draft) {
      return;
    }

    setNotice(null);
    try {
      await updateSession(sessionId, draft);
      if (await refreshPatient(selectedPatientId, selectedImage?.id ?? null)) {
        reportRequestSuccess("Visit details saved.");
      }
    } catch (err) {
      reportRequestFailure(err, "Unable to update session", "notice");
    }
  }

  async function onImportImage(event: FormEvent<HTMLFormElement>, sessionId: string, eye: EyeSide) {
    event.preventDefault();
    const upload = sessionUploads[sessionId]?.[eye] ?? makeUploadForm(eye);
    if (!upload.file || !selectedPatientId) {
      setNotice({ tone: "error", message: `Choose a ${eye} eye image before importing.` });
      return;
    }

    setNotice(null);
    try {
      await importImage(sessionId, { laterality: eye, notes: upload.notes, file: upload.file });
      setSessionUploads((current) => ({
        ...current,
        [sessionId]: {
          ...(current[sessionId] ?? initialEyeUploadForms()),
          [eye]: makeUploadForm(eye),
        },
      }));
      if (await refreshPatient(selectedPatientId)) {
        reportRequestSuccess(`${eye === "left" ? "Left" : "Right"} eye image imported.`);
        setWorkspaceView("viewer");
      }
    } catch (err) {
      reportRequestFailure(err, `Unable to import ${eye} eye image`, "notice");
    }
  }

  async function onSaveImage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPatientId || !selectedImage) {
      return;
    }

    const draft = imageDrafts[selectedImage.id];
    if (!draft) {
      return;
    }

    setNotice(null);
    try {
      await updateImage(selectedImage.id, {
        laterality: draft.laterality,
        captured_at: draft.captured_at || null,
        notes: draft.notes,
      });
      if (await refreshPatient(selectedPatientId, selectedImage.id)) {
        reportRequestSuccess("Image metadata saved.");
      }
    } catch (err) {
      reportRequestFailure(err, "Unable to update image metadata", "notice");
    }
  }

  async function onOpenImageExternally() {
    if (!selectedImage) {
      return;
    }

    setNotice(null);
    try {
      await openImageExternally(selectedImage.id);
      reportRequestSuccess("Opened image in the default viewer.");
    } catch (err) {
      reportRequestFailure(err, "Unable to open image in the default viewer", "notice");
    }
  }

  async function onExportBackup() {
    setNotice(null);
    try {
      const result = await exportBackup();
      reportRequestSuccess(`Backup saved to ${result.archive_path}`);
    } catch (err) {
      reportRequestFailure(err, "Unable to export backup", "notice");
    }
  }

  async function onRestoreBackupSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";

    if (!file) {
      return;
    }

    const confirmed = window.confirm(
      "Restore from backup will replace the current local patient database and managed images. Continue?",
    );
    if (!confirmed) {
      return;
    }

    setNotice({ tone: "info", message: "Restoring backup..." });
    try {
      const result = await restoreBackup(file);
      setSelectedPatientId(null);
      setSelectedPatient(null);
      setSelectedImage(null);
      setSearch("");
      setSessionFilters(initialSessionFilters());
      await refreshPatients("");
      setWorkspaceView("sessions");
      setNotice({
        tone: "success",
        message: `Backup restored from ${result.source_archive_name}. Safety backup saved to ${result.safety_backup_path}.`,
      });
      setConnectionMessage("Local API connected.");
    } catch (err) {
      reportRequestFailure(err, "Unable to restore backup", "notice");
    }
  }

  function onChooseRestoreBackup() {
    restoreInputRef.current?.click();
  }

  function updateSessionDraft(sessionId: string, next: Partial<SessionForm>) {
    setSessionDrafts((current) => ({
      ...current,
      [sessionId]: {
        ...(current[sessionId] ?? initialSessionForm()),
        ...next,
      },
    }));
  }

  function updateEyeUpload(sessionId: string, eye: EyeSide, next: Partial<UploadForm>) {
    setSessionUploads((current) => ({
      ...current,
      [sessionId]: {
        ...(current[sessionId] ?? initialEyeUploadForms()),
        [eye]: {
          ...((current[sessionId] ?? initialEyeUploadForms())[eye]),
          ...next,
        },
      },
    }));
  }

  function updateImageDraft(imageId: string, next: Partial<ImageEditForm>) {
    setImageDrafts((current) => ({
      ...current,
      [imageId]: {
        ...(current[imageId] ?? {
          laterality: "left",
          captured_at: "",
          notes: "",
        }),
        ...next,
      },
    }));
  }

  async function onApplySessionFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPatientId) {
      return;
    }

    setNotice(null);
    if (await refreshPatient(selectedPatientId, selectedImage?.id ?? null, sessionFilters)) {
      reportRequestSuccess("History filters applied.");
      setWorkspaceView("sessions");
    }
  }

  async function onClearSessionFilters() {
    const cleared = initialSessionFilters();
    setSessionFilters(cleared);
    if (!selectedPatientId) {
      return;
    }

    setNotice(null);
    if (await refreshPatient(selectedPatientId, selectedImage?.id ?? null, cleared)) {
      reportRequestSuccess("History filters cleared.");
    }
  }

  if (bootState !== "ready") {
    return (
      <div className="startup-shell">
        <section className="startup-card">
          <p className="eyebrow">Retina</p>
          <h1>Retina Startup</h1>
          <p>{bootMessage}</p>
          {bootState === "starting" || bootState === "checking" ? (
            <div className="startup-spinner" aria-hidden="true" />
          ) : null}
          <button className="primary-button" type="button" onClick={() => void bootstrapApp()}>
            Retry startup
          </button>
          {!isTauriRuntime() ? (
            <p className="muted">
              If you are running the browser version, start the local API separately before retrying.
            </p>
          ) : null}
        </section>
      </div>
    );
  }

  const connectionOffline =
    connectionMessage !== "Local API connected." &&
    connectionMessage !== "Checking local API availability...";
  const activeHistoryFilters = hasActiveSessionFilters(sessionFilters);
  const sessionCount = selectedPatient?.sessions.length ?? 0;
  const imageCount = countImages(selectedPatient?.sessions ?? []);
  const historyImages = selectedPatient?.sessions.flatMap((session) => session.images) ?? [];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <p className="eyebrow">Retina</p>
          <h1>Retina</h1>
          <p className="muted">Manage patients, visits, and retinal images.</p>
        </div>

        <section className="panel">
          <div className="panel-header">
            <h2>Patients</h2>
            <button className="ghost-button" type="button" onClick={() => void refreshPatients(search)}>
              Refresh
            </button>
          </div>
          <input
            className="text-input"
            value={search}
            placeholder="Search by first/last name or legacy ID"
            aria-label="Patient search"
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void refreshPatients(event.currentTarget.value);
              }
            }}
          />
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={includeArchivedPatients}
              onChange={(event) => {
                const nextIncludeArchived = event.target.checked;
                setIncludeArchivedPatients(nextIncludeArchived);
                void refreshPatients(search, selectedPatientId ?? undefined, nextIncludeArchived);
              }}
            />
            <span>Include archived patients in search</span>
          </label>
          <div className="patient-list">
            {patients.length >= PATIENT_LIST_LIMIT ? (
              <p className="muted patient-list-hint">
                Showing up to {PATIENT_LIST_LIMIT} patients. Search to narrow large lists.
              </p>
            ) : null}
            {patientListState.status === "loading" ? <p className="muted">Loading patients...</p> : null}
            {patientListState.status === "error" ? (
              <div className="inline-state">
                <p>{patientListState.message}</p>
                <button className="ghost-button" type="button" onClick={() => void refreshPatients(search)}>
                  Retry patient list
                </button>
              </div>
            ) : null}
            {patientListState.status === "ready" && patients.length === 0 ? (
              <div className="inline-state">
                <p>No patients yet.</p>
                <span className="muted">Create a patient to begin a local retinal capture workflow.</span>
              </div>
            ) : null}
            {patients.map((patient) => (
              <button
                key={patient.id}
                type="button"
                className={`patient-card ${selectedPatientId === patient.id ? "active" : ""}`}
                onClick={() => {
                  setSelectedPatientId(patient.id);
                  setWorkspaceView("sessions");
                }}
              >
                <span className="patient-card-name">{patient.display_name}</span>
                <span className="patient-card-meta">
                  DOB {patient.date_of_birth}
                  {patient.gender_text ? ` • ${patient.gender_text}` : ""}
                  {patient.archived_at ? " • Archived" : ""}
                </span>
              </button>
            ))}
          </div>
        </section>

        {selectedPatient ? (
          <section className="panel">
            <div className="panel-header">
              <h2>Patient Details</h2>
            </div>
            <form className="stack" onSubmit={onSavePatient}>
              <label className="field-group">
                <span>First name</span>
                <input
                  className="text-input"
                  value={patientDraft.first_name}
                  onChange={(event) =>
                    setPatientDraft((current) => ({ ...current, first_name: event.target.value }))
                  }
                  required
                />
              </label>
              <label className="field-group">
                <span>Last name</span>
                <input
                  className="text-input"
                  value={patientDraft.last_name}
                  onChange={(event) =>
                    setPatientDraft((current) => ({ ...current, last_name: event.target.value }))
                  }
                  required
                />
              </label>
              <label className="field-group">
                <span>Date of birth</span>
                <input
                  className="text-input"
                  type="date"
                  value={patientDraft.date_of_birth}
                  onChange={(event) =>
                    setPatientDraft((current) => ({ ...current, date_of_birth: event.target.value }))
                  }
                  required
                />
              </label>
              <label className="field-group">
                <span>Gender</span>
                <select
                  className="text-input"
                  value={patientDraft.gender_text}
                  onChange={(event) =>
                    setPatientDraft((current) => ({ ...current, gender_text: event.target.value }))
                  }
                >
                  <option value="F">F</option>
                  <option value="M">M</option>
                  <option value="X">X</option>
                  <option value="">Unspecified</option>
                </select>
              </label>
              <div className="action-row">
                <button className="primary-button" type="submit">
                  Save patient details
                </button>
              </div>
            </form>
          </section>
        ) : null}

        {selectedPatient ? (
          <section className="panel">
            <div className="panel-header">
              <h2>Patient Status</h2>
            </div>
            <div className="stack">
              <p className="muted">
                {selectedPatient.archived_at
                  ? `Archived ${formatDateTime(selectedPatient.archived_at)}.`
                  : "This patient is active and shown in the default patient search."}
              </p>
              <div className="action-row">
                {selectedPatient.archived_at ? (
                  <button className="primary-button" type="button" onClick={() => void onUnarchivePatient()}>
                    Unarchive patient
                  </button>
                ) : archiveConfirmPatientId === selectedPatient.id ? (
                  <>
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void onConfirmArchivePatient()}
                    >
                      Confirm archive
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => setArchiveConfirmPatientId(null)}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button className="danger-button" type="button" onClick={() => void onArchivePatient()}>
                    Archive patient
                  </button>
                )}
              </div>
              {!selectedPatient.archived_at && archiveConfirmPatientId === selectedPatient.id ? (
                <span className="field-help">
                  Archiving hides this patient from the default search but keeps the record in the database.
                </span>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="panel">
          <div className="panel-header">
            <h2>New Patient</h2>
          </div>
          <form className="stack" onSubmit={onCreatePatient}>
            <label className="field-group">
              <span>First name</span>
              <input
                className="text-input"
                value={patientForm.first_name}
                placeholder="First name"
                onChange={(event) =>
                  setPatientForm((current) => ({ ...current, first_name: event.target.value }))
                }
                required
              />
            </label>
            <label className="field-group">
              <span>Last name</span>
              <input
                className="text-input"
                value={patientForm.last_name}
                placeholder="Last name"
                onChange={(event) =>
                  setPatientForm((current) => ({ ...current, last_name: event.target.value }))
                }
                required
              />
            </label>
            <label className="field-group">
              <span>Date of birth</span>
              <input
                className="text-input"
                type="date"
                value={patientForm.date_of_birth}
                onChange={(event) =>
                  setPatientForm((current) => ({ ...current, date_of_birth: event.target.value }))
                }
                required
              />
            </label>
            <label className="field-group">
              <span>Gender</span>
              <select
                className="text-input"
                value={patientForm.gender_text}
                onChange={(event) =>
                  setPatientForm((current) => ({ ...current, gender_text: event.target.value }))
                }
              >
                <option value="F">F</option>
                <option value="M">M</option>
                <option value="X">X</option>
                <option value="">Unspecified</option>
              </select>
            </label>
            <button className="primary-button" type="submit">
              Create patient
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Backups</h2>
          </div>
          <p className="muted">
            Export a full local backup or restore the app from a previously exported backup zip.
          </p>
          <div className="stack">
            <button className="ghost-button" type="button" onClick={() => void onExportBackup()}>
              Export backup
            </button>
            <button className="ghost-button" type="button" onClick={onChooseRestoreBackup}>
              Restore from backup
            </button>
            <input
              ref={restoreInputRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden-file-input"
              onChange={(event) => void onRestoreBackupSelected(event)}
            />
            <span className="field-help">
              Restore replaces the current local database and managed images with the selected backup.
            </span>
          </div>
        </section>
      </aside>

      <main className="workspace">
        <div className="workspace-header">
          <div>
            <p className="eyebrow">Patient record</p>
            <h2>{selectedPatient ? selectedPatient.display_name : "Select a patient"}</h2>
            <p className="muted">
              {selectedPatient
                ? `DOB ${selectedPatient.date_of_birth}${selectedPatient.gender_text ? ` • ${selectedPatient.gender_text}` : ""} • ${sessionCount} visit(s) • ${imageCount} image(s)`
                : "Create a patient on the left or choose one from the list."}
            </p>
          </div>
          <div className="workspace-statuses">
            <div className={`connection-banner ${connectionOffline ? "offline" : ""}`}>
              {connectionMessage}
            </div>
            {notice ? <div className={`notice-banner ${notice.tone}`}>{notice.message}</div> : null}
          </div>
        </div>

        <div className="workspace-switcher" role="tablist" aria-label="Workspace panels">
          <button
            type="button"
            className={`ghost-button ${workspaceView === "sessions" ? "active-chip" : ""}`}
            onClick={() => setWorkspaceView("sessions")}
          >
            Visits
          </button>
          <button
            type="button"
            className={`ghost-button ${workspaceView === "viewer" ? "active-chip" : ""}`}
            onClick={() => setWorkspaceView("viewer")}
          >
            Image viewer
          </button>
        </div>

        <div className="workspace-grid">
          <section className={`panel content-panel ${workspaceView === "viewer" ? "mobile-hidden" : ""}`}>
            <div className="panel-header">
              <h2>Visits</h2>
            </div>

            {selectedPatient ? (
              <>
                <form className="history-filter-form" onSubmit={onApplySessionFilters}>
                  <div className="panel-header">
                    <div>
                      <h3 className="section-heading">History Filters</h3>
                      <p className="muted">Narrow the visit timeline by date or eye side.</p>
                    </div>
                    <span className="session-count">
                      Showing {sessionCount} visit(s) • {imageCount} image(s)
                    </span>
                  </div>
                  <div className="filter-grid">
                    <label className="field-group">
                      <span>Date from</span>
                      <input
                        className="text-input"
                        type="date"
                        aria-label="History date from"
                        value={sessionFilters.session_date_from}
                        onChange={(event) =>
                          setSessionFilters((current) => ({
                            ...current,
                            session_date_from: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label className="field-group">
                      <span>Date to</span>
                      <input
                        className="text-input"
                        type="date"
                        aria-label="History date to"
                        value={sessionFilters.session_date_to}
                        onChange={(event) =>
                          setSessionFilters((current) => ({
                            ...current,
                            session_date_to: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label className="field-group">
                      <span>Laterality</span>
                      <select
                        className="text-input"
                        aria-label="History laterality"
                        value={sessionFilters.laterality}
                        onChange={(event) =>
                          setSessionFilters((current) => ({
                            ...current,
                            laterality: event.target.value,
                          }))
                        }
                      >
                        <option value="">All laterality</option>
                        <option value="left">Left eye</option>
                        <option value="right">Right eye</option>
                        <option value="both">Both</option>
                        <option value="unknown">Unknown</option>
                      </select>
                    </label>
                  </div>
                  <div className="filter-actions">
                    <button className="primary-button" type="submit">
                      Apply history filters
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => void onClearSessionFilters()}
                      disabled={!activeHistoryFilters}
                    >
                      Clear filters
                    </button>
                  </div>
                </form>

                <div className="section-divider">
                  <h3 className="section-heading">New Visit</h3>
                  <p className="muted">Create a visit before importing new retinal images.</p>
                </div>

                <form className="session-form" onSubmit={onCreateSession}>
                  <label className="field-group">
                    <span>Visit date</span>
                    <input
                      className="text-input"
                      type="date"
                      value={sessionForm.session_date}
                      onChange={(event) =>
                        setSessionForm((current) => ({ ...current, session_date: event.target.value }))
                      }
                      required
                    />
                  </label>
                  <label className="field-group">
                    <span>Operator name</span>
                    <input
                      className="text-input"
                      value={sessionForm.operator_name}
                      placeholder="Operator name"
                      onChange={(event) =>
                        setSessionForm((current) => ({ ...current, operator_name: event.target.value }))
                      }
                    />
                  </label>
                  <label className="field-group">
                    <span>Visit notes</span>
                    <textarea
                      className="text-input text-area"
                      value={sessionForm.notes}
                      placeholder="Visit notes"
                      onChange={(event) =>
                        setSessionForm((current) => ({ ...current, notes: event.target.value }))
                      }
                    />
                  </label>
                  <button className="primary-button" type="submit">
                    Create visit
                  </button>
                </form>

                <div className="section-divider">
                  <h3 className="section-heading">Visit History</h3>
                  <p className="muted">Review visits, imports, and previous retinal images.</p>
                </div>

                {patientDetailState.status === "loading" ? <p className="muted">Loading visits...</p> : null}
                {patientDetailState.status === "error" ? (
                  <div className="inline-state">
                    <p>{patientDetailState.message}</p>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => selectedPatientId && void refreshPatient(selectedPatientId)}
                    >
                      Retry patient detail
                    </button>
                  </div>
                ) : null}
                {patientDetailState.status === "ready" && selectedPatient.sessions.length === 0 ? (
                  <div className="inline-state">
                    <p>{activeHistoryFilters ? "No visits match the active filters." : "No visits yet."}</p>
                    <span className="muted">
                      {activeHistoryFilters
                        ? "Clear or adjust the filters to review more of the patient history."
                        : "Create one to start a bilateral capture workflow."}
                    </span>
                  </div>
                ) : null}

                <div className="session-list">
                  {selectedPatient.sessions.map((session) => {
                    const draft = sessionDrafts[session.id] ?? buildSessionDraft(session);
                    const uploads = sessionUploads[session.id] ?? initialEyeUploadForms();
                    const left = eyeImages(session, "left");
                    const right = eyeImages(session, "right");
                    const other = otherImages(session);

                    return (
                      <article key={session.id} className="session-card">
                        <div className="session-card-header">
                          <div>
                            <h3>{formatDate(session.session_date)}</h3>
                            <p className="muted">
                              {session.operator_name ? `${session.operator_name} • ` : ""}
                              {session.status}
                              {session.legacy_visit_id ? ` • Legacy visit ${session.legacy_visit_id}` : ""}
                            </p>
                          </div>
                          <span className="session-count">{session.images.length} image(s)</span>
                        </div>

                        <div className="subsection-intro">
                          <h4>Visit details</h4>
                          <p className="muted">
                            These notes stay with the visit. Image-specific notes are entered on each eye capture.
                          </p>
                        </div>

                        <form
                          className="session-metadata-form"
                          onSubmit={(event) => void onSaveSession(event, session.id)}
                        >
                          <div className="session-meta-grid">
                            <label className="field-group">
                              <span>Visit date</span>
                              <input
                                className="text-input"
                                type="date"
                                value={draft.session_date}
                                onChange={(event) =>
                                  updateSessionDraft(session.id, { session_date: event.target.value })
                                }
                                required
                              />
                            </label>
                            <label className="field-group">
                              <span>Operator name</span>
                              <input
                                className="text-input"
                                value={draft.operator_name}
                                placeholder="Operator name"
                                onChange={(event) =>
                                  updateSessionDraft(session.id, { operator_name: event.target.value })
                                }
                              />
                            </label>
                          </div>
                          <label className="field-group">
                            <span>Visit notes</span>
                            <textarea
                              className="text-input text-area"
                              value={draft.notes}
                              placeholder="Visit notes"
                              onChange={(event) => updateSessionDraft(session.id, { notes: event.target.value })}
                            />
                          </label>
                          <button className="ghost-button" type="submit">
                            Save visit details
                          </button>
                        </form>

                        <div className="subsection-intro">
                          <h4>Eye captures</h4>
                          <p className="muted">
                            Notes entered below apply to the imported image, not the overall visit.
                            Image metadata can be edited in the right-hand panel.
                          </p>
                        </div>

                        <div className="bilateral-grid">
                          {(["left", "right"] as EyeSide[]).map((eye) => {
                            const eyeUpload = uploads[eye];
                            const images = eye === "left" ? left : right;
                            return (
                              <section key={eye} className="eye-column">
                                <div className="eye-column-header">
                                  <h4>{eye === "left" ? "Left eye" : "Right eye"}</h4>
                                  <span className="badge subtle">{images.length} capture(s)</span>
                                </div>

                                <form
                                  className="upload-form"
                                  onSubmit={(event) => void onImportImage(event, session.id, eye)}
                                >
                                  <label className="field-group">
                                    <span>{eye === "left" ? "Left" : "Right"} image notes</span>
                                    <textarea
                                      className="text-input compact-text-area"
                                      value={eyeUpload.notes}
                                      placeholder={`Notes for the ${eye} eye image`}
                                      onChange={(event) =>
                                        updateEyeUpload(session.id, eye, { notes: event.target.value })
                                      }
                                    />
                                  </label>
                                  <input
                                    className="text-input file-input"
                                    type="file"
                                    accept="image/*"
                                    onChange={(event) =>
                                      updateEyeUpload(session.id, eye, {
                                        file: event.target.files?.[0] ?? null,
                                      })
                                    }
                                    required
                                  />
                                  <button className="primary-button" type="submit">
                                    Import {eye === "left" ? "left" : "right"} eye
                                  </button>
                                </form>

                                <div className="image-grid eye-image-grid">
                                  {images.length === 0 ? (
                                    <p className="muted">No {eye} eye captures yet.</p>
                                  ) : null}
                                  {images.map((image) => (
                                    <button
                                      key={image.id}
                                      type="button"
                                      className={`image-card ${selectedImage?.id === image.id ? "active" : ""}`}
                                      onClick={() => {
                                        setSelectedImage(image);
                                        setWorkspaceView("viewer");
                                      }}
                                    >
                                      <img
                                        src={imageThumbnailUrl(image.id)}
                                        alt={image.original_filename}
                                        loading="lazy"
                                      />
                                      <div className="image-card-body">
                                        <div className="badge-row">
                                          <span className="badge">{image.laterality}</span>
                                        </div>
                                        <strong>{image.original_filename}</strong>
                                        <span className="muted">{formatBytes(image.file_size_bytes)}</span>
                                      </div>
                                    </button>
                                  ))}
                                </div>
                              </section>
                            );
                          })}
                        </div>

                        {other.length > 0 ? (
                          <div className="supplemental-captures">
                            <div className="eye-column-header">
                              <h4>Other captures</h4>
                              <span className="badge subtle">{other.length}</span>
                            </div>
                            <div className="image-grid">
                              {other.map((image) => (
                                <button
                                  key={image.id}
                                  type="button"
                                  className={`image-card ${selectedImage?.id === image.id ? "active" : ""}`}
                                  onClick={() => {
                                    setSelectedImage(image);
                                    setWorkspaceView("viewer");
                                  }}
                                >
                                  <img
                                    src={imageThumbnailUrl(image.id)}
                                    alt={image.original_filename}
                                    loading="lazy"
                                  />
                                  <div className="image-card-body">
                                    <div className="badge-row">
                                      <span className="badge">{image.laterality}</span>
                                    </div>
                                    <strong>{image.original_filename}</strong>
                                  </div>
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              </>
            ) : (
              <p className="muted">Select a patient to browse or create visits.</p>
            )}
          </section>

          <section className={`panel viewer-panel ${workspaceView === "sessions" ? "mobile-hidden" : ""}`}>
            <div className="panel-header">
              <h2>Image Viewer</h2>
            </div>
            {selectedImage ? (
              <div className="viewer-stack">
                <img
                  className="viewer-image"
                  src={imageFileUrl(selectedImage.id)}
                  alt={selectedImage.original_filename}
                />
                <div className="viewer-actions">
                  <button className="ghost-button" type="button" onClick={() => void onOpenImageExternally()}>
                    Open in default viewer
                  </button>
                </div>
                <div className="viewer-meta">
                  <div className="badge-row">
                    <span className="badge">{selectedImage.laterality}</span>
                  </div>
                  <h3>{selectedImage.original_filename}</h3>
                  <p className="muted">
                    {formatBytes(selectedImage.file_size_bytes)}
                    {selectedImage.width_px && selectedImage.height_px
                      ? ` • ${selectedImage.width_px} × ${selectedImage.height_px}`
                      : ""}
                  </p>
                  <p className="muted">Imported {formatDateTime(selectedImage.imported_at)}</p>
                  {selectedImage.captured_at ? (
                    <p className="muted">Captured {formatDateTime(selectedImage.captured_at)}</p>
                  ) : null}
                </div>

                {historyImages.length > 0 ? (
                  <div className="viewer-history">
                    <div className="panel-header">
                      <div>
                        <h3>Filtered History</h3>
                        <p className="muted">
                          Quick review of the current patient timeline{activeHistoryFilters ? " with filters applied" : ""}.
                        </p>
                      </div>
                      <span className="session-count">{historyImages.length} image(s)</span>
                    </div>
                    <div className="history-strip" role="list" aria-label="Filtered image history">
                      {historyImages.map((image) => (
                        <button
                          key={image.id}
                          type="button"
                          role="listitem"
                          className={`history-thumb ${selectedImage.id === image.id ? "active" : ""}`}
                          onClick={() => setSelectedImage(image)}
                        >
                          <img src={imageThumbnailUrl(image.id)} alt={image.original_filename} loading="lazy" />
                          <span>{image.laterality}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                <form className="viewer-form" onSubmit={(event) => void onSaveImage(event)}>
                  <div className="subsection-intro subsection-intro-tight">
                    <h4>Selected image metadata</h4>
                    <p className="muted">
                      Changes here apply only to the selected image. Visit notes stay in the visit card on the left.
                    </p>
                  </div>
                  <div className="viewer-form-grid viewer-form-grid-single">
                    <label className="field-group">
                      <span>Eye side</span>
                      <select
                        className="text-input"
                        value={imageDrafts[selectedImage.id]?.laterality ?? selectedImage.laterality}
                        onChange={(event) =>
                          updateImageDraft(selectedImage.id, { laterality: event.target.value })
                        }
                      >
                        <option value="left">Left eye</option>
                        <option value="right">Right eye</option>
                        <option value="both">Both</option>
                        <option value="unknown">Unknown</option>
                      </select>
                    </label>
                  </div>
                  <label className="field-group">
                    <span>Capture time</span>
                    <input
                      className="text-input"
                      type="datetime-local"
                      value={imageDrafts[selectedImage.id]?.captured_at ?? ""}
                      placeholder=""
                      onChange={(event) =>
                        updateImageDraft(selectedImage.id, { captured_at: event.target.value })
                      }
                    />
                    <span className="field-help">
                      Optional. Leave blank if the exact capture time is unknown. Imported time is shown above separately.
                    </span>
                  </label>
                  <label className="field-group">
                    <span>Image notes</span>
                    <textarea
                      className="text-input text-area"
                      value={imageDrafts[selectedImage.id]?.notes ?? ""}
                      placeholder="Notes for this selected image"
                      onChange={(event) => updateImageDraft(selectedImage.id, { notes: event.target.value })}
                    />
                    <span className="field-help">These notes belong to the selected image, not the whole visit.</span>
                  </label>
                  <button className="primary-button" type="submit">
                    Save image metadata
                  </button>
                </form>
              </div>
            ) : (
              <p className="muted">
                Select an imported image to view it at full resolution and edit image-level metadata.
              </p>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
