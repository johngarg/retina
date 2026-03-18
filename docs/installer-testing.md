# Installer Testing

This checklist is the minimum validation for a release candidate.

## Test environments

Use fresh machines or clean VMs:

- macOS: one recent Apple Silicon machine or VM
- Windows: one recent Windows 11 machine or VM

Avoid validating only on the maintainer's development machine.

## Install test

1. Download the packaged artifact.
2. Install it without using a terminal.
3. Launch the app from the normal OS entry point:
   - macOS: Applications after unzipping or DMG drag-install result
   - Windows: Start menu shortcut after NSIS install
4. Confirm the app opens without the user manually starting the backend.

## First-launch behavior

1. Wait for the startup screen to resolve.
2. Confirm the main workflow loads rather than showing API connection errors.
3. Create a patient.
4. Create a visit.
5. Import one left-eye image and one right-eye image.
6. Confirm thumbnails render.
7. Open one image in the system default viewer.

## Persistence

1. Quit the app fully.
2. Reopen the app.
3. Confirm the created patient, visit, and images are still present.

## Operational checks

1. Create a backup from the CLI or any future UI wrapper.
2. Confirm the backup zip exists.
3. Inspect the zip contents and confirm:
   - `app.db`
   - `images/originals/...`
   - `images/thumbnails/...`
   - `manifest.json`

## Platform-specific checks

### macOS

1. Confirm `Retina.app` can be moved into `/Applications`.
2. Confirm the icon is correct in Finder and Dock.
3. If unsigned, document the expected Gatekeeper warning.
4. If signed/notarized, confirm no Gatekeeper bypass steps are required.

### Windows

1. Confirm the installer creates the expected shortcuts.
2. Confirm the app launches from the Start menu.
3. If unsigned, document the expected SmartScreen warning.
4. If signed, confirm the warning no longer appears or is materially reduced.

## Failure logging

When a release candidate fails installer testing, record:

- OS and version
- artifact name
- exact install step that failed
- whether the failure is packaging, startup, persistence, or viewer integration
- screenshots if the issue is OS warning or installer UI related
