import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError } from "./api";

const apiMocks = vi.hoisted(() => ({
  fetchHealth: vi.fn(),
  fetchPatients: vi.fn(),
  fetchPatient: vi.fn(),
  createPatient: vi.fn(),
  createSession: vi.fn(),
  exportBackup: vi.fn(),
  updateSession: vi.fn(),
  importImage: vi.fn(),
  openImageExternally: vi.fn(),
  restoreBackup: vi.fn(),
  updateImage: vi.fn(),
  imageFileUrl: vi.fn((imageId: string) => `/images/${imageId}/file`),
  imageThumbnailUrl: vi.fn((imageId: string) => `/images/${imageId}/thumbnail`),
}));

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    ...apiMocks,
  };
});

vi.mock("./tauri", () => ({
  ensureBackendStarted: vi.fn(),
  isTauriRuntime: vi.fn(() => false),
  waitForBackendHealth: vi.fn(),
}));

describe("App", () => {
  beforeEach(() => {
    apiMocks.fetchHealth.mockReset();
    apiMocks.fetchPatients.mockReset();
    apiMocks.fetchPatient.mockReset();
    apiMocks.createPatient.mockReset();
    apiMocks.createSession.mockReset();
    apiMocks.exportBackup.mockReset();
    apiMocks.updateSession.mockReset();
    apiMocks.importImage.mockReset();
    apiMocks.openImageExternally.mockReset();
    apiMocks.restoreBackup.mockReset();
    apiMocks.updateImage.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows an actionable startup message when the backend is offline in browser mode", async () => {
    apiMocks.fetchHealth.mockResolvedValue({
      ok: false,
      error: new ApiError({
        kind: "network",
        detail: "Unable to reach the local API.",
        retryable: true,
      }),
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Backend is not running/i)).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /Retry startup/i })).toBeInTheDocument();
  });

  it("shows a patient-list retry state instead of a generic request failure", async () => {
    apiMocks.fetchHealth.mockResolvedValue({ ok: true, error: null });
    apiMocks.fetchPatients.mockRejectedValue(
      new ApiError({
        kind: "network",
        detail: "Unable to reach the local API.",
        retryable: true,
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Unable to load patients/i)).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /Retry patient list/i })).toBeInTheDocument();
    expect(screen.queryByText(/request failed/i)).not.toBeInTheDocument();
  });

  it("applies history filters through the patient detail request and shows an empty filtered state", async () => {
    apiMocks.fetchHealth.mockResolvedValue({ ok: true, error: null });
    apiMocks.fetchPatients.mockResolvedValue([
      {
        id: "patient-1",
        legacy_patient_id: null,
        first_name: "Ada",
        last_name: "Lovelace",
        display_name: "Lovelace, Ada",
        date_of_birth: "1815-12-10",
        gender_text: "F",
        archived_at: null,
        created_at: "2026-03-18T00:00:00Z",
        updated_at: "2026-03-18T00:00:00Z",
      },
    ]);
    apiMocks.fetchPatient
      .mockResolvedValueOnce({
        id: "patient-1",
        legacy_patient_id: null,
        first_name: "Ada",
        last_name: "Lovelace",
        display_name: "Lovelace, Ada",
        date_of_birth: "1815-12-10",
        gender_text: "F",
        archived_at: null,
        created_at: "2026-03-18T00:00:00Z",
        updated_at: "2026-03-18T00:00:00Z",
        sessions: [
          {
            id: "session-1",
            patient_id: "patient-1",
            session_date: "2026-03-10",
            captured_at: null,
            operator_name: "Operator One",
            status: "completed",
            source: "filesystem_import",
            notes: "Session note",
            created_at: "2026-03-18T00:00:00Z",
            updated_at: "2026-03-18T00:00:00Z",
            images: [
              {
                id: "image-1",
                session_id: "session-1",
                patient_id: "patient-1",
                laterality: "left",
                image_type: "color_fundus",
                captured_at: null,
                imported_at: "2026-03-18T00:00:00Z",
                original_filename: "left-eye.png",
                stored_filename: "stored-left.png",
                file_size_bytes: 1024,
                width_px: 100,
                height_px: 100,
                thumbnail_width_px: 100,
                thumbnail_height_px: 100,
                notes: null,
                legacy_visit_id: null,
                thumbnail_relpath: "images/thumbnail/left-eye.png",
              },
            ],
          },
        ],
      })
      .mockResolvedValueOnce({
        id: "patient-1",
        legacy_patient_id: null,
        first_name: "Ada",
        last_name: "Lovelace",
        display_name: "Lovelace, Ada",
        date_of_birth: "1815-12-10",
        gender_text: "F",
        archived_at: null,
        created_at: "2026-03-18T00:00:00Z",
        updated_at: "2026-03-18T00:00:00Z",
        sessions: [],
      });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 visit\(s\)/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/These notes stay with the visit/i)).toBeInTheDocument();
    expect(screen.getByText(/Optional. Leave blank if the exact capture time is unknown/i)).toBeInTheDocument();
    expect(screen.getByText(/^Imported /i)).toBeInTheDocument();
    expect(screen.queryByText(/Captured/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/History laterality/i), {
      target: { value: "right" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Apply history filters/i }));

    await waitFor(() => {
      expect(apiMocks.fetchPatient).toHaveBeenLastCalledWith("patient-1", {
        laterality: "right",
        session_date_from: undefined,
        session_date_to: undefined,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/No visits match the active filters/i)).toBeInTheDocument();
    });
  });
});
