# 0.14.1 · Rinari Visual Lab pasa a llamarse Media Lab

Rama: `chore/media-lab-rename`, creada desde `main` (`aa7b962`, 0.14.0). No hay funciones nuevas:
cambian los nombres, la configuración del host sale del código y se borran scripts antiguos. Así
el repositorio (`Xainner/media-lab`) se puede publicar.

| Antes | Después |
| --- | --- |
| paquete `rinari_visual_lab` | `media_lab` |
| imágenes `rinari-visual-lab-{web,agent,comfyui}` | `media-lab-{web,agent,comfyui}` (`web`/`agent` 0.14.1; ComfyUI 0.10.0 solo reetiquetada) |
| contenedores y proyecto compose `rinari-visual-lab` | `media-lab` |
| volúmenes `rinari-visual-lab_visual-lab-comfy-*` | `media-lab_comfy-*` |
| `deploy/visual-lab-web.sh` | `deploy/media-lab.sh` |
| unidades `rinari-visual-lab-*` y `/etc/rinari-visual-lab` | `media-lab-*` y `/etc/media-lab` (con `media-lab.env`) |
| base de datos `visual-lab.db` | `media-lab.db` |

## Cambios

- **Configuración del host como variables.** Los compose ya no llevan rutas, dominio ni IPs. Todo
  sale de `MEDIA_LAB_*` en `deploy/.web.env` (plantilla: `deploy/web.env.example`):
  - origen, host, puerto e IP del proxy;
  - carpetas de estado, secretos, modelos, modelos compartidos, LoRAs y H3 Fused.

  `deploy/install.sh` escribe las mismas variables en su `compose.env`.
- **Fuera del código:**
  - la IP del proxy de confianza (`TRUSTED_PROXY_IP`; vacía = no se cree a ningún proxy);
  - la IP que deja pasar el firewall (`/etc/media-lab/media-lab.env`);
  - el host del certificado de origen (`provision-web.py --host`);
  - el dominio del `Message-ID` de los correos.
- **Workers parados a propósito.** `media-lab.sh check-idle` y `renew-origin.py` ya no se bloquean
  si un ComfyUI está parado aposta (como `comfyui-gpu1` ahora).
- **Navegador.** Las claves de `localStorage` pasan de `rinari-visual-lab:` a `media-lab:` una
  sola vez al cargar la web, sin perder preferencias ni la recuperación de trabajos. No cambian
  los tokens MCP ni los prefijos internos `rvl_`.
- **Instalador.** Sus datos van por defecto a `~/media-lab-data`, fuera del checkout: antes
  coincidía con la carpeta del clon y metía estado y secretos en el contexto de `docker build`.
- **Limpieza:**
  - se borran los lanzadores del modo LAN anterior a la web;
  - se borra el entorno de staging;
  - se borran los scripts de rollouts 0.6/0.7.

  Las notas de versión anteriores conservan sus nombres históricos.
- **Marca.** «Rinari Visual Lab» y «Rinari Media Lab» pasan a «Media Lab». Rinari sigue siendo el
  nombre de la agente y la mascota dentro del estudio.

## Despliegue en Saturno

1. **Fase 1, sin corte:**
   - el código nuevo va a `~/media-lab` y el `.web.env` nuevo es privado;
   - copia consistente de la base de datos al release;
   - `~/models/media-lab-fused` contiene solo los dos archivos de H3 Fused, como enlaces duros a los de Maestro;
   - compilación de `media-lab-web` y `media-lab-agent` 0.14.1.
2. **Fase 2, corte de unos 60 s tras comprobar que no había trabajos:**
   - `down` del stack viejo;
   - movimientos:
     - `~/.rinari/visual-lab` → `~/media-lab-data/state` (con `visual-lab.db*` → `media-lab.db*`);
     - los secretos → `~/media-lab-data/secrets`;
     - `~/models/rinari-visual-lab{,-loras}` → `~/models/media-lab{,-loras}`;
   - copia de los seis volúmenes de ComfyUI;
   - firewall y renovación con unidades nuevas: la regla nueva se aplicó antes de quitar la vieja;
   - arranque de `comfyui`, `runtime` y `agent`. `comfyui-gpu1` sigue parado a petición del usuario.

## Validación

- **Local:**
  - runtime: suite completa;
  - web: 63 pruebas, con la migración del prefijo, y `tsc`;
  - agente: 31 pruebas.
- **Tras el corte:**
  - healthchecks sanos;
  - la web pública devuelve 200 y `/mcp` sin token devuelve 401;
  - la regla `media-lab-web-proxy-only` deja pasar solo al proxy;
  - el runtime confía solo en el proxy;
  - los volúmenes nuevos ocupan lo mismo que los viejos.
- **Smoke en la GPU 0** (sesión `smoke-0-14-1`): 5 de 5.

  | Prueba | Tiempo |
  | --- | --- |
  | FLUX 3 borrador / Qwen Turbo | 25 / 20 s |
  | Stable Audio 3 one-shot / voz preset | 10 / 25 s |
  | H3 Turbo t2v con la carpeta nueva de H3 Fused | 75 s |

## Rollback

- Release: `~/media-lab-data/releases/20261024-media-lab-rename-8125345/`. Contiene:
  - copia de la base de datos;
  - imágenes, contenedores y unidades de antes;
  - las unidades y `/etc/rinari-visual-lab` viejos (en `etc/`);
  - `cutover2.log`.
- Tags: `rinari-visual-lab-{web,agent,comfyui}:rollback-20261024-media-lab-rename-8125345`.
- El código viejo sigue en `~/rinari-visual-lab.pre-media-lab` y los volúmenes viejos siguen
  existiendo.

Para volver atrás, hay que deshacer los movimientos de la fase 2 en orden inverso:
1. Parar el stack nuevo.
2. Devolver las carpetas a sus rutas viejas, con `media-lab.db*` → `visual-lab.db*`.
3. Restaurar las unidades viejas desde `etc/`.
4. Ejecutar `up -d --no-build` desde `~/rinari-visual-lab`.
