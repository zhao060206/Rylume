# Local configuration and release security

Never commit API keys, model configuration, task histories, logs or `.env` files. Keep credentials outside the source checkout and use `config.example.json` as the template. The application's default data directory is `%LOCALAPPDATA%/CellFigureStudio`.

Release preparation uses a new allowlisted source tree and a fresh Git history. Source files, packaged files, decompressed PyInstaller modules and final ZIP members are scanned for known developer credentials and common credential formats. Scans are an additional check, not a reason to publish local data directories.

Report security issues through a private GitHub security advisory for this repository. Do not include working credentials in public issues. If a credential has already been exposed, revoke it with its provider.
