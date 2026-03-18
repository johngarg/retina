import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const desktopDir = path.resolve(__dirname, "..");
const apiDir = path.resolve(desktopDir, "../api");
const scriptPath = path.join(apiDir, "scripts", "build_sidecar.py");
const pythonCandidates = process.platform === "win32"
  ? [
      path.join(apiDir, ".venv", "Scripts", "python.exe"),
      path.join(apiDir, ".venv", "python.exe"),
    ]
  : [path.join(apiDir, ".venv", "bin", "python")];

const pythonPath = pythonCandidates.find((candidate) => existsSync(candidate));

if (!pythonPath) {
  const expectedPaths = pythonCandidates.join(", ");
  console.error(
    `Could not find the API virtualenv Python interpreter. Checked: ${expectedPaths}. Run \`uv sync --extra dev\` in apps/api first.`,
  );
  process.exit(1);
}

const result = spawnSync(pythonPath, [scriptPath], {
  cwd: apiDir,
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
