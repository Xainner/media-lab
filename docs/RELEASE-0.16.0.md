# 0.16.0 · Instalador con asistente y un worker por GPU

Imágenes `media-lab-web` y `media-lab-agent` 0.16.0. ComfyUI no cambia (0.10.0).

## Asistente del instalador

En una terminal, la primera instalación (`deploy/install.sh` sin configuración guardada) abre un
asistente con menús de flechas (`whiptail`). Sin `whiptail`, o con `MEDIA_LAB_PLAIN=1`, usa
preguntas de texto.

- **Hardware detectado:**
  - cada GPU con su nombre y memoria;
  - la RAM y las CPUs;
  - el espacio libre para modelos.
- **GPUs:** propone un worker por cada GPU de 24 GB o más; también puedes elegir menos.
- **Acceso:**
  - **proxy inverso:** escucha en `127.0.0.1` y pide el nombre público;
  - **red local:** escucha en `0.0.0.0` y propone la IPv4 del servidor con el puerto. La dirección
    se valida antes de seguir.
- **Modelos:** casillas con el tamaño de cada grupo. Vienen marcadas las que caben en el disco, como
  mucho las de `recommended`.
- **Resumen final:** al final muestra un resumen y pide confirmación. Si respondes que no, sale
  sin cambiar nada.

Cada pregunta tiene su opción (`--gpus`, `--listen`, `--origin`, `--models`), así que con `--yes`,
desde scripts o agentes, no se pregunta nada. Las instalaciones existentes no ven el asistente:
usan su configuración guardada.

## Un worker por GPU

- **`--gpus 0,1` o `--gpus all`:** eligen las GPUs. Por defecto se usan todas las de 24 GB o más.
  Cada GPU corre su propio ComfyUI, y un trabajo nunca usa dos.
- **Servicios y puertos:**
  - los workers 0 y 1 siguen siendo `comfyui` y `comfyui-gpu1`;
  - a partir del tercero, el override generado añade `comfyui-gpuN` con su contenedor, sus volúmenes
    y el puerto local `8391+N` (8393, 8394…);
  - cada worker recibe su GPU con `device_ids`.
- **Con una sola GPU:** el segundo worker del compose base queda en un perfil que no se arranca.
  Los trabajos se turnan.
- **Runtime:** lee la lista de workers de `COMFYUI_ENDPOINTS`. Sin esa variable, sigue usando
  `COMFYUI_ENDPOINT` y `COMFYUI_GPU1_ENDPOINT`, así que el host de referencia no cambia.
- **Canciones:** prefieren la GPU 1, y en un host con una sola GPU van a la 0.
- **Capacidades:** `capabilities.image_workers` informa de las GPUs reales.
- **Al arrancar,** el instalador para los workers que sobran de una instalación anterior con más
  GPUs, para que no retengan su GPU.
- **Inactividad y paradas:** la comprobación de inactividad, `stop` y `restart` cubren todos los
  workers.
- **`--single-gpu`:** sigue funcionando y equivale a `--gpus 0`. Una configuración guardada con
  `SINGLE_GPU=1` también se respeta.

## Validación

- **Pruebas:**
  - el reparto entre 1 y 3 workers;
  - una canción en un host de una GPU;
  - la lectura de `COMFYUI_ENDPOINTS`.
- **En un host con 2× RTX 3090,** con `--dry-run` y un directorio temporal:
  - `docker compose config` acepta los overrides de 1, 2 y 3 workers (el de 3 con una GPU 2
    simulada);
  - el asistente se recorrió entero en modo texto y con `whiptail`, incluida la cancelación.
- **Sin probar:** no se ha arrancado un stack real con 1 ni con más de 2 GPUs.
