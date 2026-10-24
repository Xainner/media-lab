# Arte de Rinari · Web (v2 «Nocturne»)

Arte de la interfaz web desde 0.8.0. Sustituye al arte v1 (`public/art/rinari-*.png`, `logo.svg`, `logo-wordmark.svg`, `favicon.svg`), que se retiró.

## Marca

El logo es el emblema «Apertura»: unos auriculares con orejas de gato que forman el diafragma de una cámara, con un destello de *play* y una onda de sonido. Junta imagen, vídeo y música. Lo generó Codex CLI (`artifacts/web-v2-art/L/out/logo-a.png`, fuera de git) y el usuario lo eligió entre tres propuestas.

| Archivo (`apps/web/public/brand`) | Uso |
|---|---|
| `emblem.webp` (640 px), `emblem-256.webp` | Riel, entrada, cargas, lockup `Brand` |
| `favicon-32.png`, `icon-512.png`, `apple-touch-icon.png` | `index.html` |
| `mail-logo.png` (144 px) | Correos transaccionales (`mail_templates.py`) |

`public/logo-rinari.png` se mantiene como copia de `mail-logo.png` para que los correos ya enviados sigan mostrando el logo. El wordmark es tipográfico (Bricolage Grotesque, no es una imagen). El trazo animado de la intro es un SVG hecho a mano (`src/brand/Logo.tsx`, `LogoTrace`).

## Banco de imágenes (`apps/web/public/art/v2`)

- `rinari/`: bustos de 720 × 1080 alineados para el *crossfade* de expresiones: smug (+blink/talk), focused, laugh, pout (+talk), proud, surprised (+blink), shy, wink y `hero-cut`.
- `chibi/`: poses para estados vacíos, cargas y cabeceras: confetti, peek, point, stamp, tug, typing, download, ledge, read, sleep, wave, dance, glowsticks, sing, dj, party, wand, orbs, paint, clapper, cut, frames, tangled, offline.
- `plates/`: escenarios 16:9 sin personaje principal (entrance, home, image, edit, video, music, director), cada uno con una versión `-sm` de 960 px.

Peso total: unos 4,5 MB en WebP. `web.py` sirve `/art/v2/*`, `/brand/*` y `/assets/*` con caché inmutable de un año.

## Proceso

1. Codex CLI (`codex exec -s read-only -i ref… - < job.txt`), con un máximo de 5 referencias de identidad por trabajo y la ficha de personaje incluida en el prompt (`~/.claude/skills/rinari-promo/v3/mv/img/CHARACTER.md`). Las salidas se recogen de `~/.codex/generated_images/<sesión>/`.
2. Revisión manual de cada imagen: identidad, lados (clips en el lado izquierdo de ELLA, estampados solo en su manga izquierda, liga en su muslo derecho), manos, sin texto y alfa real. Las imágenes rechazadas no entran al banco.
3. Optimización con `apps/web/scripts/build-art.py`:
   - Recorte del alfa (valores por debajo de 40 pasan a 0), salvo en los bustos, que no se recortan para que las expresiones queden alineadas.
   - Conversión a WebP y versiones `-sm` de los *plates*.

   ```bash
   services/runtime/.venv/Scripts/python.exe apps/web/scripts/build-art.py [prefijos]
   ```

Los trabajos, logs y hojas de revisión quedan en `artifacts/web-v2-art/` (fuera de git).

## Licencias

Bricolage Grotesque, Instrument Sans y JetBrains Mono se empaquetan con `@fontsource/*` (OFL 1.1). Sus licencias están en `node_modules/@fontsource/*/LICENSE` y en `public/licenses`.
