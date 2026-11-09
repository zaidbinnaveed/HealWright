# Third-party notices

HealWright itself is MIT-licensed (see `LICENSE`). The web app in `frontend/` contains code copied from, or depends on, the third-party work below.

## UI elements copied from uiverse.io

MIT License, Copyright (c) 2023 Uiverse.io (the same elements as https://github.com/uiverse-io/galaxy). Short paths are relative to `frontend/src/components/`.

| Element | Author / URL | Used in | Changes |
| --- | --- | --- | --- |
| Primary button | SouravBandyopadhyay, https://uiverse.io/SouravBandyopadhyay/wise-panda-94 | `frontend/src/components/ui/Button.tsx` | theme colours, smaller hover scale |
| Secondary button | Z4drus, https://uiverse.io/Z4drus/bitter-turtle-76 | `ui/Button.tsx` | theme colours, full radius |
| Theme toggle | Creatlydev, https://uiverse.io/Creatlydev/massive-quail-70 | `ui/Inputs.tsx`, `ui/uiverse.css` | 36 px, theme colours, labelled checkbox |
| Search input | themrsami, https://uiverse.io/themrsami/calm-eel-15 | `ui/Inputs.tsx`, `ui/uiverse.css` | theme colours, accent glow, label |
| Spinner | satyamchaudharydev, https://uiverse.io/satyamchaudharydev/young-puma-4 | `ui/Feedback.tsx`, `ui/uiverse.css` | accent colour, size prop |
| Row skeleton | sahilxkhadka, https://uiverse.io/sahilxkhadka/proud-octopus-27 | `ui/Feedback.tsx` | ink-token colour, repeated rows |
| Card skeleton | elijahgummer, https://uiverse.io/elijahgummer/hot-fly-77 | `ui/Feedback.tsx`, `ui/uiverse.css` | theme colours, radius |
| Tooltip | ahmedyasserdev, https://uiverse.io/ahmedyasserdev/wise-newt-71 | `ui/Feedback.tsx` | bubble only, hover + focus |
| Checkbox | lenin55, https://uiverse.io/lenin55/black-dragon-46 | `ui/Feedback.tsx`, `ui/uiverse.css` | accent colour, focus ring |
| Status dot | elijahgummer, https://uiverse.io/elijahgummer/brown-moose-94 | `components/StatusBadge.tsx`, `ui/uiverse.css` | 8 px, colour per status |
| Toast | seyed-mohsen-mousavi, https://uiverse.io/seyed-mohsen-mousavi/wicked-chipmunk-81 | `ui/Toast.tsx` | kinds, stack, auto-dismiss, live region |
| Stat card | Javierrocadev, https://uiverse.io/Javierrocadev/angry-puma-14 | `ui/Cards.tsx` | accent blob, caption line, flexible size |
| Terminal card | Yaya12085, https://uiverse.io/Yaya12085/soft-jellyfish-99 | `ui/Cards.tsx` | any body, action slot |
| Switch | Cksunandh, https://uiverse.io/Cksunandh/slimy-treefrog-92 | `ui/Inputs.tsx` (Switch), `ui/uiverse.css` | token colours, emerald thumb when on, focus ring |

The uiverse.io licence text:

```
MIT License

Copyright (c) 2023 Uiverse.io

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
```

## Fonts

- Geist and Newsreader, bundled through `@fontsource-variable/geist` and `@fontsource-variable/newsreader` 5.3.0: SIL Open Font License 1.1.
- Clash Display and Satoshi (Fontshare, Indian Type Foundry, ITF Free Font License), used only by `scripts/gen_brand.py` for the favicons and social card. The licence allows self-hosting but not redistribution, so the font files are downloaded by `scripts/fetch_fonts.py` and never committed.
