# Reinstalar el host de referencia

Cómo montar a mano el despliegue del host de referencia (`deploy/media-lab.sh` con
`deploy/.web.env`) en un equipo nuevo, o mover uno existente. Para una instalación nueva
cualquiera es más sencillo `deploy/install.sh` (ver el [README](../README.md)).

## Topología

```
Internet ──https──▶ proxy inverso (p. ej. Nginx Proxy Manager, MEDIA_LAB_PROXY_IP)
                      │  HTTPS verificado contra la CA de origen privada
                      ▼
               host:8390  (uvicorn TLS; el firewall solo acepta al proxy)
                 ├─ media-lab-runtime        web + API (host network)
                 ├─ media-lab-agent          Node, 127.0.0.1:8392
                 ├─ media-lab-comfyui        GPU 0, 127.0.0.1:8388
                 └─ media-lab-comfyui-gpu1   GPU 1, 127.0.0.1:8389
```

Compose de producción: `deploy/compose.yml` + `deploy/compose.web.yml` con `deploy/.web.env`
(privado, no versionado; plantilla en `deploy/web.env.example`). Se controla con
`deploy/media-lab.sh {start|stop|restart|status|check-idle|bootstrap|logs}`.

## Qué está en git y qué no

| Versionado | Fuera de git (respaldar aparte) |
|---|---|
| Código del runtime, la web y el agente | `deploy/.web.env` |
| Dockerfiles, compose, unidades systemd | Secretos: `MEDIA_LAB_SECRETS_DIR` |
| Workflows ComfyUI y bundles | Estado: `MEDIA_LAB_STATE_DIR` (SQLite, artefactos, agent-runs) |
| Scripts de descarga con SHA fijado | Pesos de los modelos |
| Config avanzada de NPM | CA de origen copiada en el proxy |

## Requisitos del host

- Linux con Docker Compose 2.24.4+ y NVIDIA Container Toolkit.
- 2 GPUs de 24 GB (probado con 2× RTX 3090) y un driver compatible con CUDA 13.
- Espacio para los modelos que elijas (de ~44 GB a ~310 GB) y para los artefactos.
- Los contenedores web y agente corren como uid 1000: el estado, los secretos y la carpeta de
  LoRAs deben pertenecer a ese uid.

## Pasos

1. Clonar el repo (o copiar el código) en `~/media-lab`.
2. `cp deploy/web.env.example deploy/.web.env` y ajustar todas las variables `MEDIA_LAB_*`:
   origen y host público, IP del proxy, carpetas de estado, secretos, modelos, modelos
   compartidos, LoRAs y H3 Fused.
3. Descargar los modelos con `deploy/scripts/download-*.sh`, exportando
   `MEDIA_LAB_MODELS_DIR` (y `H3_SHARED_ROOT` / `H3_FUSED_HOST_ROOT` para H3).
4. Secretos y estado:
   - **Migración** (conservar usuarios y galería): con el stack detenido
     (`media-lab.sh stop`), copiar las carpetas de secretos y de estado con permisos
     `0700/0600`.
   - **Instalación limpia**: `python3 deploy/scripts/provision-web.py <dir-nuevo> --host <host>`
     genera la CA, el certificado de origen, `master.key` y `agent.key`. Después,
     `media-lab.sh bootstrap` crea el primer administrador.
5. Construir las imágenes:
   `docker compose --env-file deploy/.web.env -f deploy/compose.yml -f deploy/compose.web.yml build`.
6. Firewall y renovación del certificado de origen:
   - Crear `/etc/media-lab/media-lab.env` con `MEDIA_LAB_PROXY_IP`, `MEDIA_LAB_PORT`,
     `MEDIA_LAB_STATE_DIR` y `MEDIA_LAB_SECRETS_DIR`.
   - Copiar `deploy/scripts/web-firewall.sh` y `deploy/scripts/renew-origin.py` a `/etc/media-lab/`.
   - Instalar en `/etc/systemd/system` las unidades `media-lab-web-firewall.service` y
     `media-lab-origin-renew.{service,timer}`, y `deploy/docker-web-firewall.conf` como
     `docker.service.d/media-lab-web-firewall.conf`.
   - `web-firewall.sh` solo deja entrar al puerto desde `MEDIA_LAB_PROXY_IP`.
7. `deploy/media-lab.sh start` y comprobar `status`.

## Proxy inverso (Nginx Proxy Manager)

- Scheme `https`, forward a `host:8390`.
- Certificado público (Let's Encrypt), Force SSL; sin caché ni websockets.
- Advanced: contenido de `deploy/npm-proxy-advanced.conf`, con tu host en `proxy_ssl_name`.
- Copiar `origin-ca.crt` de los secretos al proxy (es un certificado público, no una clave). Si
  se regenera la CA, hay que reemplazarlo.

## Verificación

- `deploy/media-lab.sh status`: `comfyui`, `comfyui-gpu1` y `runtime` sanos.
- La web devuelve 200 y `/mcp` sin token devuelve 401.
- `nvidia-smi` debe mostrar un worker ComfyUI por GPU durante un trabajo.
