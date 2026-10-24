# 0.11.0 · Feedback de una sesión real de Rinari Agent

Rama: `fix/mcp-client-compat` (incluye 0.10.2).

| Servicio | Antes | Después |
| --- | --- | --- |
| `runtime` | `web:0.10.2` | `web:0.11.0` |
| `agent` | `agent:0.9.0` | `agent:0.11.0` |

Fuente: `feedback-visual-lab-2026-10-12.md`, una sesión de Rinari Agent que generó 5 imágenes Turbo y 5 vídeos H3 de 10 s usando solo el MCP. El resultado fue bueno, pero costó 11,2 M tokens.

## 1. `prompt_guide` no cumplía su `outputSchema`

Ya estaba corregido en 0.10.2: la guía se publica como texto plano, sin esquema de salida. Un test comprueba que `tools/list` no declara `outputSchema` para ella. Los clientes que guardaron la lista de herramientas anterior tienen que reconectarse.

## 2. Anotaciones `readOnlyHint`

- **Consultas** (todos los GET, `check_prompt`, `prompt_guide`, `wait_for_job`, `get_uploads`, `get_download_links`, `get_media`, `export_image`): `readOnlyHint: true`, `destructiveHint: false` e `idempotentHint: true`.
- **Creación y subidas** (`create_uploads`, `upload_*` y las de creación): `readOnlyHint: false` y `destructiveHint: false`. Así los clientes no las tratan como destructivas por defecto.
- **`delete_media`**: sigue siendo la única con `destructiveHint: true`.
- **Herramientas que usan el proveedor externo** (`improve_prompt`, `review_with_agent`, `plan_storyboard`, `start_agent`…): `openWorldHint: true`. No se marcan como de solo lectura porque consumen el proveedor.

## 3. Esperar trabajos largos sin dar tantas vueltas

En la sesión hubo 83 llamadas solo para seguir los trabajos, y en una de ellas el cliente cortó por tiempo a los 30 s.

- **Esperas largas con progreso.** `wait_for_job` acepta `max_seconds` de hasta **600 s** cuando la llamada trae `_meta.progressToken`. Durante la espera el servidor envía `notifications/progress` cada ~5 s, con el porcentaje y un mensaje como «running · 40% · sampling · queue position 2». Rinari Agent renueva el tiempo de espera con cada notificación.
- **Cómo se envían las notificaciones.**
  - El transporte respondía siempre en JSON, y en ese modo el SDK descarta las notificaciones.
  - Ahora un `tools/call` con `progressToken`, de un cliente que acepta `text/event-stream`, se responde como flujo SSE: primero el progreso y al final el resultado.
  - Todo lo demás sigue en JSON exactamente igual.
  - Son dos gestores sin estado del SDK oficial, sin parches, y `web.py` arranca los dos.
- **Sin `progressToken`** cada espera dura como máximo 50 s, porque nada renovaría el tiempo de espera del cliente.
- **Respuesta mientras sigue en curso.** Es compacta: `status`, `progress_pct`, `stage`, `queue_position`, `gpu`, `waited_seconds` y `still_running`. No repite el prompt ni la petición, lo que ahorra tokens en cada vuelta.
- **Respuesta al terminar.** Lleva `progress_pct: 100` y `outputs` con `uri`, `sha256`, `kind`, `bytes` y `url`.

## 4. `review_with_agent` rechazado sin motivo

El motivo se perdía en dos puntos:

- El servidor del agente convertía cualquier fallo en «Operación no disponible o argumentos inválidos».
- Al llamar al runtime, sus errores llegaban como «Runtime 4xx: operación rechazada».

Ahora el motivo viaja hasta el MCP:

- El agente devuelve el detalle del runtime o del proveedor, sin secretos y recortado a 300 caracteres. Los errores internos siguen siendo genéricos.
- El runtime añade ese motivo a «El agente no pudo completar la operación: …».

Causa probable: un modelo que razona y agotó los 1200 tokens de la revisión antes de devolver el JSON. Es el mismo caso que las pruebas de capacidades de 0.9.1. No quedaban logs del contenedor para confirmarlo.

- La revisión pasa a 4096 tokens.
- La mejora de prompts pasa a 4096 / 5000 / 6000 (imagen / canción / vídeo).

## 5. Descargas

Los enlaces de `get_download_links` ya traían `bytes`. Ahora también traen `sha256` en primer nivel, y las salidas de `wait_for_job` incluyen `bytes`. Cada descarga lleva la cabecera `X-Content-SHA256` (desde 0.10.2).

## Validación

- **Runtime:** toda la suite pasa. Hay tests nuevos para las anotaciones, para el límite y la respuesta compacta sin `progressToken`, y para las notificaciones de progreso reales con el cliente oficial `mcp` por SSE hasta que el trabajo termina.
- **Agente:** 31 pruebas.
- **Web:** 44 pruebas y el build.
