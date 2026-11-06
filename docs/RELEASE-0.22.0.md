# 0.22.0 · Títulos animados

Imágenes `media-lab-web` y `media-lab-agent` 0.22.0. `media-lab-comfyui` no cambia (0.12.0). El
runtime cambia (`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye). No hay modelos nuevos
que descargar: usa MiniMax H3 Fused Turbo, que ya estaba instalado.

Texto exacto animado sobre fondo negro o blanco: un título o una secuencia de 2 a 6 frases que
aparecen de una en una. El runtime pinta el fondo como primer y último fotograma y escribe el
prompt de H3 con plantillas propias, así que nadie tiene que escribir un prompt de vídeo.

## Cómo se usa

| Dónde | Cómo |
|---|---|
| Web | Modo de vídeo **Títulos**: una frase por línea, chips **Animación** (Libre + 9 estilos) y **Fondo** (Negro, Blanco) |
| Web con IA | Con IA activa, el botón **Planear** convierte una descripción en frases, estilo y animación; se revisan antes de generar |
| API y MCP | `POST /v1/jobs/title` / `create_animated_title`; `improve_prompt` con `mode=title` planea |
| Agente | Herramienta `video_title` |

- **Campos:**
  - `phrases`: 1 título de hasta 160 caracteres, o 2–6 frases de hasta 80 (160 en total), sin
    saltos de línea; se respetan tal cual (tildes, `¡ ¿`, mayúsculas);
  - `style`: dust, dissolve, neon, typewriter, glitch, smoke, fire, impact o kinetic;
  - `motion` (opcional, inglés): sustituye al estilo;
  - `look` (opcional, inglés): estilo de letra;
  - `background`: `#000000` (por defecto) o `#FFFFFF`;
  - `seconds` 5–15, `aspect_ratio` 16:9 / 9:16 / 1:1, `resolution` preview / 480p / 720p
    (por defecto 720p).
- **Tiempos:** una secuencia necesita al menos 1 s por frase más 1 s de fondo vacío al final; el
  runtime reparte el resto según la longitud de cada frase.
- **Final limpio:** el runtime funde imagen y sonido al color de fondo en los últimos 0,5 s.
- **Sin archivos extra:** el fondo se genera en una carpeta temporal y va directo a ComfyUI; no
  queda en la biblioteca.
- **Capacidades:** `/v1/capabilities` añade `video.titles` (listo si Fused Turbo lo está).
- **Reanudar y cancelar:** `title` es una operación creativa más.

## Lo que se aprendió en las pruebas

- **Solo negro y blanco:** sobre verde croma y sobre `#1E3A8A`, H3 inventó escena detrás del texto
  (una cara, un cielo de estrellas). Los demás colores se rechazan.
- **No nombrar lo que no debe salir:** la plantilla decía "no people, faces, hands…" y H3 dibujó una
  cara sobre blanco. Fused Turbo no tiene prompt negativo; la plantilla describe solo tipografía
  sobre un fondo que no cambia.
- **El modelo no despeja la última frase:** en las secuencias, H3 dejaba la última frase hasta el
  penúltimo fotograma y cortaba en seco, aunque el prompt pidiera fondo vacío. El fundido final del
  runtime lo resuelve siempre.

## Resultados en server2

RTX 3090, 720p, Fused Turbo 4 pasos, una GPU por trabajo:

| Prueba | Resultado |
|---|---|
| Fondo negro (secuencias, máquina de escribir en español, neón de 10 s) | Fondo limpio en 5 de 5; texto exacto, con tildes y `¡!` |
| Fondo blanco | Fondo limpio en 1 de 3 (1 de 2 con la plantilla final): "MEDIA LAB" limpio; una secuencia mostró formas grises detrás del texto |
| Fundido final | La secuencia en negro y la de blanco terminan en el color de fondo |

- **Duración:** entre 3,8 y 5,8 min por clip de 5–6 s y unos 10 min el de 10 s, incluida la carga
  del modelo.
- **Sin probar:** el planificador de punta a punta (la cuenta de prueba no tenía proveedor IA); sus
  reglas están cubiertas por pruebas del agente.

## Validación

- **Pruebas:**
  - runtime, con el nuevo `test_titles.py`: límites del contrato y del fondo, reparto de tiempos,
    plantillas (texto exacto, sin nombrar personas), mismo fondo como primer y último fotograma,
    fundido real con ffmpeg, ruta, idempotencia y capacidades;
  - MCP: esquema de `create_animated_title` y modo `title` de `improve_prompt`;
  - agente: `video_title` solo con Fused Turbo listo, y planes de título validados sin recortes;
  - web, con `npm run build` y vitest: petición de Títulos con cualquier modelo elegido, @handles
    como texto, sin LoRAs ni mejora al generar, y planificación en modo `title`.
- **Generadores:** `sync-model-options.py --check` y `sync-mcp-guides.py --check`.
