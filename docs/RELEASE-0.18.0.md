# 0.18.0 · Edición a 2K

Imágenes `media-lab-web` y `media-lab-agent` 0.18.0. ComfyUI no cambia (0.10.0). El runtime
cambia (`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye).

## Edición a 2K

- **Qué:** Qwen-Image 2.1 edita ahora con `resolution` hasta 2048 (unos 4 MP; una referencia
  16:9 sale cerca de 2720×1536).
- **Límites:** solo INT8 (Base o Turbo), como mucho **4 referencias** y sin cambio de ángulo ni
  quitar fondo. Usa el mismo interruptor que la creación a 2K (`ENABLE_2K`); en un servidor sin 2K
  la edición sigue limitada a 1024.
- **Capacidades:** `two_k_create_only` pasa a `false` y `two_k_edit` describe el límite
  (resolución máxima, referencias, precisión y modelo).

## Interfaz

- **Lab:** nuevo chip **Tamaño (1 MP / 2K)** para Qwen en el modo Crear. Sirve para crear (tier 2K)
  y para editar (2048). Solo aparece si el servidor tiene el 2K activado. Al elegir 2K se
  conservan las 4 primeras referencias.
- **Estudio clásico:** la edición ofrece la opción 2K y una resolución personalizada hasta 2048
  con INT8 y hasta 4 imágenes.
- **Etiqueta:** las creaciones a 2K muestran «· 2K» junto al modelo.

## Agentes y MCP

- **MCP:** `generate_image`, `edit_image`, `prompt_guide` (guía de edición y de controles) y el
  contrato explican cuándo hay 2K y con qué límites.
- **Agente del estudio:** `image_edit` acepta `resolution` hasta 2048 con INT8 y hasta 4 imágenes,
  y `image_generate` documenta el tier 2K.
- **Sin el nombre Rinari:** el agente se mantiene, pero los textos del MCP, la página de conexión,
  las guías y los nombres de descarga (`media-lab-…`) ya no lo nombran.

## Validación

- **Prueba en una RTX 3090** (Base INT8, 25 pasos, `resolution=2048`, referencias de
  2016×1152), sin OOM ni descarga parcial del modelo:

  | Referencias | Tiempo | VRAM pico |
  |---|---|---|
  | 1 | 232 s | 21,4 GB |
  | 2 | 326 s | 22,4 GB |
  | 4 | 566 s | 23,8 GB |

- **Sin probar:** Turbo y BF16 a 2K, y más de 4 referencias. BF16 y más de 4 referencias quedan
  bloqueados.
- **Pruebas:** runtime, agente y web pasan; `npm run build` también. En el navegador (API de QA),
  el chip 2K envía `resolution_tier: "2k"` al crear.
