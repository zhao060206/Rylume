# Third-party notices

Rylume's original code is distributed under AGPL-3.0-only. The following components retain their own licenses. Inclusion in this project does not transfer their authorship to Rylume.

## Scientific artwork

Curated Bioicons artwork has per-asset author, source URL, original digest, license and modification notes in `assets/bioicons/manifest.json` and `assets/bioicons/ATTRIBUTION.md`. Original SVG files are retained as `assets/bioicons/*.original.svg`; editable conversions are under `ui/library`. Licenses include CC BY 3.0, CC BY 4.0 and CC0 as specified per entry. Attribution must be retained where required; exported figures include credit sidecars.

Third-party paper/reference images are deliberately excluded. Links in the reference catalog confer no license to redistribute the linked figures.

## MIT-licensed compatibility code

`vendor/client.py`, `vendor/credentials.py`, and `vendor/postprocess.py` originate from [yrui-cmd/cell_cns_figure](https://github.com/yrui-cmd/cell_cns_figure). Their MIT copyright and full permission notice are preserved in `licenses/cell_cns_figure-MIT.txt`. The application uses the local postprocessor compatibility layer; no customer credentials are distributed.

## PyMuPDF and MuPDF

The Windows release uses PyMuPDF 1.28.2 with MuPDF 1.28.2, Copyright Artifex Software and contributors, under GNU Affero General Public License v3. The full AGPL text is in `LICENSE`; matching PyMuPDF and MuPDF source archives, licensing and build instructions are separate release assets. Upstream: https://github.com/pymupdf/PyMuPDF and https://mupdf.com/.

## Python and packaged libraries

`licenses/Python-LICENSE.txt` contains Python's license. `licenses/python-packages.json` records installed package versions and copied notices, with full license files under `licenses/python-packages/`. The binary retains additional upstream notices shipped with its libraries, including NumPy/OpenBLAS, OpenCV, ONNX Runtime, pythonnet, pywebview and vtracer.

WebView2 Runtime and .NET are system prerequisites, not bundled Microsoft installers. Their licenses are provided by their respective vendors.

## GEOS and certifi corresponding source

The packaged Shapely 2.1.2 links dynamically to GEOS 3.13.1 (LGPL-2.1-or-later).
certifi 2025.4.26 is under MPL-2.0. Their unmodified source archives are included
in the dependency-sources release asset. The GEOS license and replacement shared
libraries remain under `_internal/shapely.libs`; Rylume does not restrict the
replacement or debugging of those libraries as permitted by the LGPL.
