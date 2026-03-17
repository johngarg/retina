import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createPatient, describeApiError, fetchHealth } from "./api";

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
});
