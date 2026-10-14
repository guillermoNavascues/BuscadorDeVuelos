"""Genera supabase/instalar.sql = esquema.sql + lista blanca de aerolíneas.

Uso: python scripts/generar_sql.py
Vuelve a ejecutarlo si cambias worker/buscador/datos/aerolineas.json.
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESQUEMA = RAIZ / "supabase" / "esquema.sql"
AEROLINEAS = RAIZ / "worker" / "buscador" / "datos" / "aerolineas.json"
SALIDA = RAIZ / "supabase" / "instalar.sql"

COLUMNAS = [
    "codigo", "nombre", "permitida", "criterio", "web_oficial", "cabina_max",
    "facturada_nacional_max", "facturada_europa_max", "facturada_largo_max",
    "cobra_por", "bebe_tasa", "notas",
]


def literal(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def main() -> None:
    aerolineas = json.loads(AEROLINEAS.read_text(encoding="utf-8"))
    filas = ",\n".join(
        "  (" + ", ".join(literal(a.get(c)) for c in COLUMNAS) + ")" for a in aerolineas
    )
    # Si la aerolínea ya existe no se pisa nada: tus cambios desde la web se respetan.
    semilla = (
        "\n-- =====================================================================\n"
        "-- Lista blanca inicial de aerolíneas (ver docs/INVESTIGACION.md)\n"
        "-- =====================================================================\n"
        f"insert into public.aerolineas ({', '.join(COLUMNAS)}) values\n{filas}\n"
        "on conflict (codigo) do nothing;\n"
    )
    # Resultado visible al final: si salen 8 tablas y 77 aerolíneas, todo ha ido bien
    comprobacion = (
        "\n-- Comprobación final (debe salir: 8 tablas, 77 aerolíneas, 3 webs, versión 2 = 1, versión 3 = 2, versión 5 = 3, versión 6 = 5, versión 7 = 6, versión 8 = 1, versión 9 = 2, versión 10 = 2;\n"
        "-- accesos registrados por Supabase: más de 0 si has usado la web este mes)\n"
        "select 'Tablas creadas' as comprobacion, count(*) as total from information_schema.tables\n"
        "  where table_schema = 'public' and table_name in\n"
        "  ('perfiles','busquedas','precios','avisos','aerolineas','estado_fuentes','ejecuciones','ajustes')\n"
        "union all select 'Aerolíneas en la lista blanca', count(*) from public.aerolineas\n"
        "union all select 'Webs configuradas', count(*) from public.estado_fuentes\n"
        "union all select 'Versión 2 instalada (tiempo real y Telegram)', count(*) from information_schema.columns\n"
        "  where table_schema = 'public' and table_name = 'perfiles' and column_name = 'telegram_prueba'\n"
        "union all select 'Versión 3 instalada (varios aeropuertos)', count(*) from information_schema.columns\n"
        "  where table_schema = 'public' and table_name = 'busquedas' and column_name in ('origenes_extra', 'destinos_extra')\n"
        "union all select 'Versión 5 instalada (alarma en el móvil)', count(*) from information_schema.columns\n"
        "  where table_schema = 'public' and table_name = 'perfiles'\n"
        "  and column_name in ('ntfy_tema', 'alarma_chollos', 'alarma_prueba')\n"
        "union all select 'Versión 6 instalada (horario solo Telegram)', count(*) from information_schema.columns\n"
        "  where table_schema = 'public' and table_name = 'perfiles'\n"
        "  and column_name in ('ntfy_pausa', 'ntfy_pausa_desde', 'ntfy_pausa_hasta', 'ntfy_pausa_dias', 'zona_horaria')\n"
        "union all select 'Versión 7 instalada (seguridad reforzada)', (select count(*) from pg_constraint where conname in\n"
        "  ('aerolineas_web_https', 'aerolineas_textos_largo', 'busquedas_nombre_largo', 'perfiles_campos_validos',\n"
        "   'estado_fuentes_limites')) + (select count(*) from pg_trigger where tgname = 'proteger_perfil')\n"
        "union all select 'Versión 8 instalada (avisos de acceso)', count(*) from pg_proc\n"
        "  where proname = 'accesos_desde' and pronamespace = 'public'::regnamespace\n"
        "  and not has_function_privilege('anon', oid, 'execute') and not has_function_privilege('authenticated', oid, 'execute')\n"
        "union all select 'Versión 9 instalada (varias fechas y varios destinos)', count(*) from information_schema.columns\n"
        "  where table_schema = 'public' and table_name = 'busquedas' and column_name in ('fechas_extra', 'tramos_viaje')\n"
        "union all select 'Versión 10 instalada (cualquier destino)', count(*) from information_schema.columns\n"
        "  where table_schema = 'public' and table_name = 'busquedas' and column_name in ('cualquier_destino', 'paises_excluidos')\n"
        "union all select 'Accesos registrados por Supabase (últimos 30 días)', count(*) from auth.audit_log_entries\n"
        "  where created_at > now() - interval '30 days';\n"
    )
    SALIDA.write_text(ESQUEMA.read_text(encoding="utf-8") + semilla + comprobacion, encoding="utf-8")
    print(f"{SALIDA} generado con {len(aerolineas)} aerolíneas")


if __name__ == "__main__":
    main()
