# Distribution

This document is for maintainers packaging Retina for real users.

## Target outcome

The minimum acceptable release flow is:

- macOS: downloadable `Retina.app` bundle, typically shipped as a zip
- Windows: downloadable NSIS installer `.exe`
- both builds include the bundled Python sidecar backend
- users do not need Python, Node, Rust, or terminal commands

## Build prerequisites

### Common

- Node.js 20+
- Rust toolchain via `rustup`
- Python 3.11+
- `uv`

### macOS maintainer machine

- Xcode Command Line Tools
- Apple Developer account and Developer ID certificate for signed releases
- notarization credentials for broad distribution

### Windows maintainer machine

- Microsoft Visual Studio Build Tools with C++ workload
- WebView2 runtime available on the target machine
- code-signing certificate for broad distribution

## Local packaging commands

### macOS

```bash
cd apps/api
uv sync --extra dev

cd ../desktop
npm ci
npm run build:desktop:macos
```

Expected artifact:

- `apps/desktop/src-tauri/target/release/bundle/macos/Retina.app`

Optional DMG attempt:

```bash
cd apps/desktop
npm run build:desktop:macos:dmg
```

The DMG path is a packaging polish step, not the baseline release path. Use it only after validating it on a clean macOS machine.

### Windows

Run on a real Windows machine:

```powershell
cd apps/api
uv sync --extra dev

cd ../desktop
npm ci
npm run build:desktop:windows
```

Expected artifacts:

- `apps/desktop/src-tauri/target/release/bundle/nsis/*.exe`

## What is already bundled

Desktop release builds include:

- the React frontend
- the Tauri shell
- the bundled FastAPI sidecar
- the SQLite database created on first launch
- managed image and thumbnail storage inside the app data directory

## Release checklist

1. Run backend and frontend tests.
2. Build the macOS app bundle on macOS.
3. Build the Windows artifact on Windows.
4. Install each artifact on a clean machine or VM.
5. Confirm first launch starts the backend automatically.
6. Confirm patient/session/image data persists after restart.
7. Confirm an imported image opens in the system image viewer.
8. Generate a backup zip and confirm it contains `app.db`, originals, thumbnails, and `manifest.json`.
9. If distributing outside a small trusted group, sign the binaries.
10. For macOS public distribution, notarize the shipped app or DMG artifact.

## Code signing and notarization

The app can be tested unsigned, but that is not acceptable for broad real-world distribution.

### macOS

Minimum acceptable public distribution:

- sign `Retina.app` with a Developer ID Application certificate
- sign any bundled sidecar binaries
- notarize the final app or DMG
- staple the notarization ticket to the shipped artifact

Without this, users should expect Gatekeeper warnings and a more awkward install flow.

For the bare minimum internal-release path, a zipped `Retina.app` is acceptable. DMG creation can remain optional until the app is signed and notarized.

### Windows

Minimum acceptable public distribution:

- sign the NSIS installer and installed executable with an Authenticode certificate

Without this, users should expect SmartScreen warnings.

## CI role

The CI workflow is intended to provide:

- repeatable packaging commands on macOS and Windows
- artifact generation on every tagged release or manual run
- early detection of packaging regressions

CI build success is not a substitute for installer testing on clean machines.
