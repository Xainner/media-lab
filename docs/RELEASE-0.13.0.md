# 0.13.0 · Media Lab: rediseño, modelos nuevos, LoRAs y personajes

Rama: `feat/media-lab-studio`, creada desde `main`.

| Servicio | Antes | Después |
| --- | --- | --- |
| `comfyui` (GPU 0) | `comfyui:0.8.0` | `comfyui:0.9.0` (ComfyUI v0.42.5 + nodo `media_lab_stems`) |
| `comfyui-gpu1` | `comfyui:0.8.0` | pendiente: detenido durante el despliegue porque la GPU 1 estaba en uso |
| `runtime` | `web:0.12.0` | `web:0.13.0` |
| `agent` | `agent:0.12.0` | `agent:0.13.0` |

## Cambios

- **Marca Media Lab y web nueva.** Creador único con prompt abajo, chips, lienzo en mosaico, Explorar, Biblioteca, Trabajos y Director nativos. Las vistas avanzadas usan la misma piel. El chip IA mejora el prompt con el proveedor del usuario.
- **Imagen:**
  - MOSS-Image;
  - Qwen-Image 2.1 Turbo;
  - Estructura (ControlNet Union: canny, profundidad, pose o mapa);
  - Ángulo (LoRA QMA);
  - Quitar fondo (instrucción oficial de Qwen).
- **Vídeo:**
  - H3 Turbo (LoRAs LightX2V) y FastH3 Omni;
  - Seguir vídeo (Fun ControlNet-Union 2.0: pose, bordes o profundidad);
  - Cambiar personaje (H3 Character Swap o SCAIL-2) y Cambiar cabeza;
  - Quitar persona;
  - Refinar cara.
  - Chip de **Resolución** en el creador: vista previa, 480p, 720p o nativa.
  - Los cambios de personaje siguen fijos en 480p.
- **Audio:**
  - ACE-Step 1.5 XL Turbo;
  - Separar pistas (Hybrid Demucs, nodo propio).
- **Biblioteca de LoRAs por cuenta.**
  - Se añaden con un enlace de Hugging Face o Civitai: revisión fijada, solo `.safetensors`, máximo 2 GB y comprobación del hash publicado.
  - El tipo se detecta por los tensores: Qwen-Image 2.1 (imagen) o MiniMax H3 (vídeo).
  - Se rechazan los modelos que Civitai marca como de una persona real y los de otras familias.
  - Los archivos se guardan por hash en `~/models/rinari-visual-lab-loras/loras`. La web los escribe en `/user-loras`; ComfyUI los lee por `extra_model_paths` (`media_lab_loras`).
- **Personajes privados.** Cada uno tiene `@nombre`, de 1 a 4 fotos, aspecto y un LoRA opcional. En el creador, `@` los inserta como referencias numeradas y aplica su LoRA. Hay una página Personajes.
- **MCP `0.13.0-mcp-en.1`:**
  - `separate_stems`, `remove_person`, `refine_faces`;
  - `swap_character` (modos `character`, `head` y `scail`);
  - `list_characters`, `list_loras`;
  - `loras` en imagen, edición y vídeo.
- **Agente:** `characters_list`, `audio_stems`, `remove_background`, control de vídeo y SCAIL-2.
- **`package-lock.json`** se regeneró con el npm 10 de `node:22-bookworm-slim`, porque `npm ci` fallaba en la imagen.

## Validación

- **Local:**
  - runtime: suite completa con pytest;
  - web: 59 pruebas con vitest y `tsc`;
  - agente: 31 pruebas;
  - guías MCP sincronizadas.
- **Pesos:** todos los scripts de descarga los verifican por SHA-256 sin fallos.
- **Detección de LoRAs** sobre los archivos reales de Saturno: 6 de H3, 1 de Qwen 2.1 y 2 de Wan rechazados. La resolución de enlaces se probó contra las APIs reales de HF y Civitai.
- **Promoción:**
  - healthchecks sanos;
  - el nodo `MediaLabStems` se carga;
  - ComfyUI ve `/user-loras/loras` y la web puede escribir en esa carpeta;
  - el firewall está activo;
  - la web devuelve 200 y `/mcp` sin token devuelve 401.
- **Smoke en la GPU 0** con trabajos reales del runtime (cuenta del administrador, sesión `smoke-0-13-0`, ruta interna con clave de servicio): 16 de 16 correctos. Revisé un fotograma de cada vídeo.

  | Prueba | Tiempo |
  | --- | --- |
  | imagen turbo / MOSS / estructura | 25 / 35 / 25 s |
  | ángulo / quitar fondo | 90 / 40 s |
  | LoRA Qwen (descarga 42 s) + imagen | 20 s |
  | ACE-Step 30 s / separar pistas | 25 / 5 s |
  | LoRA H3 (descarga 15 s) + vídeo turbo t2v | 80 s |
  | seguir vídeo (pose, turbo) | 166 s |
  | swap de personaje / de cabeza (480p) | 382 / 452 s |
  | quitar persona | 582 s |
  | refinar cara | 121 s |
  | SCAIL-2 | 632 s |

- **Uso real de los LoRAs:** el trabajo guardó `loras: [{file: ml_ad2c20e0…, strength: 0.6}]` y ComfyUI no avisó de claves sin cargar.

## Pendiente

- Recrear `comfyui-gpu1` con `comfyui:0.9.0` cuando la GPU 1 quede libre:

  ```bash
  docker compose --env-file deploy/.web.env -f deploy/compose.yml -f deploy/compose.web.yml up -d --no-build comfyui-gpu1
  ```

  Mientras está detenido, el runtime manda todo a la GPU 0.

## Rollback

- Release: `~/.rinari/releases/20261023-media-lab-0.13.0-583907b/`. Contiene `changed-files.txt`, `deleted-files.txt`, `source-before.tgz` e `images-before.txt`/`images-after.txt`.
- Tags: `rinari-visual-lab-{comfyui,web,agent}:rollback-20261023-media-lab-0.13.0-583907b`.

Para volver atrás:
1. Restaura `source-before.tgz` en `~/rinari-visual-lab`.
2. Ejecuta `up -d --no-build comfyui comfyui-gpu1 runtime agent`.

Las tablas nuevas (`loras`, `characters`) son aditivas: la versión anterior las ignora.
