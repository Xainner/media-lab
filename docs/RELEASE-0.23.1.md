# 0.23.1 · Subidas de 1 GiB desde la web

Imágenes `media-lab-web` y `media-lab-agent` 0.23.1. ComfyUI no cambia (0.13.0) ni hay modelos
nuevos. Cambia el runtime (`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye).

## Arreglo

- **Subidas desde la web y la API:** 0.23.0 subió los límites a 1 GiB, pero la capa web seguía
  cortando la petición antes: 21 MiB en `/v1/uploads` (imágenes) y 501 MiB en `/v1/media/uploads`
  (audio y vídeo), con "Solicitud demasiado grande". Ahora esa capa usa los mismos límites que el
  runtime, 1 GiB más 1 MiB para el multipart (`UPLOAD_MAX_BYTES` sigue cambiando el de imagen).
  Las subidas por enlace del MCP no pasaban por ahí y ya aceptaban 1 GiB.
- Detrás de NPM, `client_max_body_size` tiene que ser `1025m` (`deploy/npm-proxy-advanced.conf`).
