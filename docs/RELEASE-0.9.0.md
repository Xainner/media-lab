# 0.9.0 · Qwen-Image 2.1 Turbo y escalado de vídeo FlashVSR

Rama: `feat/turbo-flashvsr` (sobre `feat/web-nocturne`).

| Servicio | Antes | Después |
| --- | --- | --- |
| `runtime` | `web:0.8.0` | `web:0.9.0` |
| `agent` | `agent:0.7.2` | `agent:0.9.0` |
| `comfyui`, `comfyui-gpu1` | `comfyui:0.6.0` | `comfyui:0.7.0` (+ nodo FlashVSR) |

## Qwen-Image 2.1 Turbo

- `model_variant: "base" | "turbo"` en `generate`, `edit` y, como `keyframe_variant`, en los fotogramas clave del Director.
  - Turbo usa el calendario oficial de 8 sigmas del checkpoint (`model_index.json`, `sample_sigmas` más el 0 final), con `ManualSigmas`, `CFGGuider` (CFG 1) y `SamplerCustomAdvanced`.
  - `quality` no se aplica, y `options.steps`, `options.scheduler` y `options.denoise` se rechazan.
  - La edición conserva `QwenImage21Cache`.
- Pesos: el reempaquetado de Comfy-Org en INT8 (7,3 GB) y en BF16 (14,2 GB), con revisión y SHA-256 fijados en `deploy/scripts/download-turbo-flashvsr.sh`. El codificador y el VAE son los de Qwen-Image 2.1.
- Sin el modelo no hay sustitución automática: la petición devuelve 422. `capabilities.model_variants` indica la disponibilidad por precisión.
- Interfaz: selector «Qwen 2.1 · Turbo» en Crear y en Editar, que se recuerda por navegador.
  - Con Turbo se ocultan los pasos, la curva de ruido y el denoising.
  - Nueva comparación «mismo prompt y seed» entre los dos modelos.
  - El Director añade el selector «Modelo de imágenes nuevas».
- Medición en una 3090 (1344×768, mismo prompt): Turbo tarda 9,2 s en frío y Qwen 2.1 con 40 pasos, 23,4 s. El Turbo reprodujo mejor el texto «RINARI».

## Escalado de vídeo FlashVSR v1.1 (x2 / x4)

La idea viene de Maestro, que usa FlashVSR por tramos. **No se copió código de Maestro ni de WanGP**: su licencia no comercial de evaluación prohíbe integrarlos en servicios alojados o APIs. Usamos:

- Los pesos oficiales de FlashVSR v1.1 (Apache-2.0), en `models/FlashVSR-v1.1`.
- El nodo `lihaoyun6/ComfyUI-FlashVSR_Ultra_Fast` (GPL-3.0, uso interno), fijado en `4820b3f`, sin instalar su `requirements.txt`.

**Flujo (`POST /v1/jobs/upscale`, operación `upscale`; un trabajo usa una sola GPU)**

1. El runtime normaliza el vídeo a CFR, sin audio.
2. Lo rellena replicando los bordes hasta múltiplos de 128/escala. El nodo recorta al centro cualquier mosaico cuyo tamaño escalado no sea múltiplo de 128, y eso desalineaba el resultado.
3. Lo divide en tramos de tamaño equilibrado, cada uno con 8 fotogramas compartidos con el anterior.
4. Pasa cada tramo por FlashVSR en el mismo worker (`tiled_dit`, mosaico de 512 en x2 y de 256 en x4).
5. Une los tramos con un fundido cruzado sobre el solapamiento (sin el fundido se veía un pequeño salto), recorta el relleno y vuelve a montar el audio original: copiado si es AAC, MP3 o ALAC; si no, en AAC a 320k.
6. Libera la VRAM (`/free`) antes y después del trabajo.

**Límites**

- x2: entradas de hasta 1,1 MP por fotograma.
- x4: entradas de hasta 0,42 MP (480p).
- Duración máxima: 10 minutos.
- Tiempo estimado máximo: 45 minutos. Se estima en unos 15 s (rápido) o 40 s (calidad) por segundo de vídeo y megapíxel de salida.
- Modos: `fast` (FlashVSR tiny, por defecto) y `quality` (FlashVSR full, unas 3,4 veces más lento).

**Mediciones en una 3090, con clips H3 reales de 5–6 s**

| Caso | Tiempo | VRAM máx. | RAM máx. del contenedor |
| --- | ---: | ---: | ---: |
| x2 · 864×480 · rápido (2 tramos) | 98 s | ~15 GB | ~15 GB |
| x2 · 1280×704 · rápido (2 tramos) | 262 s | ~16 GB | 17 GB |
| x4 · 864×480 · rápido (4 tramos) | 475 s | ~17 GB | 16 GB |
| x2 · 864×480 · calidad (una pasada) | 225 s | ~17 GB | 18 GB |

- Alineación con el original: MSE medio de 26 (x2) y 30 (x4) en luminancia reducida, sin desfase temporal. Los empalmes no superan 1,16 veces el movimiento real.
- Sin mosaico, x2 de 480p llegaba a 21,7 GB de VRAM, demasiado justo; por eso no se usa.

**Interfaz y MCP**

- Panel «Escalar vídeo» bajo los resultados de Vídeo y en el inspector de la Biblioteca (vídeos, producciones y subidas). Muestra el tamaño resultante y desactiva x4 en vídeos grandes.
- Trabajos muestra el tipo «Escalado».
- MCP: nueva herramienta `upscale_video` (alcance `create`) y `model_variant` en `generate_image` y `edit_image`. Guías actualizadas, versión del servidor `0.9.0-mcp-en.1`.
- Agente Rinari: herramienta `video_upscale` y `model_variant`/`keyframe_variant`. Si no hay pesos Turbo, no lanza ningún trabajo de GPU.

## Correcciones

- `ComfyClient._first_output` podía devolver la vista previa del vídeo de entrada que publica `LoadVideo` en lugar del resultado de `SaveVideo`. Afectaba también a H3 r2v con vídeos de referencia. Ahora ignora las salidas de tipo `input`.
- `CreativeResult` mostraba como audio los vídeos subidos (carpeta `sources`); ahora decide por la extensión.
- Los errores de ffmpeg en el escalado incluyen las últimas líneas de su salida de error.

## Validación

- Runtime: pytest completo en verde (187 pruebas, 2 omitidas), con `tests/test_turbo_upscale.py` nuevo.
- Web: `tsc` y Vitest en verde (14 archivos, 43 pruebas; 5 nuevas para Turbo y escalado).
- Agente: `npm test` en verde (31 pruebas; 3 nuevas).
- Guías sincronizadas (`sync-mcp-guides.py --check`).
- Canario en Saturno: un ComfyUI temporal en la GPU1, con el worker de producción parado durante la prueba, ejecutó el método real `CreativeJobs._upscale` de principio a fin.

## Pendiente

- Bucle de vídeo de la entrada (propuesto en 0.8.0).
