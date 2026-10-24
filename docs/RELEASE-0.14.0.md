# 0.14.0 · FLUX 3 Klein, Kandinsky 6, Stable Audio 3 y Qwen3-TTS

Rama: `feat/media-lab-models-2`, creada desde `main` (`d0d67eb`, 0.13.0).

| Servicio | Antes | Después |
| --- | --- | --- |
| `comfyui` (GPU 0) | `comfyui:0.9.0` | `comfyui:0.10.0` (nodos Kandinsky 6 y `media_lab_tts`) |
| `comfyui-gpu1` | `comfyui:0.9.0` (detenido) | `comfyui:0.10.0`, detenido de nuevo a petición del usuario tras el smoke |
| `runtime` | `web:0.13.0` | `web:0.14.0` |
| `agent` | `agent:0.13.0` | `agent:0.14.0` |

## Cambios

- **Los cuatro modelos marcados «Pronto» ya funcionan.** Cada uno tiene su script de descarga con revisión fijada y SHA-256 verificado (`deploy/scripts/download-{flux3-klein,kandinsky6,stable-audio3,qwen3-tts}-models.sh`).
- **FLUX 3 Image Klein (imagen y edición).**
  - Modelo destilado de 16 pasos (borrador) y modelo base de 50 pasos (calidad), los dos int8 ConvRot.
  - El prompt lo reescribe el upsampler oficial (Qwen3.5 9B w4a8) con las instrucciones de la plantilla oficial. La edición compone de 1 a 4 imágenes con `ReferenceMultiLatent`.
  - Es un repositorio gated: hay que aceptar la FLUX Kommunity License en Hugging Face, y el token fine-grained necesita acceso a repositorios gated.
- **Kandinsky 6.0 Lite Distill (vídeo con audio).**
  - Clips de 5 s a 864×480 (16:9 o 9:16), desde texto o desde una imagen inicial, con audio de 44 kHz sincronizado y lip-sync. Las frases habladas van en el prompt como `<S>texto<E>` y la voz y los sonidos en `audio_prompt`.
  - Usa los nodos oficiales de la extensión fijada en `6b8d345`.
  - El «beautifier» reutiliza `qwen3.5_9b_w4a8_gptq`.
  - El VAE de audio de MMAudio es CC-BY-NC.
- **Stable Audio 3 (`/v1/jobs/sound`).**
  - Música instrumental (5–380 s), instrumento (2–380 s), efectos (1–120 s) y one-shots (0,5–10 s).
  - Usa Medium o Small SFX en 8 pasos. Qwen3.5 2B reescribe la idea con el prompt oficial de cada categoría.
- **Qwen3-TTS 12Hz 1.7B (`/v1/jobs/speech`).**
  - Tres modos: 9 voces preset, voz diseñada a partir de una descripción y clon de una referencia de 3–30 s. Habla 10 idiomas.
  - El clon solo se admite con `consent=true` (permiso de la persona dueña de la voz).
  - Nodo propio `MediaLabSpeech`. qwen-tts 0.1.1 necesita transformers 4.57, así que cada trabajo corre `worker.py` en un subproceso con `/opt/qwen-tts` delante en `PYTHONPATH`. La imagen mantiene transformers 5.20.2, torch 2.12.1+cu130 y numpy 2.4.6.
- **MCP `0.14.0-mcp-en.1`:**
  - herramientas nuevas `generate_sound` y `generate_speech`;
  - `model=flux3` en `generate_image` y `edit_image`;
  - `model=kandinsky6`, `audio_prompt` y `literal_prompt` en `generate_video`;
  - guías y `docs/MCP-GUIDE.md` / `docs/MODEL-CONTROLS.md` sincronizados.
- **Agente:** herramientas `audio_sound` y `audio_speech`, FLUX 3 en `image_generate`/`image_edit` y Kandinsky 6 en `video_generate`. Antes de clonar una voz, pide confirmación del permiso.
- **Web:**
  - los cuatro modelos pasan de «Pronto» a «Nuevo»;
  - chips de tipo de sonido, duración, voz, locutor e idioma;
  - subida de voz con «Tengo permiso»;
  - modos de Kandinsky;
  - las apps de Explorar abren su página;
  - el texto de Qwen Turbo dice «8 pasos».
- **README e instalador:** `README.md` reescrito para presentar Media Lab, `deploy/install.sh` para instalar en otros servidores y guía de instalación para agentes en `AGENTS.md`.
- **Corrección:** `ComfyClient.output_text` buscaba el `prompt_id` dos veces en el historial y siempre devolvía vacío. Ahora la reescritura del upsampler se guarda en `compiled_prompt`.

## Validación

- **Local:**
  - runtime: suite completa con pytest, con pruebas nuevas de FLUX 3, Kandinsky 6, Stable Audio 3, voz y `output_text`;
  - web: 62 pruebas con vitest y `tsc`;
  - agente: 31 pruebas.
- **Pesos:** los cuatro scripts terminan con todos los SHA-256 verificados en Saturno.
- **Imagen nueva en CPU:**
  - los nodos cargan sin errores de importación;
  - `MediaLabSpeech` generó 3,1 s de voz (preset «serena», en español) en 40 s;
  - transformers 5.20.2 en la imagen y 4.57.3 en `/opt/qwen-tts`.
- **Promoción:**
  - healthchecks sanos;
  - firewall activo;
  - la web pública devuelve 200 y `/mcp` sin token devuelve 401;
  - las capacidades marcan listos FLUX 3 (borrador y calidad), Kandinsky 6, los cuatro tipos de sonido y las tres voces.
- **Primer intento de smoke:** Saturno se reinició solo al empezar. El usuario tenía las dos GPU al máximo y la carga total tumbó el servidor. No hubo errores de software y el trabajo quedó como «interrumpido».
- **Smoke en la GPU 0** con `comfyui-gpu1` detenido, trabajos reales del runtime (cuenta del administrador, sesión `smoke-0-14-0`) y uno cada vez: 11 de 11 correctos. Pico de 250 W, 73 °C y 21,4 GB. Revisé las imágenes y un fotograma de cada vídeo, y medí el nivel de cada audio.

  | Prueba | Tiempo |
  | --- | --- |
  | FLUX 3 borrador / calidad / edición | 30 / 45 / 20 s |
  | Stable Audio 3: música 30 s / efecto 6 s / one-shot 1,5 s | 15 / 5 / 5 s |
  | voz preset / diseñada / clon (de la voz sintética preset) | 25 / 25 / 20 s |
  | Kandinsky 6 desde texto con frase / desde imagen | 201 / 206 s |

- **Corrección de `output_text`:** se desplegó solo el runtime y la verifiqué con un one-shot. Su `compiled_prompt` ya trae la reescritura de Qwen.

## Pendiente

- Volver a encender `comfyui-gpu1` cuando el usuario lo indique. Mientras tanto, el runtime manda todo a la GPU 0:

  ```bash
  docker compose --env-file deploy/.web.env -f deploy/compose.yml -f deploy/compose.web.yml up -d --no-deps --no-build comfyui-gpu1
  ```

## Rollback

- Release: `~/.rinari/releases/20261024-media-lab-0.14.0-a40bf45/`. Contiene `changed-files.txt`, `source-before.tgz` e `images-before.txt`/`images-after.txt`.
- Tags: `rinari-visual-lab-{comfyui,web,agent}:rollback-20261024-media-lab-0.14.0-a40bf45`.

Para volver atrás:
1. Restaura `source-before.tgz` en `~/rinari-visual-lab`.
2. Ejecuta `up -d --no-build comfyui runtime agent`.

No hay cambios de esquema en la base de datos. Los trabajos `sound` y `speech` ya guardados quedan como historial y la versión anterior no los reanuda.
