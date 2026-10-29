# 0.19.0 · Pika H3 Flex y ComfyUI nuevo

Imágenes `media-lab-web` y `media-lab-agent` 0.19.0 y `media-lab-comfyui` 0.11.0. El runtime cambia
(`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye).

## Perfil H3 Flex

- **Qué es:** [Pika H3 Flex](https://huggingface.co/Pika-Labs/Pika-H3-Flex), los LoRAs de 6 pasos
  de Pika Labs sobre los pesos oficiales de MiniMax H3. Uno es para texto e imagen (FL2VA) y otro
  para referencias (Ref2VA). No hace falta otro modelo base.
- **Cómo corre:** usa la receta de la plantilla de ComfyUI: LoRA a 1.0, `lcm`, CFG 1, las sigmas fijas
  `1.0, 0.972973, 0.923077, 0.8, 0.571429, 0.333333, 0.0` y el VAE de vídeo int8.
- **Límites:** siempre 6 pasos. Rechaza sampler, scheduler, denoise y shifts, y no sigue vídeos
  (control).
- **Dónde aparece:**
  - en el Lab, como modelo «H3 Flex»;
  - en el Director, como opción de clips;
  - en el estudio clásico, en el selector de perfil;
  - en el MCP y en el agente, como `profile=flex`.

  **H3 Turbo sigue siendo el perfil rápido por defecto.**
- **Instalación:** nuevo grupo de modelos `h3-flex` (~4 GB, incluido en el preset recomendado).
  `download-h3-flex-models.sh` fija la revisión `0ddf55a`, comprueba los SHA-256 y guarda el
  LICENSE y el NOTICE de Pika junto a los pesos.

## ComfyUI

- **Versión:** pasa a master `fd7639f` (se identifica como 0.43.0) en la imagen `media-lab-comfyui` 0.11.0.
- **Por qué:** la guía de Pika pide ComfyUI 0.43.2 o posterior para T2V, y esa versión aún no está
  publicada como etiqueta.

## Agente

- **Recuperación al arrancar:** el agente recupera las ejecuciones de cada cuenta hasta que el
  runtime responde. Antes se rendía tras unos 31 s. Tras reiniciar el servidor, el runtime puede
  tardar más de un minuto, y la comprobación de inactividad se quedaba «ocupada» hasta que cada
  usuario volvía a entrar. Cada cuenta se recupera por separado.

## Validación

- **Flex en una RTX 3090** (server2, ComfyUI nuevo, 1344×768, 5 s):

  | Modo | Tiempo | VRAM pico |
  |---|---|---|
  | T2V | 351 s | ~10 GB |
  | I2V | 345 s | ~10 GB |
  | R2V | 468 s (incluye la carga en frío) | ~10 GB |

  Son unos 46–51 s por paso. ComfyUI va pasando partes del modelo desde la RAM, de ahí la VRAM baja.
  Los clips salen nítidos, con audio estéreo de 32 kHz, y mantienen la identidad del primer
  fotograma y de las referencias.
- **Regresión con el ComfyUI nuevo** (server2, por el MCP): funcionan Qwen Turbo (crear y editar),
  MOSS-Image, FLUX 3 Klein, ACE-Step, YuE2, Stable Audio 3 (SFX), Qwen3-TTS, Demucs, H3 Turbo,
  Kandinsky 6 y FlashVSR. Todos los nodos personalizados cargan sin errores.
- **Sin probar con el ComfyUI nuevo:**
  - Qwen Base y BF16, control y ángulos de cámara, quitar fondo;
  - H3 Base, Fused Turbo, Omni y control de vídeo;
  - cambio de personaje y de cabeza, SCAIL-2, refinar caras y quitar persona;
  - el Director.
- **Pruebas:** pasan las del runtime, el agente y la web, y `npm run build` también.
