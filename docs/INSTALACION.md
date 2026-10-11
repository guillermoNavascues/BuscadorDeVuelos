# Instalación paso a paso

Todo es gratis. Tardarás unos 30 minutos. Necesitas:

- **GitHub** (ya lo tienes): guarda el código y ejecuta el robot sin parar (sesiones de casi 6 horas que se encadenan solas).
- **Supabase**: la base de datos con tu cuenta, tus búsquedas y el historial de precios.
- **Cloudflare Pages**: aloja la web para que la abras desde el móvil o el PC.
- **Telegram**: te llegan los avisos.

> 🔐 **Regla de oro:** hay dos claves de Supabase. La **publishable** (`sb_publishable_...`) es pública y va en la web.
> La **secret** (`sb_secret_...`) es secreta: solo se pega en los *secretos* de GitHub, nunca en el código ni en un chat.
> (Las antiguas *anon* y *service_role* también funcionan, pero Supabase las retira a finales de 2026.)

---

## 1. Base de datos (Supabase)

1. Entra en <https://supabase.com> → **Start your project** → regístrate con tu cuenta de GitHub.
2. **New project**:
   - Name: `buscador-vuelos`
   - Database password: genera una y guárdala (no la necesitarás a diario).
   - Region: **West EU (Paris)** o **Central EU (Frankfurt)**.
3. Cuando termine de crearse, ve a **SQL Editor** → **New query**.
4. Abre el archivo [`supabase/instalar.sql`](../supabase/instalar.sql) de este repositorio. Copia **todo** su contenido, pégalo y pulsa **Run**.
   Debe terminar con *Success*. Se puede volver a ejecutar sin problema; **hazlo tras cada actualización**
   (la versión 2 añade el tiempo real de la web, la señal de vida del robot y el mensaje de prueba de Telegram;
   la versión 3, varios aeropuertos de salida y de llegada por búsqueda; la versión 5, la alarma en el móvil;
   la versión 6, el horario «solo Telegram» de la alarma; la versión 7, seguridad reforzada; la versión 8, un aviso
   por Telegram cada vez que alguien entra en tu cuenta; la versión 9, varias fechas en una búsqueda y viajes con
   varios destinos).
   La tabla final debe decir "Versión 2 instalada" = 1, "Versión 3 instalada" = 2, "Versión 5 instalada" = 3,
   "Versión 6 instalada" = 5, "Versión 7 instalada" = 6, "Versión 8 instalada" = 1 y "Versión 9 instalada" = 2.
   "Accesos registrados por Supabase" debe ser más de 0 si has usado la web este mes; si sale 0, revisa en
   **Authentication → Audit Logs** que esté activado **Write audit logs to the database** (sin eso no hay avisos de acceso).
5. Apunta estos tres datos:
   - **Project URL** (en **Project Settings → Data API**): algo como `https://abcdxyz.supabase.co`.
   - **Publishable key** (en **Project Settings → API Keys**): empieza por `sb_publishable_`. Es pública y va en la web.
   - **Secret key** (misma pantalla, pulsa el ojo para verla): empieza por `sb_secret_`. Es **secreta** y solo va en GitHub.

## 2. Conectar la web con tu base de datos

Edita [`web/js/config.js`](../web/js/config.js) y pon tu *Project URL* y tu clave **publishable**:

```js
export const SUPABASE_URL = "https://abcdxyz.supabase.co";
export const SUPABASE_ANON_KEY = "sb_publishable_...";
```

Desde GitHub: abre el archivo → icono del lápiz → cambia las dos líneas → **Commit changes**.
Si lo prefieres, pásame la URL y la clave **publishable** (la pública, nunca la secret) y lo hago yo.

## 3. Publicar la web (Cloudflare Pages)

1. Entra en <https://dash.cloudflare.com> y crea una cuenta gratuita.
2. **Workers y Pages** → **Crear** → pestaña **Pages** → **Conectar a Git**.
3. Autoriza GitHub. Puedes dar acceso **solo** al repositorio `BuscadorDeVuelos`.
4. Configuración de compilación:
   - Framework preset: **None**
   - Build command: *(vacío)*
   - Build output directory: **`web`**
5. **Guardar e implementar**. Te dará una dirección del tipo `https://buscadordevuelos.pages.dev`.
   Cada vez que cambie algo en GitHub, la web se actualiza sola.
6. Vuelve a Supabase → **Authentication → URL Configuration**:
   - **Site URL**: tu dirección de Cloudflare, p. ej. `https://buscadordevuelos.pages.dev`.
   - **Redirect URLs**: añade la misma dirección.

## 4. Crear tu cuenta

Abre tu web → **Crear cuenta** → confirma el correo que te llega → rellena el perfil (familia numerosa, residente).
Solo se puede crear **una** cuenta: después el registro se cierra solo.

## 5. Bot de Telegram

1. En Telegram, abre **@BotFather** (tiene el check azul) y envíale `/newbot`.
2. Elige un nombre (p. ej. *Mis Vuelos*) y un usuario que acabe en `bot` (p. ej. `mis_vuelos_2026_bot`).
3. BotFather te da un **token** (`123456789:AA...`). Es secreto: guárdalo en GitHub (paso 6), no lo compartas.
4. Pon el usuario de tu bot en [`web/js/config.js`](../web/js/config.js) (`BOT_TELEGRAM`, sin la @).
5. Cuando el robot esté en marcha (paso 6), ve en tu web a **Perfil** y pulsa **Abrir Telegram y vincular**:
   se abre el chat con tu bot con el código ya puesto; pulsa **Iniciar**. En menos de un minuto te contestará
   "✅ ¡Listo!" y la tarjeta de la web se pondrá en verde sola.
   - Si ya habías hablado con el bot, envíale `/start CÓDIGO` (el código que sale en la web).
   - **Enviar mensaje de prueba** comprueba que los avisos te llegan.
   - **Volver a vincular** genera un código nuevo (por ejemplo, si cambias de móvil o algo falla).
   - En el chat puedes escribir `/estado` (resumen de tus búsquedas) o `/ayuda`.
6. (Opcional) **Alarma en el móvil para los chollazos**: instala la app gratuita **ntfy** (Android o iPhone) y sigue los
   pasos de **Perfil → Alarma en el móvil**: suscribirte a tu canal secreto, activar el interruptor y **Probar alarma**.
   Solo suena en bajadas fuertes, chollos y precios dentro de tu objetivo. En Android puedes darle sonido de alarma y que
   ignore "No molestar" (ajustes de notificaciones de ntfy → canal de prioridad máxima); en iPhone llega como notificación normal.
   Con **Horario solo Telegram** eliges horas y días en los que el móvil no suena: en ese horario los avisos llegan solo por Telegram.

## 6. Secretos del robot (GitHub)

En tu repositorio de GitHub ve a **Settings → Secrets and variables → Actions**.

En la pestaña **Secrets**, pulsa **New repository secret** tres veces:

| Nombre | Valor |
|---|---|
| `SUPABASE_URL` | La *Project URL* de Supabase |
| `SUPABASE_SERVICE_KEY` | La **Secret key** (`sb_secret_...`) |
| `TELEGRAM_BOT_TOKEN` | El token de BotFather |

En la pestaña **Variables**, pulsa **New repository variable**:

| Nombre | Valor |
|---|---|
| `URL_WEB` | La dirección de tu web, p. ej. `https://buscadordevuelos.pages.dev` |

> Esta variable es el **interruptor** del robot: mientras no exista, el robot no se ejecuta
> (así no gasta minutos ni te llegan correos de error antes de terminar la instalación).

Arrancar el robot:

1. Ve a **Actions**. Si te lo pide, pulsa **I understand… enable them**.
2. Elige **Robot de vuelos** → **Run workflow**.
3. La casilla **"Forzar: revisar ya todas las búsquedas"** ya viene marcada: pulsa el botón verde **Run workflow**.

A partir de ahí funciona **sin parar**: cada minuto mira Telegram y revisa las búsquedas a las que les toca
(cada búsqueda, cada 20 min).
Cada sesión dura casi 6 horas y, al terminar, lanza la siguiente. Además, cada 2 horas GitHub comprueba que haya
una en marcha y, si la cadena se hubiera cortado, la vuelve a arrancar.

## 7. Comprobar que todo va bien

- En tu web, el indicador de la barra lateral dice **Robot en directo** y la pantalla **Robot** muestra su actividad.
- En Telegram te ha llegado "✅ ¡Listo!" y, si lo pediste, el mensaje de prueba.
- Con la versión 8 instalada, en el primer minuto del robot te llega "🔐 Avisos de acceso activados".
- Crea una búsqueda: en uno o dos minutos verás el primer precio. Ábrela con **En directo**: la gráfica, las
  estadísticas y la lista de cambios de precio se actualizan solas en cuanto el robot encuentra un precio distinto.

---

## Mantenimiento

- **Minutos de GitHub**: el repositorio es **público**, así que no hay límite de minutos y el robot puede ir sin parar.
  ⚠️ Si algún día lo pones **privado**, el modo continuo gastaría los 2.000 minutos gratis del mes en día y medio:
  en `.github/workflows/robot.yml` quita `--continuo 345` (quedará una ronda suelta cada 2 horas).
  En un repositorio público, GitHub desactiva las ejecuciones programadas tras 60 días sin cambios: el robot sube él solo
  un cambio vacío cuando hace falta para evitarlo.
- **Uso razonable de GitHub**: GitHub Actions está pensado para automatizar proyectos, no como servidor 24/7. Un robot
  ligero como este (unas pocas peticiones cada pocos minutos) no suele dar problemas, pero GitHub podría limitarlo.
  Si pasara, la alternativa es la misma configuración con una ronda cada 2 horas (ver el punto anterior).
- **Si el robot se para** (la web dice *Robot en pausa* durante más de una hora): GitHub → **Actions** →
  **Robot de vuelos** → **Run workflow**. Si una sesión falla, el registro de esa ejecución dice por qué.
- **Supabase en pausa**: el plan gratuito pausa los proyectos sin actividad durante 7 días. El robot la usa cada minuto,
  así que no debería pasar; si pasara, entra en supabase.com y pulsa **Restore**.
- **Si Google Flights deja de funcionar** (búsquedas con "no se han encontrado vuelos" y, en el registro de la ronda,
  `Google no devolvió vuelos` o `error 13`): Google ha vuelto a cambiar su sistema. La librería `flights` (fli) suele
  corregirlo en su GitHub antes de publicar versión; en `worker/requirements.txt` cambia el commit fijado por el más
  reciente de <https://github.com/punitarani/fli/commits/main>. Desde agosto de 2026 cada día del calendario de precios
  cuesta una página de Google, por eso el modo chollo mira 8 fechas por ronda y las va rotando.
- **Avisos de acceso**: cada vez que alguien entra en tu cuenta de la web (o pide recuperar la contraseña, la cambia…)
  te llega un Telegram con la hora, la IP y si la IP es nueva (no estaba entre tus últimos 20 inicios de sesión; con
  datos móviles la IP cambia a menudo, así que «nueva» no siempre es un intruso). Si no has sido tú:
  **Perfil → Cambiar contraseña**, que cierra todas las demás sesiones. Supabase solo apunta los accesos que salen
  bien (no las contraseñas equivocadas). Como mucho llegan 6 mensajes por hora; si hay muchos seguidos, van juntos.
  El registro público de GitHub solo muestra cuántos avisos se enviaron, nunca las IPs.
- **Aerolíneas**: revisa y ajusta los precios de maletas en la pantalla **Aerolíneas** si al comprar ves que son otros.
- **Skyscanner**: está desactivada porque bloquea a los robots. Puedes activarla en **Robot** para reintentar; si bloquea,
  el robot la deja descansar sola.

## Probar el robot en tu PC (opcional)

```bash
python -m venv .venv
.venv\Scripts\pip install -r worker/requirements.txt
cd worker
..\.venv\Scripts\python -m buscador.cli SVQ ORY --ida 2026-11-15 --vuelta 2026-11-19 --adultos 2 --facturada 1
```

No necesita base de datos: imprime las mejores opciones, la decisión y cómo sería el mensaje de Telegram.
Ejecuta `python -m buscador.cli --help` para ver todas las opciones (chollo, franjas horarias, presupuesto, familia numerosa…).
