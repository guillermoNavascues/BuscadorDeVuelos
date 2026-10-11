# ✈️ Buscador de Vuelos

Vigila precios de vuelos por ti y te avisa por **Telegram** cuando es buen momento para comprar.
Tú compras en la web oficial de la aerolínea.

- **Aeropuertos exactos, uno o varios**: Orly, no "París"; y si te vale salir de Sevilla o de Jerez, añades los dos
  (la web te sugiere los cercanos) y el robot busca desde todos a la vez.
- **Horarios**: franjas de salida y de llegada para la ida y para la vuelta.
- **Pasajeros**: hasta 9 (adultos, niños y bebés), con el **precio total** de todos, maletas incluidas.
- **Descuentos**: familia numerosa y residente, aplicados automáticamente en vuelos nacionales.
- **Dos modos de búsqueda**: **fechas concretas** o **chollo** (cualquier fecha de un periodo).
- **Dos modos de precio**: **presupuesto máximo** o **lo más barato posible** (decide un algoritmo basado en la
  [investigación](docs/INVESTIGACION.md)).
- **Seguridad**: solo aerolíneas seguras (lista blanca estricta, editable) y solo enlaces a webs oficiales.
- **Privacidad**: cada búsqueda en una sesión privada nueva, sin cookies.
- **Avisos de acceso**: un Telegram cada vez que alguien entra en tu cuenta de la web (hora, IP y si la IP es nueva).
- **En directo**: el robot busca sin parar y la web muestra al momento cada revisión (suba, baje o siga igual), con
  gráfica tipo bolsa, estadísticas y comparación con tu objetivo.
- **Comprar ya**: un botón (y un enlace en Telegram) que abre Google Flights con esos vuelos exactos ya elegidos.

## Cómo funciona

```
 Tú ──► Web (Cloudflare Pages) ◄─tiempo real─► Base de datos (Supabase) ◄── Robot (GitHub Actions, sin parar)
                                                                     │
                                       Google Flights · Ryanair ◄────┤
                                                                     └──► Avisos por Telegram
```

1. En la web creas una búsqueda: aeropuertos, fechas, horarios, pasajeros, maletas y presupuesto.
2. El robot funciona sin parar en GitHub Actions (sesiones de casi 6 horas que se encadenan solas). Cada búsqueda
   se revisa cada 20 min, y cada web consultada tiene su propio ritmo (si una bloquea al robot, te avisa por Telegram).
3. El robot hace lo siguiente:
   - Descarta lo que no cumple tus filtros.
   - Calcula el total real: billetes + maletas − descuentos.
   - Guarda el historial (la web lo muestra al instante) y decide si avisar.
4. Te llega un Telegram con el vuelo, el desglose del precio y el enlace a la web oficial para comprar:
   al llegar a tu presupuesto, al tocar el mínimo en el mejor momento, en un chollo o si baja todavía más.

## Estructura

| Carpeta | Contenido |
|---|---|
| `web/` | La web (HTML + JavaScript, sin compilación). Funciona en el móvil. `?demo` muestra datos de ejemplo. |
| `worker/buscador/` | El robot en Python: fuentes (Google Flights, Ryanair, Skyscanner), filtros, precios, decisión y avisos. |
| `worker/tests/` | Pruebas automáticas, que se ejecutan antes de cada ronda. |
| `supabase/` | `instalar.sql`: tablas, seguridad y lista blanca de aerolíneas. |
| `.github/workflows/robot.yml` | Ejecuta el robot sin parar (y lo rearranca cada 2 horas si la cadena se corta). |
| `scripts/` | Generan los datos de aeropuertos y el SQL de instalación. |
| `docs/` | [Instalación paso a paso](docs/INSTALACION.md) e [investigación](docs/INVESTIGACION.md). |

## Puesta en marcha

Sigue **[docs/INSTALACION.md](docs/INSTALACION.md)** (unos 30 minutos, todo gratis).

## Probar en local

```bash
python -m venv .venv
.venv\Scripts\pip install -r worker/requirements.txt
cd worker
..\.venv\Scripts\python -m pytest -q tests
..\.venv\Scripts\python -m buscador.cli SVQ ORY --ida 2026-11-15 --vuelta 2026-11-19 --adultos 2 --facturada 1
```

La web en modo demo (sin base de datos): `python -m http.server 8765 --directory web` y abre <http://localhost:8765/?demo>.
