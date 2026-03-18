import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const nextVersion = process.argv[2];

if (!nextVersion || !/^\d+\.\d+\.\d+([-.][A-Za-z0-9.]+)?$/.test(nextVersion)) {
  console.error("Usage: node scripts/sync-version.mjs <version>");
  process.exit(1);
}

function replaceInFile(filePath, replacer) {
  const original = fs.readFileSync(filePath, "utf8");
  const updated = replacer(original);
  if (updated === original) {
    throw new Error(`No version field was updated in ${filePath}`);
  }
  fs.writeFileSync(filePath, updated);
}

function updateJsonVersion(filePath, mutator) {
  const original = fs.readFileSync(filePath, "utf8");
  const parsed = JSON.parse(original);
  mutator(parsed);
  const updated = `${JSON.stringify(parsed, null, 2)}\n`;
  if (updated === original) {
    throw new Error(`No version field was updated in ${filePath}`);
  }
  fs.writeFileSync(filePath, updated);
}

fs.writeFileSync(path.join(repoRoot, "VERSION"), `${nextVersion}\n`);

replaceInFile(path.join(repoRoot, "apps", "api", "pyproject.toml"), (content) =>
  content.replace(/^version = ".*"$/m, `version = "${nextVersion}"`),
);

updateJsonVersion(path.join(repoRoot, "apps", "desktop", "package.json"), (parsed) => {
  parsed.version = nextVersion;
});

updateJsonVersion(path.join(repoRoot, "apps", "desktop", "package-lock.json"), (parsed) => {
  parsed.version = nextVersion;
  if (parsed.packages?.[""]) {
    parsed.packages[""].version = nextVersion;
  }
});

replaceInFile(path.join(repoRoot, "apps", "desktop", "src-tauri", "Cargo.toml"), (content) =>
  content.replace(/^version = ".*"$/m, `version = "${nextVersion}"`),
);

updateJsonVersion(path.join(repoRoot, "apps", "desktop", "src-tauri", "tauri.conf.json"), (parsed) => {
  parsed.version = nextVersion;
});

console.log(`Synced project version to ${nextVersion}`);
