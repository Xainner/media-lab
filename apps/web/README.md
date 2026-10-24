# Media Lab · Web

Estudio multimedia con rutas propias, identidad Rinari y componentes de Animate UI. Las vistas de creación están en `src/studio`; el shell, la autenticación y el tema en `src`.

El acceso para agentes externos se habilita en **Cuenta → Conexiones MCP**. Cada token tiene permisos, caducidad y revocación independientes; consulta [la guía MCP](../../docs/MCP.md) para conectar clientes y usar las herramientas.

Desde la raíz del repositorio:

```powershell
npm --prefix apps/web ci
npm --prefix apps/web run build
npm --prefix apps/web test
```

La compilación se guarda en `apps/web/dist`. El runtime la sirve mediante `WEB_ROOT` bajo su origen HTTPS configurado. Para un backend real, conservar el mismo origen de UI y API: la autenticación verifica Host, Origin, CSRF y cookies Secure.

Para revisar únicamente la interfaz con datos desechables, abrir dos terminales:

```powershell
node apps/web/scripts/qa-api.cjs
```

```powershell
$env:RVL_API_URL='http://127.0.0.1:5375'
npm --prefix apps/web run dev
```

La vista se abre en `http://127.0.0.1:5374`. El servidor de prueba acepta una identidad de muestra y una contraseña ficticia, sin enviar correo ni ejecutar modelos. `qa-factor` muestra el segundo factor de prueba, con código ficticio `123456`. Estos datos no forman parte de la compilación ni de los servicios reales.

Las demostraciones de audio/vídeo esperan `artifacts/ui-review/sample-song.wav` y `sample-video.mp4`; son archivos locales de QA, no recursos publicados del producto.

Ver [implementación y validación](../../docs/WEB-REDESIGN.md) y [arte y prompts](../../docs/WEB-ART.md). Las licencias de componentes y fuentes se conservan en `public/licenses`.
