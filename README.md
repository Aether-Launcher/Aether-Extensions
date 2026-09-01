# Aether Extension Registry

<p align="center">
  <a href="https://discord.gg/pQc9NnGhpG">
    <img src="https://img.shields.io/badge/discord-Join%20our%20Discord-5865F2?logo=discord&logoColor=white&style=for-the-badge" alt="Discord">
  </a>
</p>

This repository is the official, curated extension registry for the **[Aether Launcher](https://github.com/Aether-Launcher/Aether)**.

Aether uses this registry to populate its in-app Extension Gallery and assign trust tiers to extensions, so users always know what they're installing.

---

## Trust Tiers

Every extension in this registry is assigned one of the following trust tiers:

- 🔵 **Official** — Developed and maintained directly by the Aether Team.
- 🟢 **Verified** — Personally reviewed by an Aether maintainer. Code has been thoroughly audited for security, performance, and stability.
- 🟣 **Community** — Passed automated checks and merged via Pull Request, but has not received a full manual audit. Use with caution.

*(Extensions installed locally from `.aex` files rather than through this registry are marked 🟡 **Local** by the launcher.)*

---

## Version Compatibility

Extensions may declare a `minLauncherVersion` field in their registry entry (and in their `manifest.json`):

```json
{
  "id": "my-extension",
  "minLauncherVersion": "v1.2.0"
}
```

When set, the Aether Gallery will automatically show an **⚠ Requires Aether vX.Y.Z+** badge and block installation for users on older launcher versions, preventing silent failures.

---

## Publishing Your Extension

To publish an extension to this registry:

1. Build your extension following the [Extensions Guide](https://github.com/Aether-Launcher/Aether/blob/main/docs/EXTENSIONS.md).
2. Use the [Aether CLI](https://github.com/Aether-Launcher/Aether-Cli) to validate and package it into a `.aex` file:
   ```bash
   aether-cli validate
   aether-cli build
   # → your-extension-1.0.0.aex
   ```
3. Open a Pull Request to this repository that includes **both**:
   - Your packaged **`.aex` file** added to the root of this repo
   - An entry for your extension added to **[`index.json`](index.json)**

**Example `index.json` entry:**

```json
{
  "id": "your-extension-id",
  "name": "Your Extension",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "What your extension does.",
  "url": "https://raw.githubusercontent.com/Aether-Launcher/Aether-Extensions/main/your-extension-1.0.0.aex",
  "trust": "community",
  "minLauncherVersion": "v1.0.0"
}
```

> The `url` field must point to the raw GitHub URL of the `.aex` file you included in the same PR. Do not link to external hosts.

Community submissions must include a `repository` field pointing to your extension's public GitHub repository. The AetherBot uses it to verify ownership via an `aether-verify.txt` commit token.

---

## Licensing

Extensions distributed through this registry are subject to the **[Aether Extension API License](https://github.com/Aether-Launcher/Aether-SDK/blob/main/LICENSE)**. Key points:

- ✅ Closed-source extensions are permitted
- ✅ You retain ownership of your extension's code
- ✅ Aether reviews all extensions before Gallery listing
- ❌ Extensions may not be distributed outside approved channels without written permission from Aether

By submitting a Pull Request to this registry you confirm that your extension complies with the Aether Extension API License.

---

## Learn More

- [Aether Launcher](https://github.com/Aether-Launcher/Aether) — the core launcher
- [Aether SDK](https://github.com/Aether-Launcher/Aether-SDK) — TypeScript types & helpers (`@aethermc/sdk`)
- [Aether CLI](https://github.com/Aether-Launcher/Aether-Cli) — scaffold, validate, and build extensions
