import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError } from "./api";

const apiMocks = vi.hoisted(() => ({
  fetchHealth: vi.fn(),
  fetchPatients: vi.fn(),
  fetchPatient: vi.fn(),
  createPatient: vi.fn(),
  createSession: vi.fn(),
  updateSession: vi.fn(),
  importImage: vi.fn(),
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
    apiMocks.updateSession.mockReset();
    apiMocks.importImage.mockReset();
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
});
