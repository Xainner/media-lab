"""Media Lab email identity: inline CSS, presentation tables and plain-text fallback."""
from html import escape
import re


COPY = {
    'invite': {
        'subject': 'Tu invitación al estudio · Media Lab',
        'eyebrow': 'TU PRÓXIMA HISTORIA EMPIEZA AQUÍ',
        'title': 'Un mundo por imaginar.',
        'intro': 'Tienes una invitación para entrar a Media Lab: tu estudio privado para crear imágenes, vídeos y música con IA.',
        'action': 'Aceptar mi invitación',
        'note': 'Esta invitación es personal, se usa una sola vez y caduca en 72 horas. Crea tu cuenta con el correo que recibió este mensaje.',
        'preheader': 'Tu estudio en Media Lab te espera. Acepta tu invitación en las próximas 72 horas.',
    },
    'reset': {
        'subject': 'Recupera el acceso a tu estudio · Media Lab',
        'eyebrow': 'VOLVAMOS A CREAR',
        'title': 'Tu estudio te espera.',
        'intro': 'Recibimos una solicitud para restablecer tu contraseña. Usa el siguiente botón para elegir una nueva y volver a tu espacio creativo.',
        'action': 'Restablecer mi contraseña',
        'note': 'El enlace se usa una sola vez y caduca en 30 minutos. Tu verificación en dos pasos seguirá activa. Si no solicitaste este cambio, puedes ignorar este mensaje.',
        'preheader': 'Restablece tu contraseña de Media Lab. El enlace caduca en 30 minutos.',
    },
    'test': {
        'subject': 'La conexión de correo está lista · Media Lab',
        'eyebrow': 'CONECTADOS PARA CREAR',
        'title': 'Todo listo para conectar.',
        'intro': 'Este es un mensaje de prueba de Media Lab. Si puedes leerlo, la configuración de correo está entregando mensajes a esta dirección.',
        'action': 'Abrir mi estudio',
        'note': 'Puedes volver a la pantalla de Correo y entregas para comprobar el estado de la prueba. Las invitaciones y los mensajes de recuperación compartirán este estilo.',
        'preheader': 'Una prueba de conexión con la nueva identidad de Media Lab.',
    },
}


def render_email(kind: str, content: str, origin: str) -> tuple[str, str, str]:
    """Render at delivery so already queued messages adopt the new style too.

    Invitation/reset links are extracted verbatim from the encrypted legacy payload.
    Only the expected link for this message and this site's origin becomes a CTA.
    """
    copy = COPY.get(kind)
    if copy is None:
        copy = {'subject': 'Un mensaje de tu estudio · Media Lab', 'eyebrow': 'TU ESPACIO CREATIVO',
                'title': 'Hola desde Media Lab.', 'intro': content, 'note': '',
                'action': '', 'preheader': 'Un mensaje de Media Lab.'}
    action_url = origin + '/' if kind == 'test' else ''
    if kind in {'invite', 'reset'}:
        match = re.search(r'(?<!\S)' + re.escape(origin) + r'/#' + kind + r'=([A-Za-z0-9_-]{32,128})(?=\s|$)', content)
        if match:
            action_url = match.group(0)
        else:
            # Invalid legacy data cannot introduce an arbitrary HTML link or action.
            copy = {**copy, 'intro': content, 'action': ''}
    text = '\n\n'.join(part for part in [
        'MEDIA LAB', copy['title'], copy['intro'],
        (copy['action'] + '\n' + action_url) if action_url else '', copy['note'],
        'Tu estudio privado para imaginar y crear.\nUso personal · solo por invitación.',
    ] if part) + '\n'
    url, home = escape(action_url, quote=True), escape(origin + '/', quote=True)
    logo = escape(origin + '/brand/mail-logo.png', quote=True)
    action = ''
    if action_url:
        action = f'''<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:28px 0 24px;"><tr><td bgcolor="#ff5a1f" style="background-color:#ff5a1f;border:1px solid #ff8a3d;border-radius:12px;padding:16px 24px;text-align:center;">
<a href="{url}" style="display:inline-block;font-family:Arial,sans-serif;font-size:15px;font-weight:700;line-height:22px;color:#160701;text-decoration:none;">{escape(copy['action'])} &rarr;</a></td></tr></table>'''
    fallback = ''
    if action_url and kind != 'test':
        fallback = f'''<p style="margin:24px 0 8px;font-size:12px;line-height:20px;color:#8f8a83;">Si el botón no se abre, copia este enlace en tu navegador:</p>
<p style="margin:0;font-size:12px;line-height:20px;word-break:break-all;overflow-wrap:anywhere;"><a href="{url}" style="color:#ff8a3d;text-decoration:underline;word-break:break-all;">{escape(action_url)}</a></p>'''
    html = f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark"><title>{escape(copy['subject'])}</title></head>
<body style="margin:0;padding:0;width:100%;background-color:#0b0b0d;color:#f4f1ec;font-family:Arial,sans-serif;-webkit-text-size-adjust:100%;">
<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{escape(copy['preheader'])}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#0b0b0d" style="width:100%;background-color:#0b0b0d;"><tr><td align="center" style="padding:32px 16px;">
<!--[if mso]><table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;">
<tr><td style="padding:0 8px 24px;"><table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr><td width="60" valign="middle"><a href="{home}" style="text-decoration:none;"><img src="{logo}" alt="Media Lab" width="48" height="48" style="display:block;width:48px;height:48px;border:0;"></a></td><td valign="middle"><a href="{home}" style="font-family:'Arial Narrow',Arial,sans-serif;font-size:26px;font-weight:800;line-height:30px;letter-spacing:1px;color:#f4f1ec;text-decoration:none;">MEDIA <span style="color:#ff5a1f;">LAB</span></a></td></tr></table></td></tr>
<tr><td bgcolor="#141417" style="background-color:#141417;border:1px solid #26262c;border-top:3px solid #ff5a1f;border-radius:20px;padding:32px 24px;">
<p style="margin:0 0 18px;font-size:10px;font-weight:700;line-height:18px;letter-spacing:2px;color:#ff8a3d;">&#10022; {escape(copy['eyebrow'])}</p>
<h1 style="margin:0 0 20px;font-family:'Arial Narrow',Arial,sans-serif;font-size:34px;font-weight:800;line-height:38px;letter-spacing:0;text-transform:uppercase;color:#f7f4ef;">{escape(copy['title'])}</h1>
<p style="margin:0;font-size:15px;line-height:26px;color:#c9c4bc;white-space:pre-line;">{escape(copy['intro'])}</p>
{action}
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td bgcolor="#1c1c21" style="background-color:#1c1c21;border:1px solid #2c2c33;border-radius:12px;padding:16px;"><p style="margin:0;font-size:13px;line-height:22px;color:#b8b2aa;">{escape(copy['note'])}</p></td></tr></table>
{fallback}
</td></tr>
<tr><td align="center" style="padding:24px 12px 0;"><p style="margin:0 0 8px;font-size:12px;line-height:20px;color:#ff8a3d;">Tu estudio privado para imaginar y crear.</p><p style="margin:0;font-size:10px;line-height:18px;color:#77726b;">Media Lab &middot; Uso personal &middot; Solo por invitación.</p></td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr></table></body></html>'''
    return copy['subject'], text, html
