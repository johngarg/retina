import { FormEvent, useEffect, useState } from "react";

import {
  createPatient,
  createSession,
  fetchHealth,
  fetchPatient,
  fetchPatients,
  imageFileUrl,
  imageThumbnailUrl,
  importImage,
  updateImage,
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
  image_type: string;
  notes: string;
  file: File | null;
};

type ImageEditForm = {
  laterality: string;
  image_type: string;
  captured_at: string;
  notes: string;
};

type EyeSide = "left" | "right";
type EyeUploadForms = Record<EyeSide, UploadForm>;
type BootState = "checking" | "starting" | "ready" | "error";

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
  image_type: "color_fundus",
  notes: "",
  file: null,
});

const initialEyeUploadForms = (): EyeUploadForms => ({
  left: makeUploadForm("left"),
  right: makeUploadForm("right"),
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
    image_type: image.image_type,
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

function eyeImages(session: StudySession, eye: EyeSide): RetinalImage[] {
  return session.images.filter((image) => image.laterality === eye);
}

function otherImages(session: StudySession): RetinalImage[] {
  return session.images.filter((image) => image.laterality !== "left" && image.laterality !== "right");
}

function App() {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [selectedPatient, setSelectedPatient] = useState<PatientDetail | null>(null);
  const [selectedImage, setSelectedImage] = useState<RetinalImage | null>(null);
  const [search, setSearch] = useState("");
  const [patientForm, setPatientForm] = useState<PatientForm>(initialPatientForm);
  const [sessionForm, setSessionForm] = useState<SessionForm>(initialSessionForm);
  const [sessionDrafts, setSessionDrafts] = useState<Record<string, SessionForm>>({});
  const [sessionUploads, setSessionUploads] = useState<Record<string, EyeUploadForms>>({});
  const [imageDrafts, setImageDrafts] = useState<Record<string, ImageEditForm>>({});
  const [isLoadingPatients, setIsLoadingPatients] = useState(true);
  const [isLoadingPatient, setIsLoadingPatient] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bootState, setBootState] = useState<BootState>("checking");
  const [bootMessage, setBootMessage] = useState("Checking backend availability...");

  async function refreshPatients(nextQuery = search, preferredPatientId?: string) {
    setIsLoadingPatients(true);
    setError(null);
    try {
      const result = await fetchPatients(nextQuery);
      setPatients(result);
      const nextSelectedId =
        preferredPatientId && result.some((patient) => patient.id === preferredPatientId)
          ? preferredPatientId
          : selectedPatientId && result.some((patient) => patient.id === selectedPatientId)
            ? selectedPatientId
            : result[0]?.id ?? null;
      setSelectedPatientId(nextSelectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load patients");
    } finally {
      setIsLoadingPatients(false);
    }
  }

  async function refreshPatient(patientId: string, preferredImageId?: string | null) {
    setIsLoadingPatient(true);
    try {
      const detail = await fetchPatient(patientId);
      setSelectedPatient(detail);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load patient detail");
    } finally {
      setIsLoadingPatient(false);
    }
  }

  async function bootstrapApp() {
    setBootState("checking");
    setBootMessage("Checking backend availability...");
    setError(null);

    if (await fetchHealth()) {
      setBootState("ready");
      await refreshPatients();
      return;
    }

    if (isTauriRuntime()) {
      setBootState("starting");
      setBootMessage("Starting the local API...");
      try {
        const result = await ensureBackendStarted();
        setBootMessage(result.detail);
      } catch (err) {
        setBootState("error");
        setBootMessage(err instanceof Error ? err.message : "Unable to start the backend process.");
        return;
      }
    } else {
      setBootState("error");
      setBootMessage("Backend is not running. Start the API on http://127.0.0.1:8000 and retry.");
      return;
    }

    const isHealthy = await waitForBackendHealth(fetchHealth, 40, 500);
    if (!isHealthy) {
      setBootState("error");
      setBootMessage("Backend did not become healthy in time. Check the desktop logs and retry.");
      return;
    }

    setBootState("ready");
    setBootMessage("Backend is ready.");
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
      return;
    }
    void refreshPatient(selectedPatientId);
  }, [bootState, selectedPatientId]);

  useEffect(() => {
    if (!selectedImage) {
      return;
    }
    setImageDrafts((current) => ({
      ...current,
      [selectedImage.id]: buildImageDraft(selectedImage),
    }));
  }, [selectedImage]);

  async function onCreatePatient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const created = await createPatient(patientForm);
      setPatientForm(initialPatientForm);
      await refreshPatients(search, created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create patient");
    }
  }

  async function onCreateSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPatientId) {
      return;
    }
    setError(null);
    try {
      const created = await createSession(selectedPatientId, sessionForm);
      setSessionForm(initialSessionForm());
      await refreshPatient(selectedPatientId);
      setSessionUploads((current) => ({ ...current, [created.id]: initialEyeUploadForms() }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create session");
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

    setError(null);
    try {
      await updateSession(sessionId, draft);
      await refreshPatient(selectedPatientId, selectedImage?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update session");
    }
  }

  async function onImportImage(event: FormEvent<HTMLFormElement>, sessionId: string, eye: EyeSide) {
    event.preventDefault();
    const upload = sessionUploads[sessionId]?.[eye] ?? makeUploadForm(eye);
    if (!upload.file || !selectedPatientId) {
      setError(`Choose a ${eye} eye image before importing`);
      return;
    }

    setError(null);
    try {
      await importImage(sessionId, { ...upload, laterality: eye, file: upload.file });
      setSessionUploads((current) => ({
        ...current,
        [sessionId]: {
          ...(current[sessionId] ?? initialEyeUploadForms()),
          [eye]: makeUploadForm(eye),
        },
      }));
      await refreshPatient(selectedPatientId);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to import ${eye} eye image`);
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

    setError(null);
    try {
      await updateImage(selectedImage.id, {
        laterality: draft.laterality,
        image_type: draft.image_type,
        captured_at: draft.captured_at || null,
        notes: draft.notes,
      });
      await refreshPatient(selectedPatientId, selectedImage.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update image metadata");
    }
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
          image_type: "color_fundus",
          captured_at: "",
          notes: "",
        }),
        ...next,
      },
    }));
  }

  if (bootState !== "ready") {
    return (
      <div className="startup-shell">
        <section className="startup-card">
          <p className="eyebrow">Milestone 1</p>
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
              Browser mode still expects the API to be started separately. Tauri mode will start it
              automatically.
            </p>
          ) : null}
        </section>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <p className="eyebrow">Local-first retinal workflow</p>
          <h1>Retina</h1>
          <p className="muted">
            Patients, sessions, and bilateral retinal capture flows rebuilt from the legacy app.
          </p>
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
            placeholder="Search by name or legacy ID"
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void refreshPatients(event.currentTarget.value);
              }
            }}
          />
          <div className="patient-list">
            {isLoadingPatients ? <p className="muted">Loading patients...</p> : null}
            {!isLoadingPatients && patients.length === 0 ? <p className="muted">No patients yet.</p> : null}
            {patients.map((patient) => (
              <button
                key={patient.id}
                type="button"
                className={`patient-card ${selectedPatientId === patient.id ? "active" : ""}`}
                onClick={() => setSelectedPatientId(patient.id)}
              >
                <span className="patient-card-name">{patient.display_name}</span>
                <span className="patient-card-meta">
                  DOB {patient.date_of_birth}
                  {patient.gender_text ? ` • ${patient.gender_text}` : ""}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>New Patient</h2>
          </div>
          <form className="stack" onSubmit={onCreatePatient}>
            <input
              className="text-input"
              value={patientForm.first_name}
              placeholder="First name"
              onChange={(event) => setPatientForm((current) => ({ ...current, first_name: event.target.value }))}
              required
            />
            <input
              className="text-input"
              value={patientForm.last_name}
              placeholder="Last name"
              onChange={(event) => setPatientForm((current) => ({ ...current, last_name: event.target.value }))}
              required
            />
            <input
              className="text-input"
              type="date"
              value={patientForm.date_of_birth}
              onChange={(event) =>
                setPatientForm((current) => ({ ...current, date_of_birth: event.target.value }))
              }
              required
            />
            <select
              className="text-input"
              value={patientForm.gender_text}
              onChange={(event) => setPatientForm((current) => ({ ...current, gender_text: event.target.value }))}
            >
              <option value="F">F</option>
              <option value="M">M</option>
              <option value="X">X</option>
              <option value="">Unspecified</option>
            </select>
            <button className="primary-button" type="submit">
              Create patient
            </button>
          </form>
        </section>
      </aside>

      <main className="workspace">
        <div className="workspace-header">
          <div>
            <p className="eyebrow">Session-centered workflow</p>
            <h2>{selectedPatient ? selectedPatient.display_name : "Select a patient"}</h2>
            <p className="muted">
              {selectedPatient
                ? `DOB ${selectedPatient.date_of_birth}${selectedPatient.gender_text ? ` • ${selectedPatient.gender_text}` : ""}`
                : "Create a patient on the left or choose one from the list."}
            </p>
          </div>
          {error ? <div className="error-banner">{error}</div> : null}
        </div>

        <div className="workspace-grid">
          <section className="panel content-panel">
            <div className="panel-header">
              <h2>Sessions</h2>
            </div>

            {selectedPatient ? (
              <>
                <form className="session-form" onSubmit={onCreateSession}>
                  <input
                    className="text-input"
                    type="date"
                    value={sessionForm.session_date}
                    onChange={(event) =>
                      setSessionForm((current) => ({ ...current, session_date: event.target.value }))
                    }
                    required
                  />
                  <input
                    className="text-input"
                    value={sessionForm.operator_name}
                    placeholder="Operator name"
                    onChange={(event) =>
                      setSessionForm((current) => ({ ...current, operator_name: event.target.value }))
                    }
                  />
                  <textarea
                    className="text-input text-area"
                    value={sessionForm.notes}
                    placeholder="Session notes"
                    onChange={(event) => setSessionForm((current) => ({ ...current, notes: event.target.value }))}
                  />
                  <button className="primary-button" type="submit">
                    Create session
                  </button>
                </form>

                {isLoadingPatient ? <p className="muted">Loading sessions...</p> : null}
                {!isLoadingPatient && selectedPatient.sessions.length === 0 ? (
                  <p className="muted">No sessions yet. Create one to start a bilateral capture session.</p>
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
                            </p>
                          </div>
                          <span className="session-count">{session.images.length} image(s)</span>
                        </div>

                        <form
                          className="session-metadata-form"
                          onSubmit={(event) => void onSaveSession(event, session.id)}
                        >
                          <div className="session-meta-grid">
                            <input
                              className="text-input"
                              type="date"
                              value={draft.session_date}
                              onChange={(event) =>
                                updateSessionDraft(session.id, { session_date: event.target.value })
                              }
                              required
                            />
                            <input
                              className="text-input"
                              value={draft.operator_name}
                              placeholder="Operator name"
                              onChange={(event) =>
                                updateSessionDraft(session.id, { operator_name: event.target.value })
                              }
                            />
                          </div>
                          <textarea
                            className="text-input text-area"
                            value={draft.notes}
                            placeholder="Session notes"
                            onChange={(event) => updateSessionDraft(session.id, { notes: event.target.value })}
                          />
                          <button className="ghost-button" type="submit">
                            Save session details
                          </button>
                        </form>

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
                                  <select
                                    className="text-input"
                                    value={eyeUpload.image_type}
                                    onChange={(event) =>
                                      updateEyeUpload(session.id, eye, { image_type: event.target.value })
                                    }
                                  >
                                    <option value="color_fundus">Color fundus</option>
                                    <option value="red_free">Red-free</option>
                                    <option value="fluorescein">Fluorescein</option>
                                    <option value="autofluorescence">Autofluorescence</option>
                                    <option value="other">Other</option>
                                  </select>
                                  <textarea
                                    className="text-input compact-text-area"
                                    value={eyeUpload.notes}
                                    placeholder={`${eye === "left" ? "Left" : "Right"} eye notes`}
                                    onChange={(event) =>
                                      updateEyeUpload(session.id, eye, { notes: event.target.value })
                                    }
                                  />
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
                                      onClick={() => setSelectedImage(image)}
                                    >
                                      <img
                                        src={imageThumbnailUrl(image.id)}
                                        alt={image.original_filename}
                                        loading="lazy"
                                      />
                                      <div className="image-card-body">
                                        <div className="badge-row">
                                          <span className="badge">{image.laterality}</span>
                                          <span className="badge subtle">{image.image_type}</span>
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
                                  onClick={() => setSelectedImage(image)}
                                >
                                  <img
                                    src={imageThumbnailUrl(image.id)}
                                    alt={image.original_filename}
                                    loading="lazy"
                                  />
                                  <div className="image-card-body">
                                    <div className="badge-row">
                                      <span className="badge">{image.laterality}</span>
                                      <span className="badge subtle">{image.image_type}</span>
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
              <p className="muted">Select a patient to browse or create sessions.</p>
            )}
          </section>

          <section className="panel viewer-panel">
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
                <div className="viewer-meta">
                  <div className="badge-row">
                    <span className="badge">{selectedImage.laterality}</span>
                    <span className="badge subtle">{selectedImage.image_type}</span>
                  </div>
                  <h3>{selectedImage.original_filename}</h3>
                  <p className="muted">
                    {formatBytes(selectedImage.file_size_bytes)}
                    {selectedImage.width_px && selectedImage.height_px
                      ? ` • ${selectedImage.width_px} × ${selectedImage.height_px}`
                      : ""}
                  </p>
                </div>

                <form className="viewer-form" onSubmit={(event) => void onSaveImage(event)}>
                  <div className="viewer-form-grid">
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
                    <select
                      className="text-input"
                      value={imageDrafts[selectedImage.id]?.image_type ?? selectedImage.image_type}
                      onChange={(event) =>
                        updateImageDraft(selectedImage.id, { image_type: event.target.value })
                      }
                    >
                      <option value="color_fundus">Color fundus</option>
                      <option value="red_free">Red-free</option>
                      <option value="fluorescein">Fluorescein</option>
                      <option value="autofluorescence">Autofluorescence</option>
                      <option value="oct">OCT</option>
                      <option value="external_photo">External photo</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <input
                    className="text-input"
                    type="datetime-local"
                    value={imageDrafts[selectedImage.id]?.captured_at ?? ""}
                    onChange={(event) =>
                      updateImageDraft(selectedImage.id, { captured_at: event.target.value })
                    }
                  />
                  <textarea
                    className="text-input text-area"
                    value={imageDrafts[selectedImage.id]?.notes ?? ""}
                    placeholder="Image notes"
                    onChange={(event) => updateImageDraft(selectedImage.id, { notes: event.target.value })}
                  />
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
