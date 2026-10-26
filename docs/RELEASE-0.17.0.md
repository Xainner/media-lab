# 0.17.0 · La interfaz web en inglés y español

Imágenes `media-lab-web` y `media-lab-agent` 0.17.0. ComfyUI no cambia (0.10.0). El runtime y la
API no cambian.

## Idiomas

- **Inglés y español:** todos los textos de la interfaz salen de un catálogo con las dos lenguas.
  Esto incluye etiquetas, botones, avisos, errores del navegador y textos de accesibilidad
  (`aria-label`, `title`, `placeholder`). El español sigue siendo el texto original.
- **Idioma al entrar:**
  - si ya elegiste uno en este dispositivo, se usa ese;
  - si no, el primero de `navigator.languages` que sea `es` o `en`;
  - si ninguno coincide, inglés.
- **Selector ES / EN:** está en la tarjeta de acceso, en el menú de la cuenta y en
  **Cuenta → Preferencias**. El cambio se aplica al momento, sin recargar, y actualiza
  `<html lang>`.
- **Dónde se guarda:** en el navegador (`localStorage`, clave `media-lab-locale`). Es una
  preferencia del dispositivo, no de la cuenta: sobrevive al cierre de sesión y ya se aplica en la
  pantalla de acceso.
- **Fechas y números:** se muestran con `Intl` en el idioma activo. Los recuentos usan plural
  ("1 trabajo", "2 trabajos").

## Lo que no se traduce

- **Prompts y contenido:** los prompts e instrucciones que van a los modelos y al proveedor de
  mejora, el brief MCP para agentes (en inglés a propósito) y todo lo que escribe el usuario.
- **Textos del servidor:** las etiquetas, ayudas y errores que llegan del runtime (`capabilities`,
  proveedores, trabajos) se muestran tal cual.
  - Excepción: los nueve formatos de imagen conocidos en Crear se muestran en el idioma activo; un
    formato desconocido conserva la etiqueta del servidor.
- **Valores internos:** las opciones del compositor que el cliente envía o compara (voces, idiomas
  de voz, modos como «Ángulo» o «Escalar») siguen siendo los mismos valores. Solo cambia cómo se
  muestran.
- **Al cambiar de idioma con trabajos en pantalla,** sus etiquetas de modelo y los avisos ya
  mostrados conservan el idioma anterior hasta que la lista se refresca.

## Validación

- **Pruebas:** 71 pruebas de la web en verde, 6 de ellas nuevas:
  - mismas claves en `es` y `en`, sin textos vacíos y con los mismos marcadores;
  - plurales;
  - detección del idioma del navegador y prioridad de la elección guardada;
  - fechas en el idioma activo;
  - el selector, que cambia la interfaz, `<html lang>` y la preferencia guardada.
- **Compilación:** `npm run build` (`tsc --noEmit && vite build`) pasa.
- **Revisión visual:** con la API de pruebas local (`scripts/dev-qa.cjs`) se recorrieron 23
  pantallas en inglés: acceso, Explorar, creadores, Biblioteca, Trabajos, Cuenta, Administración
  y modo avanzado. Solo quedan en español los datos de ejemplo de esa API.
- **Sin probar:** no se ha desplegado ni probado en un host real.
