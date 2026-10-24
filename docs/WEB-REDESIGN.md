# Rediseño de Media Lab

Desarrollado localmente y desplegado en Saturno el 1 de octubre de 2026. Se mantienen los cambios que ya existían en el repositorio y la navegación de Electron.

## Interfaz

La web tiene un shell propio con enlaces directos, historial del navegador, menú móvil, búsqueda de pantallas y herramientas que conservan formularios y trabajos al navegar. La sesión de una cuenta determina el espacio montado; al cerrar sesión o caducar se retiran streams, previews y preferencias del navegador.

Se incluyen Inicio, Agente, Crear imagen, Editar imagen, Vídeo, Música, Director, Galería, Biblioteca y Trabajos; cuatro pantallas de cuenta y seis de administración. Los flujos de invitación, recuperación, restablecimiento y TOTP comparten el nuevo login.

El tema negro/ciruela/violeta carga Outfit e Inter localmente. Los recursos originales de Rinari se generaron para este proyecto; la chibi fue corregida tras la revisión del usuario. El logo y favicon usan un nuevo retrato PNG de Rinari con transparencia, generado a partir de las referencias. El wordmark SVG incorpora esa imagen junto al nombre. Las referencias originales no se publican.

Animate UI se incorporó desde su registro oficial para sidebar, diálogos, sheets, tabs, menús, acordeones, progreso, botones y tooltips. Los archivos vendorizados tienen adaptaciones `forwardRef` para React 18; el instalador preserva estas adaptaciones al ejecutarse nuevamente. El tema, Tailwind y Motion pertenecen al entrypoint web. Las licencias distribuidas están en `apps/web/public/licenses`, incluida la licencia MIT con Commons Clause de Animate UI, MIT de shadcn/ui y OFL de las fuentes.

Los controles tienen foco visible, nombres accesibles, navegación por teclado y respeto a `prefers-reduced-motion`. Usuarios pasa de tabla a tarjetas en móvil. Los resultados, referencias, audio, vídeo y storyboard muestran previews. Las generaciones directas conservan parámetros, perfil H3, exportaciones y lógica de trabajos existente.

Los argumentos/resultados del agente, el análisis del Director y el estado del sistema se presentan como campos y listas. SMTP y usuarios usan tarjetas y tablas. No hay visores de JSON, incluidos los ajustes avanzados. Los prompts y letras conservan exactamente su texto, incluso si el usuario escribió una descripción que contiene sintaxis JSON. ABC continúa como notación musical avanzada.

## Proveedores

`saved_providers` guarda una clave cifrada y configuración por cuenta y endpoint compartido o personal. `user_providers` conserva la selección activa y la interfaz utilizada por el agente y el bridge. La migración `INSERT OR IGNORE` preserva la configuración anterior y es idempotente.

| Método | Ruta | Función |
|---|---|---|
| GET | `/v1/account/providers` | Conexiones guardadas y selección activa, sin claves |
| PUT | `/v1/account/providers/{eid}` | Guardar clave/configuración, sin exigir modelo previo |
| DELETE | `/v1/account/providers/{eid}` | Retirar la conexión propia |
| GET | `/v1/account/providers/{eid}/models` | Consultar `/models` desde el servidor |
| POST | `/v1/account/providers/activate` | Activar `{endpoint_id, model}` |
| POST | `/v1/account/provider/test` | Verificar conversación, herramientas y visión |

Se conserva HTTPS, resolución pública, TLS y conexión al destino DNS validado. El descubrimiento tiene timeout y respuesta limitada, no sigue redirects ni devuelve secretos. El selector permite búsqueda y actualización; un catálogo vacío o no compatible permite introducir el identificador manualmente. Un proveedor desactivado sigue visible para retirar su conexión.

Cambiar clave o modelo invalida las pruebas. No se deducen capacidades por nombres. Las admisiones y ejecuciones activas impiden cambiar la selección o desactivar su endpoint en API; la UI bloquea los controles durante la ejecución. Se conservan los endpoints anteriores de proveedor activo.

## Administración

Usuarios incluye búsqueda, filtros, rol, estado, almacenamiento y conteos de trabajos. El panel lateral separa identidad, recursos y seguridad. Se puede cambiar nombre y rol, límites de concurrencia, cupo diario y almacenamiento, consultar/revocar sesiones, desactivar, reactivar y enviar recuperación.

| Método | Ruta | Función nueva |
|---|---|---|
| GET/PUT | `/v1/account/profile` | Perfil propio / cambio de nombre |
| PUT | `/v1/admin/users/{uid}` | Nombre y rol |
| GET | `/v1/admin/users/{uid}/sessions` | Sesiones del usuario |
| DELETE | `/v1/admin/users/{uid}/sessions/{sid}` | Revocar sesión; `all` revoca todas |
| GET | `/v1/admin/invitations` | Estado de invitaciones sin tokens |
| POST | `/v1/admin/invitations/{iid}/resend` | Reenviar con enlace nuevo |
| DELETE | `/v1/admin/invitations/{iid}` | Revocar invitación |
| PUT | `/v1/admin/providers/{eid}/enabled` | Reactivar o desactivar endpoint aprobado |
| POST | `/v1/admin/users/{uid}/delete` | Solicitar eliminación definitiva |
| GET | `/v1/admin/deletions` | Operaciones persistentes |
| POST | `/v1/admin/users/{uid}/delete/retry` | Reintentar una operación fallida |

Cambiar nombre actualiza las identidades de acceso; cambiar rol revoca sesiones. Se impide perder el último administrador habilitado. Administración exige TOTP. El registro sigue siendo exclusivamente por invitación. No se añade acceso administrativo a archivos, conversaciones ni claves privadas de otras cuentas.

## Eliminación definitiva

La solicitud exige nombre exacto del objetivo, contraseña del administrador y código TOTP/recuperación válido reciente. No permite autoeliminación administrativa ni retirar el último administrador habilitado. Responde 202 y persiste su estado antes de iniciar la limpieza.

Se bloquea el acceso, revocan sesiones/enlaces y solicitan cancelaciones. La limpieza espera las solicitudes HTTP ya admitidas, los trabajos asignados/en ejecución y las ejecuciones/admisiones del agente. El endpoint interno `/purge` del agente exige su autenticación de servicio y propietario; se niega a crear trabajo nuevo para la cuenta bloqueada.

La purga valida que cada ruta de sesión pertenece al root de artefactos y no redirige a otro directorio. Retira archivos, conversaciones, medios, preferencias, configuraciones cifradas, identidades y datos privados del agente. Un fallo conserva una operación recuperable y permite reintento; el estado `waiting` se procesa automáticamente tras la detención. Se mantiene un registro mínimo de auditoría y el estado final.

El runtime se utiliza con un solo proceso de autoridad, como en los scripts existentes; el conteo de solicitudes en curso pertenece a ese proceso. No ejecutar múltiples workers de Uvicorn sobre el mismo estado sin una barrera distribuida equivalente.

## Validación ejecutada

| Comprobación | Resultado |
|---|---|
| `npm --prefix apps/desktop run build:web` | TypeScript y build web correctos |
| `npm --prefix apps/desktop run build` | TypeScript y build Electron correctos |
| `npm --prefix apps/desktop run test:electron` | 36 pruebas correctas |
| `npm --prefix apps/desktop run test:renderer` | 15 pruebas correctas |
| `npm --prefix apps/desktop run test:web` | 10 pruebas correctas |
| Runtime: `python -m pytest services/runtime/tests -o addopts='' -q` | 93 correctas, 1 omitida |
| `node --test services/agent/purge.test.cjs services/agent/recovery.test.cjs` | 4 pruebas correctas |

En PowerShell, el runtime requiere `$env:PYTHONPATH='services/runtime/src'` antes del comando de pruebas. La omisión corresponde a la creación de symlinks, que exige Developer Mode en este Windows. La prueba del agente con junctions/symlinks sí se ejecutó y pasó.

Las pruebas incluyen aislamiento entre cuentas, autenticación/invitaciones/reset/TOTP, sesiones y CSRF; migración, catálogos válidos/vacíos/no compatibles, credenciales/selección/capacidades; identidad, roles, protección de administrador, invitaciones y revocación; eliminación con trabajos activos, solicitudes en curso, fallo parcial, reintento y preservación de otra cuenta. Renderer verifica edición de prompts y H3. Web verifica conservación de formularios al navegar, modelos manuales/descubiertos, bloqueo durante ejecución, conexiones desactivadas, texto exacto, errores legibles y caducidad/cambio de cuenta durante uploads.

Se recorrieron las 20 rutas en el navegador integrado a 390, 768 y 1440 px. Las 60 comprobaciones no encontraron desbordamientos horizontales ni visores de JSON. Se revisaron login, invitación, recuperación, reset y 2FA en los mismos tamaños. Las capturas y manifiestos están en `artifacts/ui-review` (ignorados por Git). También se probaron menús y tabs de usuarios, confirmación escrita, búsqueda/activación de modelos, descarga, galería→edición, biblioteca→Director, storyboard con reutilización y resultado, cancelación/reanudación y reproductores con medios locales.

La inspección visual e interacciones usaron `apps/web/scripts/qa-api.cjs`, un servidor desechable explícito. El código del producto usa las APIs reales. Estas capturas no prueban ejecución de modelos GPU, entrega SMTP real ni conexión a un proveedor externo real; esos servicios no se invocaron en esta entrega local. Su lógica y errores se cubrieron mediante pruebas con transportes/servicios controlados.

## Ejecución y arte

Consultar `apps/web/README.md` para compilación y vista local de QA. Servir `apps/web/dist` mediante `WEB_ROOT` del runtime bajo su origen HTTPS configurado para utilizar la autenticación real.

El manifiesto de arte con rutas, procedencia y prompts está en [WEB-ART.md](WEB-ART.md).

## Despliegue en Saturno · 1 de octubre de 2026

Publicado en `https://media.example.com`. Release: `20261001-ui-a2057dcc`. Se construyeron imágenes de web/runtime y agente antes de detener los servicios, desde un paquete de 153 archivos sin credenciales, estado ni servidor QA. Se aplicaron 100 archivos nuevos o modificados al checkout canónico. Las imágenes activas siguen usando los tags operativos `0.7.1`; la release conserva tags únicos y los tags de rollback.

El corte exigió colas y agente sin trabajo activo. Se actualizaron únicamente runtime y agente; los dos ComfyUI conservaron sus contenedores y siguen saludables. No se cambiaron dominio, proxy, firewall, modelos ni secretos.

Respaldo privado (permisos 0700/0600): `~/media-lab-data/releases/20261001-ui-a2057dcc/backup`, con código anterior, referencias de imágenes anteriores y snapshot SQLite consistente. Las migraciones son aditivas; no se restauró ni reinicializó el estado. Se verificaron integridad SQLite, identidad/roles/credenciales de las dos cuentas, proveedor activo, migración a conexiones guardadas y conservación de las claves externas. Los 10 registros de medios permanecen idénticos al respaldo.

Verificación de entrega: compilación Linux de ambas imágenes; 10 pruebas web, 93 de runtime (1 omitida) y 4 del agente correctas. HTTPS público y enlaces directos responden 200; APIs privadas siguen devolviendo 401 sin sesión. El PNG del logo, la última chibi y el arte del login servido por HTTPS coinciden con los archivos locales. Se revisó el login público en el navegador, sin errores de consola ni desbordamiento. No se introdujeron contraseñas ni códigos de usuarios reales.

La prueba histórica de continuidad inicialmente encontró dos archivos ausentes de una aceptación anterior; ambos ya estaban ausentes del registro SQLite antes del despliegue. La comprobación posterior exigió conservar todos los medios anteriores y verificó cuatro descargas Range (206), maestros PNG intactos, la ejecución del agente completada sin duplicaciones, configuración del proveedor, modelos y ambos workers. No se ejecutaron nuevas generaciones ni se enviaron correos.

Evidencias locales: `artifacts/deploy/20261001-ui-a2057dcc/result.json`, `deployed-manifest.json`, `continuity-check.log` y `production-login.png`. Los logs de compilación y pruebas también se conservan en el directorio privado de la release en Saturno.


## Proveedores personales por cuenta — 2026-10-01

La pantalla Cuenta → Proveedores IA permite «Añadir proveedor» con nombre y URL de API compatible con OpenAI. Cada cuenta puede registrar hasta 20 endpoints personales; luego guarda su propia clave cifrada, descubre modelos y activa uno explícitamente. Las cuentas sin conexiones guardadas no seleccionan automáticamente el primer proveedor compartido. Las selecciones existentes se conservan.

`POST /v1/account/endpoints` registra el endpoint bajo la cuenta autenticada. El catálogo combina endpoints compartidos habilitados y los personales de esa cuenta. Las APIs de guardar, activar, descubrir, conversar y retirar comprueban su pertenencia. Los endpoints personales no aparecen en Administración y no pueden ser modificados por otras cuentas. Retirar una conexión personal elimina su endpoint; la eliminación de una cuenta también purga sus endpoints.

La migración transaccional conserva IDs, claves, modelos y referencias, añadiendo `owner_id` a `provider_endpoints`: NULL para los compartidos existentes, ID de cuenta para los personales. Sustituye la unicidad global de URL por índices parciales separados para proveedores compartidos y personales por cuenta; verifica todas las claves foráneas. Es idempotente. Se mantiene HTTPS/443, DNS exclusivamente público, TLS verificado, fijación del destino DNS, límites de respuesta y ausencia de redirecciones. Los cambios permanecen bloqueados durante ejecuciones del agente.

Validación: 122 pruebas del runtime aprobadas (una omisión opcional), 13 del renderer web y compilaciones web/escritorio. Doce nuevas pruebas del runtime cubren registro por miembros, aislamiento, DNS/destinos prohibidos, límites, bloqueo del agente, migración y purga. La UI verifica añadir un endpoint, guardar clave, descubrir modelos y activar una selección explícita. Las pruebas no contactan proveedores reales ni generan medios.
