# Windows publication

Pushing source or publishing resource packs does not update the Windows
application. Each application release needs the complete Windows ZIP, matching
public source ZIP, dependency sources, SHA256SUMS.txt, update.json, and its
Ed25519 signature. Keep the private signing key outside the repository and all
release archives.

1. Write the current version's changelog, commit the source, and run the Python
   and JavaScript checks. Build with the pinned Windows environment.
2. Verify the embedded version and source, exercise the packaged application in
   an isolated user-data directory, and test upgrading a copy of the previous
   public binary. Never use a user's live installation as a test fixture.
3. Scan the packaged application and all final archives for private files and
   credentials. Sign the completed installer metadata with
   `tools/prepare_update_manifest.py`.
4. Create a draft application release tagged `vX.Y.Z`, upload all six files, and
   compare GitHub's uploaded sizes and digests with the local artifacts.
5. Publish the application release as Latest only after every file is present.
   Resource-pack releases must not become Latest application releases.
6. Run `python tools/verify_update_release.py --latest --artifacts PATH` and
   exercise the public channel using the previous client version. This gate
   must report the intended version, a valid signature, and the same installer
   bytes. Announce completion only after this passes.
