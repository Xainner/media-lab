# 0.20.0 · Borrado real

Imágenes `media-lab-web` y `media-lab-agent` 0.20.0 y `media-lab-comfyui` 0.12.0. El runtime cambia
(`media-lab-runtime`, misma etiqueta 0.6.0; se reconstruye).

Hasta ahora, borrar en el estudio solo quitaba el archivo. El prompt seguía en el historial de
trabajos, ComfyUI guardaba una copia de cada entrada y salida, y no había forma de borrar una
conversación ni una ejecución del agente. Desde esta versión, borrar no deja rastro.

## Qué borra cada acción

| Acción | Dónde | Borra |
|---|---|---|
| Borrar archivo | Biblioteca, lightbox, MCP `delete_media` | El archivo y todo lo que solo existía por él. Si era la última salida de su trabajo, también el trabajo con su prompt y sus ajustes. Además, sus enlaces de transferencia y sus menciones en mensajes, personajes y ejecuciones del agente. |
| Borrar trabajo (nuevo) | Trabajos, MCP `delete_job` | Un trabajo terminado con todas sus salidas, su prompt y sus ajustes. Los archivos que usó como referencia se conservan. |
| Borrar conversación (nuevo) | Agente, MCP `delete_session` | Los mensajes, las ejecuciones del agente y todos los trabajos y archivos de esa conversación. |
| Borrar ejecución (nuevo) | Agente, MCP `delete_agent_run` | El registro de una ejecución terminada, los mensajes que añadió y lo que heredaron las ejecuciones posteriores (sus trabajos y su texto en el historial). Los archivos que creó siguen en la biblioteca. |

- **Si quedan otras salidas:** cuando un trabajo tiene varias (por ejemplo, las pistas separadas de
  una canción), su prompt se conserva hasta borrar la última, porque también es de ellas.
- **Conversaciones vacías:** si al borrar un trabajo su conversación queda sin nada, también se
  borra. Si queda algo y su título era el prompt borrado, vuelve a "Nueva sesión".
- **Trabajos activos:** nada se borra mientras un trabajo activo lo usa. Las conversaciones y las
  ejecuciones con trabajo en curso tampoco.
- **Mensajes del agente:** ahora guardan el id de su ejecución. Los anteriores a esta versión se
  identifican por su contenido exacto.

## ComfyUI ya no guarda copias

- **Al terminar cada trabajo:** el runtime borra lo que el trabajo subió a `input/`, lo que guardó en
  `output/media_lab/` y su entrada del historial de ComfyUI. Esto lo hace un nodo propio y mínimo
  (`media_lab_cleanup`) que solo puede tocar `input/job_*`, `output/media_lab/` y `temp/`.
- **Restos de trabajos interrumpidos:** cuando una GPU queda libre, se barren los que tengan más de
  un día.

## Cuentas

- **Borrado de cuenta:** fallaba en cuanto había algún correo enviado; el buzón vacía el contenido
  de los correos ya enviados y el borrado intentaba descifrarlo. Ahora los salta.
- **Auditoría:** el correo de la persona borrada desaparece del registro de auditoría.

## Higiene

- **SQLite:** sobrescribe con ceros lo que se borra (`secure_delete`) y vacía el WAL después de cada
  borrado.
- **Permisos:** la base de datos y los archivos nuevos del estado son privados del usuario del
  servicio (`umask 077`, base de datos en 600).
- **Logs:** los contenedores rotan sus logs (3 × 10 MB). El runtime ya no registra cada consulta a
  ComfyUI; en server2 el log había llegado a 261 MB en 6 días.

## Validación

- **Pruebas:**
  - runtime (incluye `test_erasure.py` y `test_comfy_cleanup.py`, y una prueba del borrado de
    cuenta con correo enviado que falla sin el arreglo);
  - agente (borrar ejecuciones y conversaciones, `forget`);
  - web y `npm run build`.
