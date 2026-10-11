Claude Desktop Session Gateway — Investigación de viabilidad

# Estado de la investigación

**Última revisión:** 11 de octubre de 2026

**Estado:** investigación técnica. No se autoriza implementar el producto.

**Decisión actual:** **NO-GO para reutilizar directamente la credencial extraída de Claude Desktop en una petición independiente a /v1/messages.** La única prueba real terminó en HTTP 403 por autorización OAuth; la causa exacta todavía no está identificada.

## 1. Objetivo de la investigación

Determinar si una aplicación local para macOS podría aprovechar la sesión que mantiene Claude Desktop y ofrecer una pasarela local de inferencia para otros agentes.

La hipótesis tiene tres preguntas principales: si la credencial puede leerse de la caché local; si el servidor acepta esa credencial desde otro proceso; y si sería posible sostener una integración fiable con respuestas normales, streaming, herramientas, límites y ciclo de vida de sesión.

**Resultado principal:** la lectura local se ha demostrado. La petición directa de inferencia no. Una credencial descifrable y cuya fecha local de expiración es futura no es necesariamente una credencial autorizada por el servidor.

## 2. Estado actual por evidencia

### Entorno de referencia aportado por el usuario

- **Claude Desktop:** versión indicada por la aplicación: `Claude 2.31226.1 (857652)`, compilación `2026-10-09T17:56:07.000Z`. El chat nativo respondió `OK` a una prueba manual, por lo que funciona en la comprobación realizada.
- **Claude Code:** versión instalada `2.1.296`, pero no se usa con una cuenta propia de Claude Code; el usuario lo ejecuta a través del gateway local FreeLLMAPI. Por tanto, Claude Code **no debe utilizarse como prueba comparativa de la autorización OAuth de la cuenta de Claude Desktop** ni debe ser un requisito para continuar esta investigación.
- Las siguientes pruebas se centrarán exclusivamente en Claude Desktop y en el comportamiento de su sesión nativa.

### Confirmado localmente

**Archivo local:** en el equipo examinado existe `~/Library/Application Support/Claude/config.json` y el JSON se puede leer.

**Campos OAuth:** se encontraron `oauth:tokenCache` y `oauth:tokenCacheV2`. Ambos valores se descifraron en memoria con el elemento de Llavero observado como `Claude Safe Storage` / `Claude Key`.

**Contenido de las cachés:** `oauth:tokenCacheV2` descifró a un diccionario vacío; `oauth:tokenCache` contenía una entrada.

**Metadatos de la entrada:** incluía el ámbito `user:inference` y los campos `token`, `expiresAt`, `rateLimitTier` y `subscriptionType`. No se encontró un campo `refreshToken` en esa entrada.

**Token candidato:** el campo `token` era una cadena de 108 caracteres con prefijo `sk-ant-oat01-`. El metadato local `expiresAt`, interpretado como timestamp en milisegundos, apuntaba a una fecha futura en el momento del análisis.

**Tratamiento de secretos:** los diagnósticos locales no imprimieron el token, el valor del Llavero ni el JSON descifrado completo.

### Confirmado por una prueba real, con resultado negativo

Se envió una sola petición HTTPS a `POST https://api.anthropic.com/v1/messages`, usando el token extraído en memoria, el modelo `claude-haiku-4-5-20251001`, `max_tokens: 1` y un mensaje mínimo.

**HTTP:** 403.

**Tipo de error:** `permission_error`.

**Mensaje:** `OAuth authentication is currently not allowed for this organization.`

**ID de petición:** `req_011CfvJZmPRtprf2dXoq9ZXB`.

**Reintentos y escrituras:** no hubo reintentos ni escrituras locales durante esa prueba.

La solicitud no generó una respuesta de modelo. Por tanto, no se ha demostrado que la credencial extraída sirva para inferencia desde un proceso independiente.

### Todavía desconocido

**Causa del 403:** no está identificada la causa concreta de la denegación de autorización para esta cuenta/organización.

**Estado de Desktop:** no se ha documentado aquí si Claude Desktop sigue funcionando con normalidad en el mismo momento y contexto.

**Alternativas de integración:** no se ha probado si una vía que no reenvíe directamente la credencial podría satisfacer el objetivo.

**Ciclo de vida:** la estabilidad del formato entre versiones, el comportamiento después de cerrar sesión o cambiar de cuenta y la recuperación tras revocación no se han caracterizado.

**Funciones avanzadas:** streaming, herramientas, conversaciones de varios turnos, cancelación, tratamiento de límites y errores no se han probado.

**Renovación:** no hay base para afirmar que una aplicación independiente pueda renovar esta credencial de forma segura. No debe intentarse renovar basándose en la entrada observada.

## 3. Interpretación del HTTP 403

El error indica que el servidor rechazó la operación por autorización OAuth. No es evidencia de un fallo de descifrado local. Tampoco es, por sí solo, prueba de que el token haya caducado: la fecha local era futura, aunque ese dato no garantiza su aceptación por el servidor.

**Hallazgo externo relevante:** el mismo mensaje exacto aparece en incidencias del propio cliente Claude Code, no solo en intentos de reutilización de tokens. Por ejemplo, #63685, #65714 y #68370 describen el rechazo `OAuth authentication is currently not allowed for this organization`, incluido en algunos reportes de cuentas personales Pro/Max. En al menos un informe se señala que volver a iniciar sesión y generar un setup token tampoco solucionó el bloqueo. Son reportes comunitarios, no un diagnóstico oficial de esta cuenta, pero refuerzan la hipótesis de una denegación de autorización en el servidor y hacen menos probable que el problema sea un error de nuestro descifrado.

**Documentación oficial relacionada:** la documentación de autenticación de Claude Code describe vías admitidas para clientes y scripts, como el inicio de sesión del CLI y `claude setup-token`; esto no demuestra que un token extraído de Claude Desktop sea intercambiable con una credencial del CLI ni que la autorización actual de la cuenta permita las peticiones. La documentación también distingue credenciales de Claude Code de las usadas por Claude Desktop.

**No demostrado:** que sea necesario activar un permiso específico de administrador; que el token esté corrupto o mal extraído; que cambiar el modelo o las cabeceras vaya a resolverlo; o que todos los métodos de integración con Claude Desktop sean inviables. Cualquiera de esas conclusiones excedería la evidencia disponible.

## 4. Evidencia comunitaria que motivó la prueba

El proyecto comunitario CodexBar — incidencia #1894 describe una petición mínima a `/v1/messages` que, en las cuentas y condiciones de ese informe, fue aceptada con un setup token de ámbito `user:inference`. El mismo informe diferencia esos tokens de las credenciales que incluyen `user:profile`, necesarias para consultar el endpoint OAuth de uso.

Esto justificó probar una sola petición con la credencial local, pero no garantizaba que el resultado se reprodujese con la sesión concreta de Claude Desktop de este estudio. La prueba local ha dado 403, por lo que el resultado observado en esta cuenta prevalece sobre la expectativa comunitaria.

**Referencia técnica comunitaria:** ai-usagebar — código que lee credenciales de Desktop. Esta implementación interpreta el campo local `token` como credencial de acceso.

**Referencia oficial contextual (no usada como entorno de prueba):** Autenticación de Claude Code. Describe flujos de Claude Code, pero el usuario no tiene una sesión propia de ese producto. No usar Claude Code como comparación experimental ni asumir que su autenticación explica la de Claude Desktop.

## 5. Registro resumido de experimentos

**Prueba 1 — Inventario local:** se encontró `config.json`; ambos campos OAuth tenían valores Base64.

**Prueba 2 — Análisis estructural:** `oauth:tokenCache` tenía 496 caracteres y descodificaba a 371 bytes; `oauth:tokenCacheV2` tenía 28 caracteres y descodificaba a 19 bytes. Ambos presentaban el prefijo `v10`. Estas longitudes, por sí solas, no identificaban la semántica de cada campo.

**Prueba 3 — Descifrado y análisis JSON:** V2 resultó vacío y V1 contenía una entrada con ámbito `user:inference`. Una ejecución anterior se detuvo porque faltaba la biblioteca Python `cryptography`; esa incidencia quedó resuelta al usar un entorno virtual aislado.

**Prueba 4 — Metadatos de la credencial:** se identificaron el prefijo, la longitud y la fecha local futura descritos arriba, sin imprimir el secreto.

**Prueba 5 — Inferencia independiente:** una petición, sin reintentos ni escrituras locales, terminó con el HTTP 403 descrito en la sección 2.

**Prueba 6 — Exploración estática de registros (11 de octubre):** el análisis de las ventanas recientes de `main.log` y `claude.ai-web.log` no encontró la marca de prueba `DIAG-DESKTOP-20261011-R7K2` ni una ruta explícita `/v1/messages`. `main.log` sí contiene referencias a `api.anthropic.com`, `claude.ai` y `oauth`, pero el resumen no permite ligar esas referencias a la petición de chat probada. Varias “rutas” que salieron de `claude.ai-web.log` parecen ser ubicaciones de archivos JavaScript/stack traces y no endpoints HTTP; no deben tratarse como evidencia de rutas de inferencia. **Conclusión:** la búsqueda estática no es concluyente.

**Prueba 7 — Monitor de registros en tiempo real:** se ejecutó un monitor sobre `main.log` y `claude.ai-web.log`, configurado para mostrar solo rutas normalizadas. El usuario confirmó que envió el mensaje de prueba mientras el monitor estaba activo, pero este no encontró la marca `DIAG-DESKTOP-LIVE-20261011-X9Q4` ni detectó eventos de ruta reconocibles. Esto solo significa que el parser no reconoció URLs en las líneas nuevas; no demuestra que Desktop no realizara peticiones.

**Prueba 8 — Correlación por metadatos (11 de octubre):** `main.log` creció de 3.122.786 a 3.124.185 bytes (1.399 bytes) durante la prueba `DIAG-DESKTOP-SNAPSHOT-20261011-P3M8`. La fecha de modificación cambió de 17:39:08 a 17:40:25. No se leyó el contenido para obtener este resultado. Esto confirma que `main.log` registra alguna actividad durante el intervalo, pero por sí solo no demuestra qué eventos contiene ni asocia los bytes a una petición concreta.

**Prueba 9 — Resumen estructural del fragmento nuevo:** se analizaron los 1.399 bytes desde el desplazamiento inicial informado. El fragmento contenía ocho líneas; no se reconocieron JSON, palabras clave de HTTP, OAuth, token, message, error, response, websocket o stream, ni nombres de campos JSON comunes. La marca de prueba no apareció. **Conclusión:** el fragmento no aporta evidencia útil para identificar el flujo de inferencia. No demuestra ausencia de tráfico y no justifica inspeccionar de forma más intrusiva los protocolos privados. Se cierra la línea de análisis de este fragmento.

**Siguiente paso actualizado:** bajo el supuesto de que el propósito de la investigación está autorizado, resumir los metadatos estructurados de `claude.ai-web.log`, centrando la siguiente prueba en las entradas relacionadas con `a-api.anthropic.com` y mostrando únicamente combinaciones permitidas de método, estado HTTP, código de error y tipo/nombre de evento, sin imprimir líneas originales, valores, parámetros, cuerpos de mensajes, tokens, cookies ni cabeceras. No se repetirá ni sorteará el HTTP 403. Si el registro no ofrece datos útiles, se cerrará esta línea de diagnóstico local.

**Prueba 10 — Análisis agregado de ambos registros:** `main.log` (41.693 líneas) presentó recuentos de términos `api.anthropic.com` (696), `claude.ai` (2.162), `oauth` (1.466), `request` (145) y `error` (341), pero no reconoció `/v1/messages`, GraphQL, WebSocket ni campos JSON permitidos en las 47 líneas parseables. En `claude.ai-web.log` (3.034 líneas), el parser reconoció 1.233 líneas JSON, 44 menciones de `method`, 44 de `statusCode` y 44 de `errorCode`; la ruta normalizada `a-api.anthropic.com/v1/m` apareció 16 veces. Esa ruta puede estar truncada, anonimizada o pertenecer a otro tipo de evento; los recuentos no demuestran que sea un endpoint de inferencia ni que una petición concreta del chat pase por él. No se imprimieron valores de campos, mensajes, credenciales ni cabeceras.

**Conclusión:** el análisis agregado de `main.log` no aporta más evidencia útil; `claude.ai-web.log` contiene metadatos estructurados que podrían describir solicitudes o errores de red, pero aún no se ha identificado con certeza el tipo de evento. Se intentó resumir esos metadatos en las 16 líneas relacionadas con el host, pero ninguna se pudo analizar como JSON y no se reconocieron métodos HTTP, códigos de estado, códigos de error ni nombres/tipos de evento permitidos. **Conclusión de la línea de logs:** no hay evidencia suficiente para identificar el flujo de inferencia. La ruta parcial no debe tratarse como endpoint demostrado. Se cierra el análisis de esos registros.

Este registro reemplaza las antiguas listas de pruebas pendientes que quedaron desactualizadas a medida que se completaron los experimentos. La primera petición real ya se realizó: no queda pendiente ejecutarla; su resultado fue negativo.

## 6. Decisión GO / NO-GO

### Decisión vigente: NO-GO para implementar el método probado

No se debe implementar todavía una pasarela que dependa de extraer esta credencial y reenviarla directamente a `/v1/messages`. El único intento controlado no fue autorizado por el servidor y el motivo no está resuelto.

La investigación general no queda declarada inviable en todos sus enfoques. El bloqueo demostrado corresponde a esta credencial, este contexto y este método de petición en la prueba realizada. No se deben extender las conclusiones más allá de esa evidencia.

### Criterios que aún faltarían para autorizar un prototipo

**Autorización:** aclarar la denegación actual o identificar una vía alternativa verificable.

**Inferencia:** demostrar una petición mínima aceptada desde el proceso que usaría la futura pasarela.

**Ciclo de vida:** explicar la autenticación, incluido cierre de sesión, revocación y recuperación.

**Compatibilidad:** probar por separado streaming y cualquier función de herramientas requerida.

**Seguridad de la pasarela:** definir control de acceso local, redacción de secretos, manejo de errores y dependencias de versión.

Una futura respuesta HTTP 200 sería una condición necesaria para retomar la evaluación de la petición directa, no una aprobación automática de implementación o comercialización.

## 7. Próximas acciones vigentes — enfoque exclusivo en Claude Desktop

**1. Estado nativo:** Claude Desktop respondió `OK` a una prueba manual. No hace falta repetirla salvo que la aplicación empiece a fallar.

**2. Análisis local de logs cerrado:** las búsquedas estáticas, el monitor en tiempo real, la comparación de tamaños y los resúmenes estructurales no identificaron el flujo de inferencia. No ejecutar más parsers sobre esos registros.

**3. Decisión de arquitectura:** la comparación de interfaces de la sección 9 ya está realizada. La reutilización directa de la sesión de Desktop queda en NO-GO provisional; la API oficial es una alternativa de inferencia documentada con autenticación/facturación propia; MCP local sirve para que Claude use herramientas, no para convertir Desktop en motor de inferencia de salida. El permiso para seguir investigando no cambia el HTTP 403 ni confirma que OAuth directo esté admitido.

**4. Evitar intentos a ciegas:** no rotar, renovar ni volver a extraer credenciales para repetir la misma petición; no probar modelos o cabeceras en bucle. Claude Code y su gateway FreeLLMAPI quedan fuera de los experimentos porque no representan una sesión autenticada de Claude Code con la cuenta de Anthropic.

Siguiente paso: fijar si el requisito no negociable es reutilizar la suscripción de Claude Desktop sin autenticación ni facturación de API adicional. Si lo es, el camino queda bloqueado hasta obtener evidencia técnica/documental que explique el 403 y establezca una interfaz aceptada; no tiene sentido implementar la pasarela completa todavía. Si el objetivo puede flexibilizarse, se puede avanzar con una arquitectura de proveedor intercambiable y evaluar la API oficial por separado. Streaming, herramientas y funcionamiento sostenido siguen sin demostrarse para la sesión de Desktop.

## 8. Seguridad y límites del estudio

**Secretos:** no guardar ni incluir tokens, valores del Llavero, cabeceras de autorización o JSON descifrado en Notion.

**Caché:** no intentar renovar credenciales modificando la configuración local.

**Peticiones:** no repetir llamadas para sondear el servidor.

**Compatibilidad:** tratar los formatos internos como detalles no garantizados entre versiones.

**Calidad de evidencia:** mantener separadas las observaciones locales, la evidencia comunitaria y las hipótesis.

**Expiración:** no asumir que una fecha futura local implica validez, autorización o compatibilidad con una API concreta.

## 9. Revisión de interfaces documentadas — 11 de octubre de 2026

Se compara el objetivo exacto del estudio —que una aplicación externa invoque inferencia de Claude reutilizando la sesión de Claude Desktop— con las interfaces descritas en la documentación oficial consultada. La hipótesis de que el estudio puede continuar se entiende como permiso para investigar; **no significa que Anthropic haya confirmado que el uso directo de la sesión sea una vía soportada**, ni modifica el HTTP 403 obtenido.

### A. Extensiones de escritorio y servidores MCP locales

La documentación oficial presenta las Desktop Extensions como servidores MCP locales que Claude Desktop puede utilizar para acceder a herramientas, datos y procesos del equipo. Las extensiones se instalan desde Settings > Extensions, y se pueden crear extensiones propias con MCPB. Estas interfaces permiten que **Claude invoque herramientas externas desde una conversación**; no documentan una API para que un agente externo use Claude Desktop como motor de inferencia.

Fuente oficial: Getting Started with Local MCP Servers on Claude Desktop.

### B. Conectores MCP remotos

Los conectores MCP remotos sirven también para que Claude acceda a herramientas y datos de servicios externos. En este modo, las conexiones al servidor MCP remoto se originan en infraestructura de Anthropic, mientras que los servidores MCP locales configurados para Desktop son un mecanismo diferente. Tampoco representan una API de inferencia de salida para otros agentes.

Fuente oficial: Get started with custom connectors using remote MCP.

### C. API oficial de Claude

La API de Messages es la vía documentada para construir aplicaciones que solicitan inferencia de Claude. La suscripción de chat y Claude Console/API son productos distintos: una suscripción Pro no incluye el uso de API. Las condiciones de planes y créditos cambian; la página de ayuda actual describe créditos de API mensuales para algunos planes Max y Team, sujetos a elegibilidad y a las condiciones aplicables.

Fuentes oficiales:

- Por qué la API se factura por separado de la suscripción de Claude.
- Créditos mensuales de API para planes Max y Team.

### D. Estado de viabilidad para el objetivo original

- **Extraer la credencial local:** demostrado en la instalación examinada.
- **Enviar esa credencial directamente a `/v1/messages`:** rechazado con HTTP 403 y `OAuth authentication is currently not allowed for this organization`.
- **Usar Desktop Extensions/MCP como una API de inferencia para agentes externos:** no es lo que documentan esas interfaces.
- **Invocar inferencia mediante la API oficial:** es un camino documentado, pero utiliza la autenticación y facturación de API; no equivale a reutilizar la sesión de la suscripción de Desktop.
- **Existencia de una interfaz oficial para reutilizar la sesión de Desktop desde otro proceso:** no encontrada en las fuentes consultadas; esto no prueba la inexistencia de una función privada, futura o específica de cuenta, pero tampoco existe evidencia para depender de ella.

### E. Decisión de la siguiente fase

Se cierra la línea de análisis actual de los logs: los análisis estáticos y estructurales no identificaron el flujo de inferencia. No se deben seguir probando combinaciones de cabeceras o rutas para sortear el HTTP 403. El trabajo útil restante es evaluar si el producto acepta una de estas decisiones de arquitectura: (1) utilizar una interfaz de inferencia documentada con credenciales/costes propios; (2) cambiar el objetivo para que Claude Desktop llame a herramientas MCP locales; o (3) mantener la idea de reutilización de sesión como hipótesis bloqueada que requiere una explicación verificable de Anthropic antes de escribir una implementación funcional.

## 10. Investigación adicional del HTTP 403 — contexto de autorización OAuth

Se buscaron informes públicos del mensaje exacto `OAuth authentication is currently not allowed for this organization`.

### Hallazgo comunitario relevante

En la incidencia anthropics/claude-code #63685, un colaborador de Anthropic explicó que ese mensaje en Claude Code indica que el acceso mediante inicio de sesión de suscripción está desactivado en la organización del lado del servidor y que los ajustes locales no pueden anularlo. Otras incidencias, como #65714 y #68370, documentan el mismo texto en cuentas personales cuyo chat de Claude seguía funcionando.

**Límite de aplicabilidad:** esas incidencias se refieren a autenticación de Claude Code, mientras que nuestro experimento envió una petición directa a Messages con la credencial observada en Claude Desktop. El mensaje idéntico es una pista significativa de una denegación de autorización del lado del servidor, pero **no demuestra que la causa interna sea exactamente la misma** para la sesión Desktop ni identifica la política concreta aplicada a esta cuenta.

La incidencia #68370 incluye una teoría del propio usuario sobre una suscripción de facturación duplicada; no se presentó como diagnóstico confirmado de Anthropic y no debe asumirse que ese sea nuestro caso.

### Interpretación y efecto en el plan

- El rechazo no parece resoluble mediante otra lectura o descifrado local del mismo token.
- No hay evidencia de que cambiar cabeceras, modelos o rutas lo solucione; no se deben probar combinaciones a ciegas.
- No existe un resultado de logs que identifique el endpoint interno de inferencia de Desktop.
- El siguiente dato decisivo sería una aclaración de Anthropic sobre si la autorización OAuth de esa sesión de Desktop permite uso de inferencia desde un proceso independiente y, si no, qué interfaz admitida corresponde al objetivo.
- El supuesto de que podemos seguir investigando permite continuar el estudio, pero no convierte en autorizada o funcional una petición que el servidor rechazó.

**Estado:** reutilización directa de la sesión Desktop → **NO-GO provisional, bloqueada por el 403 del servidor**. Integración mediante API oficial con credenciales/facturación propias → vía documentada, pero no equivalente al objetivo original. MCP local → alternativa para que Claude utilice herramientas, no una pasarela de inferencia para otros agentes.
