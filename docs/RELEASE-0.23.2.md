# 0.23.2 · Sonidos cortos y errores de ComfyUI

Imágenes `media-lab-web` y `media-lab-agent` 0.23.2. ComfyUI no cambia (0.13.0) ni hay modelos
nuevos. Cambia el runtime (`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye).

## Arreglos

- **Golpes de menos de 1 s:** `generate_sound` anunciaba `one_shot` de 0,5 a 10 s, pero el nodo
  `EmptyLatentAudio` de ComfyUI no acepta menos de 1 s. Un golpe de 0,6 s se aceptaba y terminaba
  sin audio ("ComfyUI completed without an output in audio"). Ahora `one_shot` va de 1 a 10 s en
  el contrato, `capabilities`, las guías y el agente, y lo más corto se rechaza al pedirlo.
- **Grafos válidos solo en parte:** si alguna salida del grafo no pasa la validación, ComfyUI
  igual ejecuta las que sí y devuelve los errores en `node_errors`. El runtime ya no lo deja
  correr: lo saca de la cola y falla el trabajo con el error real de ComfyUI (nodo, tipo y
  motivo) en lugar de "completed without an output".
