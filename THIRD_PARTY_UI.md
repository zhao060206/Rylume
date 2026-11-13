# UI components and design references

The Rylume desktop shell uses native HTML, CSS and JavaScript. The scientific
canvas and document model remain independent of the interface components.

## BoardUI — MIT

The native button, input and segmented-control components adapt BoardUI's
component dimensions, variant system, field relationships and selected-segment
indicator pattern. React and React Aria implementations were adapted to native
controls; Rylume does not bundle React or claim to use BoardUI's React runtime.

Source: https://github.com/BoardUI/boardui

Reviewed revision: `ec5c5eb3e29c2441be63b9422cd54f411ef23466` (2026-11-10).

Adapted from:

- `components/base/buttons/button.tsx`
- `components/base/input/input.tsx`
- `components/base/segmented-control/segmented-control.tsx`
- `styles/theme.css`

MIT License

Copyright (c) 2026 Mertcan Dundar Esmergul (BoardUI)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Unslop — CC BY 4.0

The redesign follows Unslop's spacing, color, icons, copy, type, layout,
details, product visuals and motion workflow by Damir Sokolovsky (@heydamir).

- Source: https://github.com/heydamir/unslop
- Creator: https://heydamir.design/unslop
- License: https://creativecommons.org/licenses/by/4.0/
- Reviewed revision: `97daa3eb365670ea3f87ed85356cbfcee18105a5` (2026-11-10).
- Application: adapted the workflow to an existing scientific drawing desktop
  application. No marketing artwork or example dashboard was copied.

## Other evaluated resources

BoardUI was selected from the user's component-library reference. Public pages
from Bencho, HeroUI Pro, beUI Pro, Libraries.dev and Watermelon UI were reviewed.
No paid Pro source or unlicensed component was copied. Promotional glow and
decorative effect libraries were not added to the drawing workspace. Native
interaction transitions preserve the quiet interface and reduced-motion support.

- https://www.boardui.com/
- https://bencho.dev/
- https://heroui.pro/
- https://pro.beui.dev/
- https://libraries.dev/llms.txt
- https://ui.watermelon.sh/
