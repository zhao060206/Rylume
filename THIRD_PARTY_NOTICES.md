# Third-party notices

Rylume's original code is distributed under AGPL-3.0-only. The following components retain their own licenses. Inclusion in this project does not transfer their authorship to Rylume.

## Scientific artwork

Optional discipline packs under `resource-packs/` record per-asset source and license information in their manifests. The 2.2.0 artwork imports use ScanSci SVG (CC BY 4.0) and Material Design Icons (Apache-2.0); source revisions and modification notes are retained per asset. Cached upstream artwork under `assets/online-sources/` retains its original authorship and license. Application and generator code retain the project's AGPL license.

Curated Bioicons artwork has per-asset author, source URL, original digest, license and modification notes in `assets/bioicons/manifest.json` and `assets/bioicons/ATTRIBUTION.md`. Original SVG files are retained as `assets/bioicons/*.original.svg`; editable conversions are under `ui/library`. Licenses include CC BY 3.0, CC BY 4.0 and CC0 as specified per entry. Attribution must be retained where required; exported figures include credit sidecars.

The 4.5 expansion uses the same individually licensed upstream Bioicons revision `d29e766ea7580b8063c4f47b29e872db40a4d979`, verified against GitHub's tree. The offline import tool uses CairoSVG 2.9.1 (LGPL-3.0-or-later) for visual validation during development; CairoSVG is not part of the desktop runtime. Per-file modification notes describe conversion checks, which do not certify scientific meaning.

Third-party paper/reference images are deliberately excluded. Links in the reference catalog confer no license to redistribute the linked figures.

## MIT-licensed compatibility code

`vendor/client.py`, `vendor/credentials.py`, and `vendor/postprocess.py` originate from [yrui-cmd/cell_cns_figure](https://github.com/yrui-cmd/cell_cns_figure). Their MIT copyright and full permission notice are preserved in `licenses/cell_cns_figure-MIT.txt`. The application uses the local postprocessor compatibility layer; no customer credentials are distributed.

## PyMuPDF and MuPDF

The Windows release uses PyMuPDF 1.28.2 with MuPDF 1.28.2, Copyright Artifex Software and contributors, under GNU Affero General Public License v3. The full AGPL text is in `LICENSE`; matching PyMuPDF and MuPDF source archives, licensing and build instructions are separate release assets. Upstream: https://github.com/pymupdf/PyMuPDF and https://mupdf.com/.

## Local document conversion

Microsoft MarkItDown 0.1.9, Markdownify and openpyxl retain their MIT licenses. Mammoth and Cobble are BSD-2-Clause; Magika is Apache-2.0; PDFMiner.six and pdfplumber are MIT; DefusedXML uses the PSF license. Beautiful Soup and PDFium retain their upstream notices. Full notices and installed versions are included under `licenses/python-packages/`. LibreOffice is an optional separately installed system program and is not bundled.

Document figure planning uses an original Rylume prompt inspired by the public planning and faithfulness approaches in PaperBanana (dwzhu-pku, Apache-2.0; llmsresearch, MIT) and Paper2Any (Apache-2.0). Source links and adaptations are recorded in `docs/DOCUMENT-ASSISTANT-4.0.md`; their prompt files are not redistributed as application code.

## Python and packaged libraries

`licenses/Python-LICENSE.txt` contains Python's license. `licenses/python-packages.json` records installed package versions and copied notices, with full license files under `licenses/python-packages/`. The binary retains additional upstream notices shipped with its libraries, including NumPy/OpenBLAS, OpenCV, ONNX Runtime, pythonnet, pywebview and vtracer.

WebView2 Runtime and .NET are system prerequisites, not bundled Microsoft installers. Their licenses are provided by their respective vendors.

## GEOS and certifi corresponding source

The packaged Shapely 2.1.2 links dynamically to GEOS 3.13.1 (LGPL-2.1-or-later).
certifi 2026.10.23 is under MPL-2.0; its unmodified source is included in the
4.0.0 dependency-sources release asset. The unchanged PyMuPDF/MuPDF 1.28.2 and
GEOS 3.13.1 sources remain available in the [3.0.0 dependency-sources asset](https://github.com/zhao060206/Rylume/releases/download/v3.0.0/Rylume-3.0.0-dependency-sources.zip).
The GEOS license and replacement shared
libraries remain under `_internal/shapely.libs`; Rylume does not restrict the
replacement or debugging of those libraries as permitted by the LGPL.
# Source-matched artwork in 4.8.0

New discipline assets retain the original author, pinned source URL, source filename, licence and modification notes in each pack's manifest and LICENSE.txt. Tabler and Phosphor MIT notices and the Lucide ISC notice are included under licenses/artwork. Creative Commons and public-domain assets retain their per-item attribution and licence links. Rylume does not claim authorship of these images. Legacy files with unverified names are retained for old documents but quarantined from the palette and model proposals.
