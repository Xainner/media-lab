# Web 0.8.0 «Nocturne»: rediseño completo de la interfaz

Desplegado en Saturno el 2026-10-08 como `20261008-nocturne-487e92c`, con ajustes posteriores el mismo día.
Rama: `feat/web-nocturne`.

| Servicio | Antes | Después |
| --- | --- | --- |
| `runtime` | `web:0.7.3` | `web:0.8.0` |
| `agent` | `agent:0.7.2` | sin cambios |
| `comfyui`, `comfyui-gpu1` | `comfyui:0.6.0` | sin cambios |

Rollback: `rinari-visual-lab-web:rollback-20261008-nocturne-487e92c` (= 0.7.3). El código anterior está en `~/.rinari/releases/20261008-nocturne-487e92c/source-before.tgz`, junto con `changed-files.txt`, `deleted-files.txt` e `images-before.txt` / `images-after.txt`.

## Cambios

La interfaz web se rehízo desde cero. Solo se conservó la capa API: `bridge.ts`, `studio/lib/api.ts`, `h3.ts`, las claves de `localStorage` y los eventos. No se quitó ninguna función ni ningún endpoint.

**Entrada cinematográfica**

- El emblema «Apertura» se dibuja con luz, el diafragma se abre hacia el observatorio y Rinari saluda junto al panel de acceso.
- Rinari reacciona al formulario: se tapa los ojos en la contraseña, hace un puchero ante un error, guiña al entrar y se concentra en el paso de 2FA.
- La intro se puede saltar, se ve una vez por sesión y no aparece con movimiento reducido ni con la animación desactivada. Dura como máximo 6,5 s aunque el navegador limite los fotogramas.

**Estudio**

- Riel propio que se expande, con desplazamiento cuando hay muchas secciones.
- Franja de telemetría con el estado de las GPU y la cola.
- Paleta Ctrl/⌘+K.
- Nebulosa WebGL que cambia de tono según la herramienta.
- Rinari como mascota viva que reacciona a los trabajos (evento `rvl-job`).

**Pantallas**

- Nueva portada (Inicio).
- Cada herramienta (Crear, Editar, Vídeo, Música, Director, Agente) sigue el patrón «Consola + Escenario».
- Galería en mosaico con lightbox, Biblioteca con inspector y Trabajos como pistas de progreso.
- Cuenta, MCP, Proveedores y Administración usan el nuevo sistema visual.

**Arte y marca**

- Logo real, favicons y un banco de bustos, chibis y escenarios en WebP (unos 4,5 MB en total). Detalle en [WEB-ART.md](WEB-ART.md).
- Se retiró el arte v1 y los logos SVG de 3,2 MB.
- El logo de los correos pasa a ser un PNG de 37 KB (`/brand/mail-logo.png`).

**Servidor**

- `/assets/*` se sirve con `public, max-age=31536000, immutable`.
- `/art/*` y `/brand/*` se sirven con `public, max-age=86400, stale-while-revalidate=604800`.
- La página de la aplicación, las rutas que no existen y la API siguen con `no-store`.
- Se registraron los tipos MIME webp, avif, woff y woff2, que faltaban en la imagen *slim*.

**Fuentes y motion**

- Bricolage Grotesque, Instrument Sans y JetBrains Mono, autoalojadas.
- GSAP para las líneas de tiempo y motion para las transiciones.

**Correcciones de paso**

- El patrón HTML del nombre de usuario era inválido con el modo `v`.
- El botón «Saltar intro» quedaba dentro de un contenedor `aria-hidden`.

## Validación

- Web: `tsc` y `vite build` pasan. Vitest: 13 archivos y 38 pruebas, 4 de ellas nuevas (intro saltable, intro desactivada con movimiento reducido o `animation=off`, reacciones de la mascota, y riel de administración con la paleta).
- Runtime: pytest completo en verde (2 pruebas omitidas), con una prueba nueva de cabeceras de caché y tipo MIME.
- `package-lock.json` generado con npm 10.9 (`node:22-bookworm-slim`). `npm ci` pasa en ese contenedor.
- Recorrido visual con el backend simulado a 1440, 768 y 375 px:
  - Pantallas: Inicio, Crear, Editar, Vídeo, Música, Director, Agente, Galería, Biblioteca, Trabajos, Perfil, Seguridad, Preferencias, MCP, Proveedores y Administración (Usuarios, Correo y Estado).
  - Corregido durante el recorrido: la mascota tapaba el escenario, el chibi tapaba el botón de la cabecera, el riel no mostraba Administración y el compositor del agente se superponía al chat.
- Producción:
  - `check-idle` en OK antes de cada reinicio y runtime `healthy`.
  - `/` y `/health` devuelven 200; `/mcp` sin token devuelve 401.
  - La regla del cortafuegos sigue presente.
  - La página de la aplicación sale con `no-store` y los recursos estáticos con su caché y tipo MIME.
  - La entrada se ve completa y no hay errores en la consola.

## Pendiente

- Bucle de vídeo de la entrada generado con H3 (FL2VA con el mismo primer y último fotograma). Queda como mejora opcional; la entrada funciona sin él.
