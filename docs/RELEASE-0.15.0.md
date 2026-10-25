# 0.15.0 · Guías de prompts para todos los modelos y botón IA por modelo

Rama: `docs/model-prompt-guides`, creada desde `main` (`f51dfe5`, 0.14.2). Imágenes `media-lab-web`
y `media-lab-agent` 0.15.0; ComfyUI sin cambios (0.10.0).

## Guías nuevas

Seis guías nuevas en `model_guides.py`, escritas a partir de las fuentes oficiales de cada modelo
(revisadas el 2026-10-24; el docstring las lista):

| Modelo | Tema de `prompt_guide` | Fuente principal |
| --- | --- | --- |
| MOSS-Image | `image` | Prompt enhancer oficial de OpenMOSS y USERGUIDE |
| FLUX 3 Klein | `image`, `edit` | Upsampler y guías de prompting de BFL |
| Kandinsky 6 | `video` | Prompts del beautifier en la extensión oficial (`6b8d345`) |
| ACE-Step 1.5 | `music` | Tutorial e INFERENCE de ACE-Step, nodos de ComfyUI |
| Stable Audio 3 | `sound` (nuevo) | Guía de prompting y reprompt de Stability |
| Qwen3-TTS | `speech` (nuevo) | README, ejemplos y paquete `qwen_tts` |

- Los recursos MCP pasan de `rinari://guides/...` a `media-lab://guides/<tema>`, uno por tema.
- El resumen del agente, el resumen del MCP y la herramienta `prompt_guide` del agente cubren
  todos los modelos.

## Auditoría de las guías existentes

Se revisaron contra sus fuentes:
- **Qwen imagen:**
  - longitud oficial de unas 400–500 palabras;
  - tono prudente con lo que se inventa;
  - formato según el sujeto;
  - 2K para texto denso;
  - ejemplo más largo.
- **Qwen edición:**
  - distingue entre cambiar la foto y crear una imagen nueva del sujeto;
  - regla oficial para elegir la imagen lienzo, que va primero;
  - el ejemplo de dos imágenes estaba al revés.
- **H3:**
  - longitudes de las descripciones;
  - límites oficiales de Ref2VA;
  - fila de control de vídeo;
  - funciones disponibles al día;
  - mapa de perfiles sin contradicción;
  - aviso de que las pistas de los vídeos de referencia siempre cuentan como `<Audio>`.
- **YuE2:**
  - el modo por defecto de la API es `direct`;
  - `max_duration` es un tope de 120 s;
  - ABC de melodía sin acordes.
- **Director:**
  - cualquier escena puede durar menos de 5 s;
  - `partially_copy` cuando el fragmento no cubre el clip.
- **Controles MCP:**
  - shifts por perfil (Turbo usa 6/3);
  - `ref_image_size=match` en Turbo y Omni;
  - SheetSage2.

## Botón IA del composer

- **Canciones (YuE2 y ACE-Step).** Con IA activa, la primera caja es la idea de la canción y la
  IA escribe el estilo y la letra. Si escribes letra, se respeta tal cual.
  - Antes la caja se enviaba como «Estilo». Sin letra, un proveedor pequeño cantaba la propia
    descripción.
  - Con ACE-Step la IA también propone BPM, tonalidad, compás e idioma.
- **Cada modelo usa su guía:**
  - MOSS: caption completo;
  - Kandinsky: escena en inglés con las frases habladas literales y `audio_prompt`; su
    beautifier no traduce;
  - Qwen, H3 y Estructura: como antes.
- **FLUX 3 Klein no usa el botón**, igual que Stable Audio 3 y Qwen3-TTS: su upsampler oficial
  ya reescribe en inglés.

## Arrastrar y soltar en el composer

- **Las imágenes** van a las referencias del modo.
- **El audio o el vídeo** van a la fuente del modo: la canción del cover o de Separar pistas, la
  voz a clonar, el vídeo de los swaps o de Seguir vídeo. Antes solo entraban con el botón.
- **Si el modo no usa ese tipo de archivo**, se avisa en lugar de subirlo.
- **Al arrastrar**, un resaltado dice qué se puede soltar.
- **Un archivo soltado fuera del composer** ya no se abre en la pestaña: antes se perdía lo
  escrito.

## Runtime

- **ACE-Step:**
  - los BPM y la tonalidad escritos en `style` se usan como parámetros y se quitan del caption;
  - nuevo `time_signature` (2, 3, 4 o 6);
  - límites oficiales de 512 caracteres de estilo y 4096 de letra.
- **H3 r2v (límites oficiales):**
  - necesita una imagen o un vídeo;
  - como mucho 12 referencias;
  - audios de 2 a 15 s;
  - 15 s de vídeo y 15 s de audio en total.
- **Transparencia:** la frase RGBA es ahora la oficial de Qwen-Image 2.1, sin punto doble.
- **`check_prompt`:** avisa de prompts de Qwen con menos de 200 palabras.

## Pendiente

- Probar las LoRAs Turbo de LightX2V publicadas el 2026-10-20 (FL2VA 8 pasos v1.1, Ref2VA 4 pasos).
- MOSS-Image solo crea desde texto. Las LoRAs de edición de la comunidad son de esta semana y
  no están probadas.
