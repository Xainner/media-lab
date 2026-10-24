# 0.12.0 · Rinari Media Lab y ComfyUI v0.42.5

Rama: `chore/comfyui-v0.42`, creada desde `main`. Es la fase 0 del plan de Media Lab.

| Servicio | Antes | Después |
| --- | --- | --- |
| `comfyui`, `comfyui-gpu1` | `comfyui:0.7.0` (ComfyUI v0.39.0) | `comfyui:0.8.0` (ComfyUI v0.42.5) |
| `runtime` | `web:0.11.0` | `web:0.12.0` |
| `agent` | `agent:0.11.0` | `agent:0.12.0` |

## Cambios

- **Nombre visible: Rinari Media Lab.** Se aplica a:
  - la web (título, marca, pie y las instrucciones para agentes);
  - el servidor MCP y sus guías;
  - los prompts del agente;
  - los correos;
  - el emisor TOTP en las altas nuevas. Las entradas ya guardadas en las apps de autenticación siguen funcionando.

  Los nombres internos no cambian (contenedores, rutas de Saturno, paquete `rinari_visual_lab`, dominio), así que scripts y despliegue siguen igual.
- **ComfyUI v0.39.0 → v0.42.5.** El análisis completo está en [UPGRADE-COMFYUI-0.42.md](UPGRADE-COMFYUI-0.42.md).
  - Trae soporte nativo de MOSS-Image, FLUX 3 Image, CameraAngle, cargadores de LoRA en pila y ReferenceMultiLatent.
  - Para H3: LightVAE y LoRAs sobre el banco PDD.
  - Para Qwen 2.1: corrige su problema con poca VRAM.
  - No hay que cambiar ningún grafo del runtime.
- **Versión del servidor MCP:** `0.12.0-mcp-en.1`.

## Validación

- **Local:**
  - runtime: suite completa con pytest;
  - web: 44 pruebas con vitest y build;
  - agente: 31 pruebas;
  - guías MCP sincronizadas.
- **Imagen nueva en Saturno, en CPU y sin red:**
  - commit `483dae43`, torch 2.12.1+cu130, torchaudio 2.11.0+cu130;
  - los cinco paquetes de nodos cargan sin errores.
- **Esquemas:** comparé `/object_info` de un ComfyUI de prueba solo con CPU contra el de producción, para todos los nodos que usa el runtime. No falta ningún nodo ni cambia ninguna entrada o salida. Hay 11 nodos nuevos y ninguno eliminado.
- **Canario en la GPU 1** (la GPU 0 seguía en 0.7.0), con `creative-smoke.py`: 9 de 9 correctos.

  | Prueba | Tiempo |
  | --- | --- |
  | qwen, qwen-edit | ✓ |
  | song, song-abc, song-plan, song-cover | 2,6–8,8 s |
  | h3-t2v / h3-i2v / h3-r2v | 85,0 / 86,4 / 88,1 s |

- **Promoción:**
  - la GPU 0 pasó a 0.8.0 y runtime y agente a 0.12.0;
  - los contenedores con healthcheck (las dos instancias de ComfyUI y el runtime) quedaron sanos;
  - el firewall está activo;
  - la web devuelve 200 con el título «Rinari — Media Lab» y `/mcp` sin token devuelve 401.
- **GPU 0:** qwen y song generan exactamente los mismos bytes (mismo sha256) que en la GPU 1.

## Rollback

- Release: `~/.rinari/releases/20261023-media-lab-4e6a692/`. Contiene `changed-files.txt`, `source-before.tgz` e `images-before.txt`/`images-after.txt`.
- Tags: `rinari-visual-lab-{comfyui,web,agent}:rollback-20261023-media-lab-4e6a692`.

Para volver atrás:
1. Restaura `source-before.tgz` en `~/rinari-visual-lab`.
2. Ejecuta `up -d --no-build comfyui comfyui-gpu1 runtime agent`.
