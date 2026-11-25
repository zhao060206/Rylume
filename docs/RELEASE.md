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

## Build environment

Build only in a dedicated virtual environment whose packages match
`licenses/python-packages.json`, the versions whose notices and corresponding
sources ship with the release. A general-purpose Python drifts: 5.0.0 was first
built in one that lacked MarkItDown and Magika and had older PyMuPDF and certifi.

```powershell
python -m venv E:\py-build
E:\py-build\Scripts\python.exe tools/build_constraints.py --write build-constraints.txt
E:\py-build\Scripts\python.exe -m pip install -r requirements-dev.txt -c build-constraints.txt
E:\py-build\Scripts\python.exe tools/build_constraints.py --check
powershell -File build_rylume.ps1 -Python E:\py-build\Scripts\python.exe
```

`build_rylume.ps1` runs the same check and stops when a version differs. When a
dependency changes, update `requirements.txt`, the license record and its notice
files together. Packages bundled indirectly (pyclipper through RapidOCR,
svgwrite through svgpathtools) need a license record too.

## Signing key

`update.json` is signed with the Ed25519 key matching `update_mirrors.PUBLIC_KEY`.
Keep it outside the repository and every archive, with an offline backup.

The key was replaced in 5.0.0 because the previous one was lost. Clients that
reach GitHub directly check the installer digest and updated normally; 4.12.x
clients that can only use a mirror verify the old key and have to install 5.0.0
by hand once. Losing the key again has the same cost, so treat a missing key as
a release blocker.

```powershell
python tools/prepare_update_manifest.py --archive out/release-X.Y.Z/Rylume-X.Y.Z-Windows-x64.zip --output out/release-X.Y.Z --notes-file out/release-X.Y.Z/release-notes.md --signing-key <key path outside the repository>
```

## Release archives

- Windows ZIP: `dist-rylume/Rylume` under a top folder `Rylume/`.
- Source ZIP: `git archive --format=zip --prefix=Rylume-X.Y.Z-source/ -o out/release-X.Y.Z/Rylume-X.Y.Z-source.zip vX.Y.Z`
  from the clean commit the installer was built from (the published 4.12.4
  source ZIP has exactly the same files).
- Dependency sources: unmodified source distributions of components whose license
  asks for them and that no older asset covers (currently certifi), with
  `README.txt` and `SOURCE-MANIFEST.json`.
- `prepare_update_manifest.py` writes `SHA256SUMS.txt` for the installer only;
  rewrite it to list all three ZIPs before uploading.

## Upgrade test

Extract the previous public Windows ZIP into a scratch folder and start it with
a fresh `--data-dir` and its window: the new version confirms its health from the
loaded page, so a run without a window rolls back. Call `/api/updates/check`,
`/api/updates/download` and `/api/updates/apply`. The test passes when the
restarted application reports the new version and `updates/apply/*/result.json`
says `completed`. Stop only processes started from the scratch folder.
