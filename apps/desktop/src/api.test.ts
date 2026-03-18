import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createPatient, describeApiError, fetchHealth, fetchPatient, fetchPatients } from "./api";

vi.mock("./tauri", () => ({
  isTauriRuntime: () => false,
}));

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("wraps network failures in an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    await expect(
      createPatient({
        first_name: "Ada",
        last_name: "Lovelace",
        date_of_birth: "1815-12-10",
        gender_text: "F",
      }),
    ).rejects.toMatchObject({
      name: "ApiError",
      kind: "network",
    });
  });

  it("returns structured health failure details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Backend unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const result = await fetchHealth();

    expect(result.ok).toBe(false);
    expect(result.error).toBeInstanceOf(ApiError);
    expect(result.error?.status).toBe(503);
  });

  it("maps network errors to actionable messages", () => {
    const error = new ApiError({
      kind: "network",
      detail: "Unable to reach the local API.",
      retryable: true,
    });

    expect(describeApiError(error, "Unable to load patients")).toContain(
      "Check that the local API is running",
    );
  });

  it("builds patient filter query strings for filtered detail requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
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
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchPatient("patient-1", {
      session_date_from: "2026-03-01",
      session_date_to: "2026-03-31",
      laterality: "left",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/patients/patient-1?session_date_from=2026-03-01&session_date_to=2026-03-31&laterality=left",
      expect.any(Object),
    );
  });

  it("includes the default patient list limit in list requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchPatients();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/patients?limit=100",
      expect.any(Object),
    );
  });
});
