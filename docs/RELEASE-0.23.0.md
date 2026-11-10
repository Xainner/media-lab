# 0.23.0 · MiniMax-H3-Image

Imágenes `media-lab-web` y `media-lab-agent` 0.23.0 y `media-lab-comfyui` 0.13.0 (ComfyUI v0.45.0,
`989d93d`). El runtime cambia (`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye). Hay un
grupo de modelos nuevo, `h3-image` (~22 GB), que entra en los presets `recommended` y `all`.

MiniMax-H3-Image es el modelo de imagen de la familia H3: un solo checkpoint crea y edita, con 6
pasos y sin prompt negativo. Trabaja de 4 MP a sus 16 MP nativos y sigue instrucciones largas.

## Cómo se usa

| Dónde | Cómo |
|---|---|
| Web | Modelo **MiniMax H3 Image** en el selector de imagen; chip **Tamaño** 2K (unos 4 MP) o 16 MP. Con fotos adjuntas, edita |
| API y MCP | `generate_image` / `edit_image` con `model=h3image` |
| Agente | `image_generate` / `image_edit` con `model=h3image` |

- **Crear:** `resolution_tier` `2k` (unos 4 MP, por defecto) o `4k` (16 MP: 4096×4096, 5472×3072…).
  Los nueve formatos de siempre. El prompt se usa tal cual: una descripción completa en inglés de
  toda la imagen (la guía `image` explica cómo). No acepta 1MP, opciones, transparencia, Turbo,
  BF16, control ni LoRAs; `quality` se ignora.
- **Editar:** de 1 a 10 referencias. La instrucción va en cualquier idioma; `<image1>`… se envía como
  `<Picture 1>`…. El expansor oficial (las instrucciones de edición de MiniMax-H3-Image-PE sobre
  Qwen3.5 9B) ve las fotos y escribe la descripción completa, que queda como prompt compilado. El
  lienzo es la primera referencia a unos 4 MP.
- **Grafos:** siguen las plantillas oficiales de ComfyUI (`image_minimax_h3_image_t2i` /
  `_image_edit`): `MiniMaxH3ImageConditioning`, euler / simple, CFG 1.
- **Capacidades:** `/v1/capabilities` añade `image_models.h3image`.

## Modelos

`deploy/scripts/download-h3-image-models.sh` descarga, con revisión fija y SHA-256:

- el DiT `minimax_h3_image_pruned_int8_convrot` y el VAE de imagen (Comfy-Org);
- las instrucciones del expansor (`prompt/t2i/system_prompt.txt` y `prompt/edit/task_prompt.txt` de
  MiniMaxAI/MiniMax-H3-Image-PE), que no se copian al repositorio.

Reutiliza el codificador Qwen3-VL 32B de H3 (grupo `h3`) y el Qwen3.5 9B de MOSS (grupo `moss`):
el instalador añade esos grupos solos.

> [!IMPORTANT]
> **Licencia distinta a la de H3:** la MiniMax-H3-Image Community License exige autorización
> previa por escrito de MiniMax para que otras personas usen el modelo en tu servidor (web, API o
> MCP), y obliga a comprometerlas con sus restricciones de uso. No cubre la UE, el Reino Unido,
> Corea del Sur ni EE. UU., y sus resultados no pueden usarse para entrenar otros modelos. Si no
> encaja con tu caso, no instales `h3-image`.

## Otros cambios

- **ComfyUI v0.45.0:** trae los nodos de H3 Image (`MiniMaxH3ImageConditioning`, `TextGenerateV2`,
  `JsonExtractString`). La imagen `media-lab-comfyui` pasa a 0.13.0.
- **Subidas de hasta 1 GiB:** imágenes, audio y vídeo, en la web, `/v1/uploads`, `/v1/media/uploads`
  y la subida por enlace del MCP (antes 20 MiB las imágenes y 500 MiB audio y vídeo). El límite de
  imagen se cambia con `UPLOAD_MAX_BYTES`. La herramienta MCP en base64 sigue en 20 MiB: el archivo
  viaja dentro del mensaje. Detrás de NPM, sube `client_max_body_size` a `1025m`
  (`deploy/npm-proxy-advanced.conf`).
- **Resultados grandes:** las imágenes que genera el estudio ya no usan el límite de subida (un PNG
  de 16 MP pesa más de 20 MiB y no se podía guardar); tienen un tope propio de al menos 160 MiB.

## Resultados en server2

RTX 3090, una GPU por trabajo, tiempos con la carga del modelo:

| Prueba | Tiempo | Resultado |
|---|---|---|
| Crear a 4 MP (2752×1536), calle con letrero | 55 s | Texto exacto con tilde ("Panadería La Esperanza", "Desde 1962"); composición según el prompt. "Desde 1962" salió verde oscuro en vez de negro |
| Editar con instrucción en español (de noche, con lluvia) | 3 min | Mantiene personas, perro y letrero; el expansor reescribe la instrucción viendo la foto |
| Crear a 16 MP (4096×4096), macro de escarabajo | 2,2 min | Detalle real al 100 %: textura del élitro, pelos, ojo compuesto |

Regresión con ComfyUI v0.45.0: Qwen-Image Turbo, títulos animados (H3 Fused i2v), ACE-Step y
Kandinsky 6 (vídeo y voz) funcionan igual.

- **Sin probar:** la edición con varias referencias, el uso de VRAM (cabe en una 3090), H3 r2v,
  los cambios de personaje, YuE2 y SCAIL-2 con la ComfyUI nueva.
