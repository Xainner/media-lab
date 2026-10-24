# Correos de Media Lab

Las invitaciones, la recuperación de contraseña y la prueba SMTP comparten la identidad de la web: logo de Rinari, fondo ciruela, acentos violeta, tarjeta y botón de acción. El remitente muestra «Media Lab» y los asuntos están en español.

`services/runtime/src/media_lab/mail_templates.py` construye las plantillas. `Mailbox.deliver_one` envía `multipart/alternative` con versiones UTF-8 de texto y HTML. El HTML usa tablas de presentación, CSS en línea, ancho adaptable y una estructura de 600 px para Outlook. No depende de fuentes externas ni de JavaScript. El logo usa el recurso público `/logo-rinari.png`; el nombre de la aplicación sigue legible cuando el cliente bloquea imágenes externas.

El formato se aplica al entregar: los mensajes pendientes conservan su contenido cifrado y reciben la nueva plantilla. Los enlaces de invitación y recuperación se extraen de ese contenido, sin generar otro token ni cambiar su caducidad. Solo un enlace del origen configurado y del tipo esperado puede convertirse en botón. Las invitaciones mantienen las 72 horas, y la recuperación los 30 minutos y el aviso de que 2FA sigue activo.

La configuración SMTP, TLS, verificación, cola cifrada, reintentos y Message-ID estable conservan su funcionamiento. Los mensajes ya entregados no se pueden reformatear.

## Validación

- 110 pruebas del runtime aprobadas; una omitida por el decodificador opcional.
- Ocho pruebas de las plantillas: enlaces anteriores, escape de HTML, enlaces inesperados, MIME UTF-8, remitente, SMTP con STARTTLS/SSL, verificación y aceptación real de una invitación generada.
- El SMTP se captura en memoria: estas pruebas no envían correos a destinatarios reales.
- Las vistas de ejemplo están en `artifacts/mail-preview` y usan tokens ficticios, sin credenciales. Son archivos HTML, texto y EML.
- La revisión en navegador comprueba la estructura adaptable. La apariencia final puede variar entre clientes; no se ha accedido a buzones de Gmail u Outlook para validarla.
