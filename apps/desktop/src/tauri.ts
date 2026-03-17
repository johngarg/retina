declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export type BackendStartResult = {
  status: string;
  detail: string;
  mode: string;
};

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && typeof window.__TAURI_INTERNALS__ !== "undefined";
}

export async function ensureBackendStarted(): Promise<BackendStartResult> {
  if (!isTauriRuntime()) {
    return {
      status: "external",
      detail: "Non-Tauri runtime detected.",
      mode: "web",
    };
  }

  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<BackendStartResult>("ensure_backend_started");
}

export async function waitForBackendHealth(
  checkHealth: () => Promise<boolean>,
  attempts = 30,
  delayMs = 500,
): Promise<boolean> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await checkHealth()) {
      return true;
    }

    await new Promise((resolve) => {
      window.setTimeout(resolve, delayMs);
    });
  }

  return false;
}
