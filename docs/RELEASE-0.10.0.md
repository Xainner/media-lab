# 0.10.0 · Archivos por MCP: enlaces de subida y descarga

Rama: `feat/mcp-files` (sobre `fix/provider-probe`).

| Servicio | Antes | Después |
| --- | --- | --- |
| `runtime` | `web:0.9.1` | `web:0.10.0` |
| `agent`, `comfyui` | sin cambios | sin cambios |

## Problema

Los agentes conectados por MCP no podían trabajar con archivos reales:

- **Subidas imposibles.** La única forma de subir era base64 dentro de los argumentos de la herramienta. Un modelo de lenguaje tendría que escribir cada byte como texto: una imagen de 1 MB son unos 1,4 millones de caracteres. Además, los vídeos de más de 15 s no se podían subir, ni siquiera para escalarlos.
- **Descargas inaccesibles.** La descarga exigía el token Bearer, que guarda el cliente MCP y el modelo no conoce.
- **Guía incompleta.** No explicaba que el servidor es remoto ni que hay que usar el dominio público también desde la red local. Los agentes acababan buscando modelos en local o creando trabajos por SSH.

## Cambios

### Subidas con enlace temporal

- **`create_uploads(files=[{name}], session_id?)`** (permiso `create`)
  - Devuelve de 1 a 50 enlaces por llamada, válidos 2 horas. Cada cuenta puede tener como máximo 200 enlaces sin usar.
  - El agente sube con `curl -T archivo "<url>"`, o en multipart con `-F file=@archivo`, sin cabecera de autorización.
  - La respuesta trae la `reference` (uri y sha256) lista para cualquier herramienta.
  - Un intento fallido no gasta el enlace; uno correcto lo consume.
  - **`get_uploads(ids)`** recupera el resultado si la respuesta se pierde.
- **Detección por contenido**, no por nombre ni por el MIME declarado:

  | Tipo | Se guarda tal cual | Se convierte | Límites |
  | --- | --- | --- | --- |
  | Imagen | PNG, JPEG, WebP (se normalizan a PNG) | GIF, BMP, TIFF y otros a PNG | 20 MiB, 50 MP |
  | Audio | WAV, FLAC, MP3, Ogg/Opus | M4A/AAC, AIFF y otros a FLAC | 1–900 s, 500 MiB |
  | Vídeo | MP4/MOV, MKV, WebM | AVI, MPEG-TS y otros a MKV, sin recodificar | 1–600 s, 500 MiB |

- **Vídeos más largos.** `/v1/media/uploads` (web y MCP) ahora acepta vídeos de hasta 600 s para poder escalarlos. H3 sigue exigiendo entre 2 y 15 s al crear el trabajo.
  - La subida se escribe en disco por partes, en vez de cargarse entera en memoria.
  - El análisis del archivo se hace fuera del bucle de eventos.

### Descargas con enlace temporal

- **`get_download_links(references)`** (permiso `read`): de 1 a 50 enlaces GET válidos 1 hora y reutilizables durante ese tiempo. Admiten Range y no necesitan cabeceras: `curl -o archivo "<url>"`.
- **`get_media`** añade un `temporary_url` y conserva el `download_url` que exige el token Bearer.

### Guías y web

- **`capabilities.inputs`**: formatos y límites de subida, y cuántas referencias acepta cada herramienta:
  - edición: de 1 a 10 imágenes;
  - H3: fotograma inicial y final; en r2v, hasta 9 imágenes, 3 vídeos de 2–15 s y 3 audios de 1–15 s;
  - música: una fuente para covers;
  - escalado: un vídeo;
  - Director: la canción y una imagen o un vídeo por escena;
  - mejora de prompts y agente: 16 referencias.
- **Instrucciones del servidor** (el texto que recibe el agente al conectarse): nueva sección «How this server works». Explica que el servidor es remoto y no hay que instalar nada, que hay que usar el dominio público también en la red local, y cómo enviar y traer archivos.
- **Guía `formats` reescrita** y ejemplos con el flujo de subida, edición y descarga. Las herramientas base64 quedan como alternativa para archivos pequeños.
- **Web, Conexiones MCP**:
  - nuevo paso «Envía y recibe archivos»;
  - aviso de usar siempre la URL pública;
  - bloque «Instrucciones para tu agente», que se puede copiar, está en inglés y no incluye el token.
- **Documentación**: `docs/MCP.md` y `docs/MCP-GUIDE.md` actualizados. La versión del servidor MCP es `0.10.0-mcp-en.1`.

## Seguridad

- **El secreto del enlace.** Cada enlace lleva un secreto aleatorio de 256 bits, del que solo se guarda el hash SHA-256.
- **A qué está ligado.** Al propietario, al token que lo creó y, en las descargas, a un único archivo.
- **Comprobación en cada petición.** Se verifica que el token no esté revocado ni caducado, que conserve el permiso necesario y que MCP y la cuenta sigan activos. Revocar el token o deshabilitar MCP corta los enlaces al instante.
- **Límites.** Siguen vigentes los límites de peticiones (180 por minuto por token y 300 por IP), las cuotas de almacenamiento y las comprobaciones de propiedad.
- **Registros del proxy.** Las URLs quedan en los registros de acceso del proxy, como cualquier URL; por eso duran poco. La guía pide no compartirlas.
- **Archivos temporales.** Las subidas parciales se escriben en `/data/incoming/<temporal>` y se borran al terminar. Al arrancar se eliminan las que tengan más de un día.

## Validación

- **Runtime (pytest):** toda la suite pasa. `tests/test_mcp_files.py` cubre:
  - un solo uso del enlace, el reintento tras un fallo, el límite de tamaño, el 405 y el 404;
  - la caducidad, la revocación y los permisos;
  - el aislamiento entre cuentas y el uso de la referencia en `edit_image`;
  - la descarga sin cabeceras, con Range;
  - la conversión real con ffmpeg de M4A a FLAC y de AVI a MKV, y la detección de WAV y MP4.
- **Web (vitest):** 44 pruebas, incluida la del bloque de instrucciones sin token. `npm run build` pasa.

## 0.10.1 · Que los agentes no recurran a scripts

Revisión hecha como agente, con llamadas reales al MCP de producción:

- **Errores visibles.** Los rechazos del runtime llegaban como «Invalid parameters…», sin el motivo, mientras que un script contra la API sí lo veía. Ahora la herramienta devuelve el mensaje del estudio, por ejemplo «Rejected by the studio: i2v requires first_frame…», sin rutas del servidor.
  - Cola llena (429): pide esperar y reenviar con la misma `idempotency_key`. Antes se confundía con la cuota.
  - Conflicto (409) y función no disponible (503): incluyen el detalle.
- **`wait_for_job(job_id, max_seconds≤50)`**: espera dentro del servidor y devuelve el trabajo. Si sigue en curso, marca `still_running` para volver a llamar. Así no hacen falta `sleep` ni bucles en scripts.
- **`outputs` uniforme**: `get_job` y `wait_for_job` añaden `outputs` (`uri`, `sha256`, `kind`), con cada archivo resultante de cualquier operación.
- **Esquemas descritos**: `tools/list` explica cada campo de imagen, edición, vídeo, música, Director y escalado.
  - Prompt en inglés según el `prompt_guide` del tema.
  - Modos de H3 y etiquetas `<Picture i>`.
  - Valores de `aspect_ratio`.
  - `idempotency_key` y `session_id`.
- **Overview**: muestra la forma exacta de la llamada (`{"body": {...}, "idempotency_key": "..."}`) con un ejemplo, `wait_for_job` y `outputs`. Indica no usar la API HTTP, SSH ni scripts: las herramientas MCP lo cubren todo.
- Las instrucciones copiables de la web incluyen lo mismo.

Validación: toda la suite del runtime (2 tests nuevos de errores, espera, `outputs` y esquemas), 44 pruebas de la web y su build, y 31 pruebas del agente.

## 0.10.2 · Compatibilidad con más clientes MCP

Problemas que reportó un agente externo:

- **`prompt_guide` daba error** («VALIDATION_FAILED: falta la propiedad 'result'»).
  - Causa: era la única herramienta que declaraba un esquema de salida generado (`{result: string}`), y algunos clientes validan contra él el texto Markdown.
  - Solución: ahora se publica como texto plano (`structured_output=False`), sin esquema de salida.
- **El agente confundía las URI `artifact://`** con su propio almacén de artefactos e intentaba abrirlas con sus herramientas locales.
  - La guía, la descripción de `uri` y la de `wait_for_job` aclaran que son identificadores del estudio y no archivos locales. Para verlas se usa `inspect_media` y para obtenerlas, los enlaces de descarga.
  - `wait_for_job` ya devuelve cada salida con su `url` de descarga (1 hora). No hace falta otra llamada.
  - Las descargas incluyen la cabecera `X-Content-SHA256`, que coincide con el `sha256` de la referencia.

Validación: suite completa del runtime (incluye un test nuevo para estos casos), 44 pruebas de la web y build.
