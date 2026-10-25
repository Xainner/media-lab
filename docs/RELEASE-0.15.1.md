# 0.15.1 · Origen con IP para instancias solo de LAN

Imágenes `media-lab-web` y `media-lab-agent` 0.15.1. El runtime y ComfyUI no cambian.

## Instalador

- `--origin` acepta una IPv4 además de un nombre, por ejemplo `https://192.168.1.20:8390`, junto
  con `--listen 0.0.0.0`. Es para instancias que solo se usan dentro de la LAN.
- **Certificado:** con una IP, el certificado de origen la lleva como `IP:` en el SAN; con un nombre
  sigue siendo `DNS:`. Si cambia el origen, el instalador vuelve a emitir el certificado.
- **IP inválida:** se rechaza con un mensaje claro, por ejemplo octetos mayores de 255 o con ceros
  a la izquierda.
- **Healthcheck:** usa `curl --connect-to`, que funciona igual con nombres y con IPs. Antes usaba
  `--resolve`, que curl no aplica a una IP literal.

## Agente

- Con un origen IP, el agente ya no manda la IP como SNI, porque RFC 6066 no lo permite y Node lo
  va a ignorar.
- El certificado del runtime se sigue verificando contra la IP del origen.
- Con un nombre no cambia nada.

## Notas

- La IP debe ser fija (reserva DHCP). Si cambia, vuelve a ejecutar el instalador con la nueva.
- Los navegadores y los clientes MCP deben confiar en `origin-ca.crt`, igual que con un nombre
  en la LAN.
