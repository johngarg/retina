# macOS Signing And Notarization

This document describes the minimum remaining work to make Retina installable on macOS without terminal commands.

## Current status

What works now:

- local macOS app bundle builds
- local macOS app bundle runs when launched directly on the build machine

What does not work yet for normal users:

- a downloaded `Retina.app.zip` is quarantined by macOS
- unsigned builds may be shown as damaged or blocked by Gatekeeper
- users should not be asked to run `xattr` commands

This means the remaining blocker is macOS trust and distribution, not the app runtime itself.

## Official references

- Tauri macOS bundle documentation: https://v2.tauri.app/distribute/macos-application-bundle/
- Tauri macOS signing documentation: https://tauri.app/distribute/sign/macos/
- Apple notarization documentation: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution

## What needs to be signed

At minimum:

- `Retina.app`
- the bundled `retina-api` sidecar executable

Tauri can handle signing during the build when the expected Apple signing environment variables are present.

## GitHub Actions secrets

The workflow is now prepared to sign and notarize macOS tagged builds if these secrets are added to the repository:

- `APPLE_CERTIFICATE`
  Base64-encoded `.p12` Developer ID Application certificate
- `APPLE_CERTIFICATE_PASSWORD`
  Password for the exported `.p12`
- `APPLE_SIGNING_IDENTITY`
  The Developer ID Application identity name from Keychain Access
- `APPLE_API_ISSUER`
  App Store Connect API issuer ID
- `APPLE_API_KEY`
  App Store Connect API key ID
- `APPLE_API_KEY_P8`
  The contents of the `.p8` App Store Connect API key

## Suggested setup

### 1. Apple Developer prerequisites

You need:

- an Apple Developer account
- a `Developer ID Application` certificate
- an App Store Connect API key for notarization

### 2. Export the signing certificate

From Keychain Access on macOS:

1. Export the `Developer ID Application` certificate as a `.p12`
2. Protect it with a password
3. Base64-encode the `.p12`
4. Store that value in the `APPLE_CERTIFICATE` GitHub secret

### 3. Add the notarization key

Store the following in GitHub secrets:

- `APPLE_API_ISSUER`
- `APPLE_API_KEY`
- `APPLE_API_KEY_P8`

The workflow writes the `.p8` contents to a temporary file and passes the path to Tauri during the tagged macOS build.

## How the workflow behaves

Current behavior:

- untagged builds remain unsigned test builds
- tagged macOS builds attempt signing and notarization if the required Apple secrets are present
- if Apple secrets are absent, tagged macOS builds still build, but remain unsigned

## Local verification commands

After building a macOS app bundle locally, verify it with:

```bash
codesign --verify --deep --strict --verbose=2 apps/desktop/src-tauri/target/release/bundle/macos/Retina.app
spctl --assess -vv apps/desktop/src-tauri/target/release/bundle/macos/Retina.app
```

If signing and notarization are correct, these checks should pass without requiring quarantine removal.

## Expected end state

The end goal is:

1. user downloads the release asset
2. user unzips or opens it normally
3. user launches Retina from Finder or Applications
4. macOS does not require `xattr`, terminal commands, or Gatekeeper bypass steps
