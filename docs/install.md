# Install Retina

These instructions are for end users installing a packaged release.

## macOS

1. Download the latest Retina macOS app package.
2. If it arrives as a `.zip`, unzip it.
3. Move `Retina.app` into `Applications`.
4. Open `Applications` and launch Retina.

If the app is not yet signed and notarized, macOS may warn that the app is from an unidentified developer. That is expected for pre-release or internal builds.

## Windows

1. Download the latest Retina installer `.exe`.
2. Run the installer.
3. Follow the installer prompts.
4. Launch Retina from the Start menu or desktop shortcut.

If the app is not yet code-signed, Windows SmartScreen may warn before launch. That is expected for pre-release or internal builds.

## What you do not need to install

You should not need to install:

- Python
- Node.js
- Rust
- SQLite

Those are only needed by developers building the app from source.

## First run

On first launch, Retina creates its local data directory automatically. Imported retinal images are copied into app-managed storage and remain available after restart.
