# Releasing the Command Palette extension

Command Palette only loads extensions installed as signed MSIX packages. The free way to get
them signed is to publish through the Microsoft Store, which signs each package. The
Store-signed packages then go on a GitHub release, and the WinGet listing points at them.
That WinGet listing is what puts the extension in Command Palette's gallery.

Extension releases use `cmdpal-v*` tags (for example `cmdpal-v0.1.0`). The PyPI workflow
skips them.

## One-time setup

1. **Partner Center account** (done). Sign up at <https://storedeveloper.microsoft.com> as an
   individual developer, with a personal Microsoft account. It's free and needs photo ID.
2. **Reserve the name** (done: "marcfinder"). Go to Apps and games > New product > MSIX or
   PWA app. The `<DisplayName>` in the manifest must match a reserved name.
3. **Copy the identity** (done: `mikegsaunders.marcfinder`). Under Product management >
   Product identity, copy these three values into `MarcFinderExtension/Package.appxmanifest`:
   - `Package/Identity/Name` goes in `<Identity Name="...">`
   - `Package/Identity/Publisher` goes in `<Identity Publisher="...">`
   - `Package/Properties/PublisherDisplayName` goes in `<PublisherDisplayName>`
4. **Icons.** Replace the template placeholders in `MarcFinderExtension/Assets/` with real
   ones at the same sizes.
5. **WinGet tooling.** Run `winget install Microsoft.WingetCreate`.

## Each release

1. **Tag it.**
   ```powershell
   git tag cmdpal-v0.1.0
   git push origin cmdpal-v0.1.0
   ```
   The `cmdpal-release` workflow builds unsigned x64 and ARM64 `.msix` files and attaches them
   to a **draft** release. The version in the package comes from the tag.

2. **Submit to the Store.** In Partner Center, start a new submission and upload both `.msix`
   files from the draft release. In Notes for certification, say that it needs PowerToys
   with Command Palette, and give test steps: open Command Palette with Win+Alt+Space, run
   MARC lookup, type `245`. Certification usually takes 1-3 business days.

3. **Swap in the signed packages.** After certification, download the Store-signed packages
   from Partner Center. On the draft release, replace the unsigned `.msix` files with the
   signed ones, then publish the release.

4. **Update WinGet.**
   - First release:
     ```powershell
     wingetcreate new <x64 .msix URL> <arm64 .msix URL>
     ```
     Use package identifier `mikegsaunders.marcfinder`. Before submitting,
     add this to the `.locale.en-US.yaml` file:
     ```yaml
     Tags:
     - windows-commandpalette-extension
     ```
     Without that tag the extension won't show in the Command Palette gallery.
   - Later releases:
     ```powershell
     wingetcreate update mikegsaunders.marcfinder --version 0.1.1 --urls <x64 URL> <arm64 URL> --submit
     ```
   WinGet's checks and review usually take a few days.

No dependency entries are needed, because the packages include their own .NET runtime.
