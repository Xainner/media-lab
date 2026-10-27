# 0.17.1 · La interfaz en el teléfono

Imágenes `media-lab-web` y `media-lab-agent` 0.17.1. ComfyUI no cambia (0.10.0). El runtime y la
API no cambian.

## Arreglos en pantallas pequeñas

- **Menú de la cuenta:** quedaba debajo del compositor y tapaba la parte de abajo (idioma y
  cerrar sesión). Ahora la barra superior va por encima del compositor.
- **Menús del compositor:** modo, formato y modelo se abren desde el borde izquierdo de su botón.
  En el teléfono el menú de modo se salía por la derecha; ahora se recoloca dentro de la pantalla.
- **Biblioteca y galería:** en un teléfono medían unos 565 px y se cortaban a la derecha, porque la
  rejilla de la página crecía al ancho de la fila de filtros. Ahora caben, y los filtros se
  desplazan de lado.
- **Pestañas:** la sección actual se desplaza a la vista, así que Director, Biblioteca y Personajes
  ya no quedan escondidos al final de la barra.

## iPhone

- **Sin zoom al escribir:** Safari en iOS hace zoom al enfocar un campo con letra menor de 16 px.
  En iOS, los campos usan ahora al menos 16 px.
- **Zonas seguras:** la barra superior y el compositor respetan el notch y la barra de inicio
  (`env(safe-area-inset-*)`).

## Validación

- **Pruebas:** las 71 pruebas de la web pasan, y `npm run build` también.
- **Navegador a 375×812** (emulación táctil, API de pruebas local):
  - la biblioteca cabe;
  - el menú de modo queda dentro de la pantalla;
  - el menú de la cuenta llega hasta cerrar sesión;
  - la pestaña activa se ve;
  - ninguna de las 26 rutas tiene elementos fuera de la pantalla.
- **Sin probar en un iPhone real:** el zoom y las zonas seguras solo cambian en Safari de iOS.
