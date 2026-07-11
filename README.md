# Aether Extension Registry

This repository serves as the official, curated extension registry for the **[Aether Launcher](https://github.com/wayback09/Aether)**.

Aether relies on this registry to populate its in-app Extension Gallery and assign cryptographic-style trust tiers to extensions, ensuring users know exactly what they are installing.

## Trust Tiers

Every extension in this registry is assigned one of the following trust tiers:

- 🔵 **Official**: Developed and maintained directly by the Aether Team.
- 🟢 **Verified**: Personally reviewed by an Aether maintainer. The code has been thoroughly audited for security, performance, and stability.
- 🟣 **Community**: Passed automated checks and was merged into the registry via Pull Request, but has not received a manual code audit. Use with caution.

*(Note: Extensions installed locally from `.zip` files rather than through this registry are marked as 🟡 **Local** by the launcher).*

## Publishing Your Extension

To publish an extension to this registry:
1. Ensure your extension follows the [Extensions Guide](https://github.com/wayback09/Aether/blob/main/docs/EXTENSIONS.md).
2. Host your packaged `.zip` release on GitHub Releases (or another direct-download host).
3. Open a Pull Request adding your extension metadata to `index.json`. 

By default, new submissions will receive the `community` trust tier until they can be manually audited for the `verified` tier.

## Learn More

To learn more about the core launcher, how to build extensions, and the sandbox architecture, head over to the main [Aether repository](https://github.com/wayback09/Aether).
