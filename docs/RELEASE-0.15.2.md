# 0.15.2 · LoRAs sin límite por cuenta

Imágenes `media-lab-web` y `media-lab-agent` 0.15.2. Solo cambia el runtime; el agente sube de
versión con la web. ComfyUI no cambia.

- **Sin tope por cuenta:** la biblioteca de LoRAs ya no tiene el máximo de 30 por cuenta. El espacio
  libre del disco se sigue comprobando en cada descarga.
- **Tope opcional:** un host puede volver a poner uno con la variable `LORA_LIMIT` del runtime.
  `GET /v1/loras` devuelve `limit: null` cuando no hay tope.
- **Por trabajo no cambia:** se siguen usando como mucho 4 LoRAs (`LORA_USE_MAX`), porque se cargan
  a la vez en la GPU.

## Composer de vídeo

- **Arreglo:** los escalados en curso ya no desaparecen de la vista de vídeo al recargarla. La lista
  que reconstruye la vista no incluía la operación `upscale`. Los trabajos seguían en marcha y se
  veían en Trabajos.
