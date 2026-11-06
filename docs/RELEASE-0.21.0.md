# 0.21.0 · Atención dispersa para H3

Imágenes `media-lab-web` y `media-lab-agent` 0.21.0. `media-lab-comfyui` no cambia (0.12.0). El
runtime cambia (`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye). No hay modelos nuevos
que descargar.

Los vídeos de MiniMax H3 pueden renderizarse con atención dispersa, una opción para ir más rápido.
Por defecto sigue la atención densa, como hasta ahora.

## Cómo se usa

| Dónde | Cómo |
|---|---|
| Web | Ajuste **Atención → Densa / Dispersa** en los modelos H3 (no aparece con Kandinsky 6) |
| API y MCP | `options.attention: "dense" \| "sparse"` en `generate_video` |
| Director | `video_options.attention` se aplica a todas las escenas |

- **Qué hace:** inserta el nodo `BlockSparseAttention` del núcleo de ComfyUI justo antes del
  guider, después de toda la cadena del modelo (LoRAs, desplazamiento de sigmas y control de vídeo).
- **Método por perfil:**
  - FastH3 Omni usa VSA al 10 %, el patrón con el que se entrenó su checkpoint;
  - Base, Turbo, Fused Turbo y Flex usan sol-attn, que no necesita entrenamiento, con los valores
    por defecto del nodo;
  - SLA no se usa, porque ningún checkpoint ni LoRA instalado está entrenado para SLA.
- **Primeros pasos densos:** los primeros pasos del muestreo siguen siendo densos (empieza al 20 %).
  El log de ComfyUI dice en qué bloques entró la atención dispersa.
- **Huellas de idempotencia:** el valor por defecto (`dense`) no se guarda en la petición, así que
  las peticiones anteriores conservan su huella.
- **Capacidades:** `/v1/capabilities` lista `["dense", "sparse"]` en `video.attention` y en cada
  perfil.

## Mediciones

RTX 3090, 720p, 5 s, misma semilla:

| Perfil | Densa | Dispersa |
|---|---|---|
| Fused Turbo | 36.1 s/it · 177.8 s en total (modelo ya cargado) | 15.7 s/it · 160.1 s en total (con carga en frío) |
| FastH3 Omni (referencias) | 40.0 s/it · 370.8 s en total | 25.5 s/it · 257.8 s en total |

- **Velocidad:** el muestreo va unas 2.3× más rápido en Fused Turbo y unas 1.6× en Omni.
- **Calidad:** en la comparación por fotogramas, la dispersa mantuvo la composición y la identidad
  de la densa.
- **Sin medir:** Base, Turbo y Flex. La guía del modelo pide no prometer una mejora de velocidad ahí.

## Validación

- **Pruebas:**
  - runtime, con el nuevo `test_h3_sparse.py`: colocación del nodo por perfil, VSA en Omni,
    sol-attn en el resto, orden después del control de vídeo, huella sin cambios por defecto y
    rechazo en Kandinsky 6;
  - agente;
  - web, con `npm run build` y vitest.
- **Generadores:** `sync-model-options.py --check` y `sync-mcp-guides.py --check`.
- **server2:** los dos ComfyUI exponen `BlockSparseAttention`, y las mediciones de arriba son de
  trabajos reales en ese servidor.
