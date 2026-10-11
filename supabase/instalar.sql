-- =====================================================================
-- Buscador de Vuelos · esquema de base de datos (Supabase / PostgreSQL)
-- No ejecutes este archivo directamente: ejecuta supabase/instalar.sql,
-- que incluye este esquema más la lista blanca de aerolíneas.
-- Se puede ejecutar varias veces sin romper nada.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Perfil del usuario (se crea solo al registrarse)
-- ---------------------------------------------------------------------
create table if not exists public.perfiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nombre text,
  familia_numerosa text not null default 'ninguna'
    check (familia_numerosa in ('ninguna', 'general', 'especial')),
  residente text not null default 'ninguno'
    check (residente in ('ninguno', 'canarias', 'baleares', 'melilla')),
  telegram_chat_id text,
  telegram_codigo text,
  telegram_prueba boolean not null default false,
  -- Alarma en el móvil (app ntfy) en los chollazos: canal secreto, interruptor y prueba
  ntfy_tema text,
  alarma_chollos boolean not null default false,
  alarma_prueba boolean not null default false,
  -- Horario «solo Telegram»: en esas horas (de su zona horaria) la alarma del móvil no suena
  ntfy_pausa boolean not null default false,
  ntfy_pausa_desde time not null default '09:00',
  ntfy_pausa_hasta time not null default '14:00',
  ntfy_pausa_dias smallint[] not null default '{1,2,3,4,5,6,7}',
  zona_horaria text not null default 'Europe/Madrid',
  perfil_completado boolean not null default false,
  creado timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Búsquedas que vigila el robot
-- ---------------------------------------------------------------------
create table if not exists public.busquedas (
  id uuid primary key default gen_random_uuid(),
  usuario uuid not null default auth.uid() references auth.users(id) on delete cascade,
  nombre text not null,
  modo text not null check (modo in ('fechas', 'chollo')),
  ida_vuelta boolean not null default true,
  origen text not null check (origen ~ '^[A-Z]{3}$'),
  destino text not null check (destino ~ '^[A-Z]{3}$'),
  -- Aeropuertos alternativos (p. ej. salir de Sevilla o de Jerez): vale cualquiera de ellos
  origenes_extra text[] not null default '{}',
  destinos_extra text[] not null default '{}',
  -- modo "fechas": fechas concretas (con margen opcional de ± días)
  fecha_ida date,
  fecha_vuelta date,
  flex_dias int not null default 0 check (flex_dias between 0 and 3),
  -- modo "chollo": cualquier fecha dentro de un rango
  chollo_desde date,
  chollo_hasta date,
  noches_min int check (noches_min between 1 and 60),
  noches_max int check (noches_max between 1 and 60),
  -- franjas horarias en horas (0-24), hora local de cada aeropuerto
  ida_salida_min int not null default 0 check (ida_salida_min between 0 and 24),
  ida_salida_max int not null default 24 check (ida_salida_max between 0 and 24),
  ida_llegada_min int not null default 0 check (ida_llegada_min between 0 and 24),
  ida_llegada_max int not null default 24 check (ida_llegada_max between 0 and 24),
  vuelta_salida_min int not null default 0 check (vuelta_salida_min between 0 and 24),
  vuelta_salida_max int not null default 24 check (vuelta_salida_max between 0 and 24),
  vuelta_llegada_min int not null default 0 check (vuelta_llegada_min between 0 and 24),
  vuelta_llegada_max int not null default 24 check (vuelta_llegada_max between 0 and 24),
  -- pasajeros y equipaje
  adultos int not null default 1 check (adultos between 1 and 9),
  ninos int not null default 0 check (ninos between 0 and 8),
  bebes int not null default 0 check (bebes between 0 and 8),
  maletas_cabina int not null default 0 check (maletas_cabina >= 0),
  maletas_20kg int not null default 0 check (maletas_20kg >= 0),
  -- aplicar los descuentos del perfil (familia numerosa / residente) a estos pasajeros
  aplicar_descuentos boolean not null default true,
  -- preferencias de vuelo
  escalas_max int not null default 1 check (escalas_max between 0 and 2),
  escala_max_horas int not null default 6 check (escala_max_horas between 1 and 24),
  -- precio: 'presupuesto' (total máximo) o 'mas_barato' (decide el algoritmo)
  modo_precio text not null default 'mas_barato' check (modo_precio in ('presupuesto', 'mas_barato')),
  presupuesto numeric(10, 2) check (presupuesto is null or presupuesto > 0),
  -- estado interno del robot
  activa boolean not null default true,
  proxima_revision timestamptz not null default now(),
  ultima_revision timestamptz,
  mejor_precio numeric(10, 2),
  precio_actual numeric(10, 2),
  ultimo_aviso_precio numeric(10, 2),
  ultimo_aviso_en timestamptz,
  aviso_final_enviado boolean not null default false,
  historial_desde timestamptz,
  estado text,
  info jsonb not null default '{}'::jsonb,
  creada timestamptz not null default now(),
  constraint pasajeros_max check (adultos + ninos + bebes <= 9),
  constraint un_bebe_por_adulto check (bebes <= adultos),
  constraint maletas_por_pasajero check (maletas_cabina <= adultos + ninos and maletas_20kg <= adultos + ninos),
  constraint fechas_modo check (
    (modo = 'fechas' and fecha_ida is not null and (not ida_vuelta or fecha_vuelta >= fecha_ida))
    or (modo = 'chollo' and chollo_desde is not null and chollo_hasta >= chollo_desde
        and (not ida_vuelta or (noches_min is not null and noches_max >= noches_min)))
  ),
  constraint presupuesto_si_modo check (modo_precio <> 'presupuesto' or presupuesto is not null),
  constraint aeropuertos_distintos check (origen <> destino),
  constraint busquedas_extras_max check (
    cardinality(origenes_extra) <= 3 and cardinality(destinos_extra) <= 3
    and array_to_string(origenes_extra || destinos_extra, ',') ~ '^([A-Z]{3}(,|$))*$')
);
create index if not exists busquedas_revision_idx on public.busquedas (activa, proxima_revision);

-- ---------------------------------------------------------------------
-- Historial de precios (las mejores opciones de cada revisión)
-- ---------------------------------------------------------------------
create table if not exists public.precios (
  id bigint generated always as identity primary key,
  busqueda uuid not null references public.busquedas(id) on delete cascade,
  usuario uuid not null references auth.users(id) on delete cascade,
  revisado timestamptz not null default now(),
  fuente text not null,
  fecha_ida date,
  fecha_vuelta date,
  precio_billetes numeric(10, 2) not null,
  precio_maletas numeric(10, 2) not null default 0,
  descuento numeric(10, 2) not null default 0,
  precio_total numeric(10, 2) not null,
  maletas_estimadas boolean not null default false,
  es_mejor boolean not null default false,
  detalle jsonb not null default '{}'::jsonb
);
create index if not exists precios_busqueda_idx on public.precios (busqueda, revisado desc);
create index if not exists precios_grafica_idx on public.precios (busqueda, es_mejor, revisado);

-- ---------------------------------------------------------------------
-- Avisos enviados por Telegram
-- ---------------------------------------------------------------------
create table if not exists public.avisos (
  id bigint generated always as identity primary key,
  busqueda uuid references public.busquedas(id) on delete cascade,
  usuario uuid not null references auth.users(id) on delete cascade,
  enviado timestamptz not null default now(),
  tipo text,
  motivo text,
  precio_total numeric(10, 2),
  mensaje text,
  entregado boolean not null default false
);
create index if not exists avisos_busqueda_idx on public.avisos (busqueda, enviado desc);

-- ---------------------------------------------------------------------
-- Lista blanca de aerolíneas (solo se aceptan vuelos de las permitidas)
-- Los precios de maletas son el MÁXIMO estimado por unidad, en euros.
-- ---------------------------------------------------------------------
create table if not exists public.aerolineas (
  codigo text primary key check (codigo ~ '^[A-Z0-9]{2}$'),
  nombre text not null,
  permitida boolean not null default true,
  criterio text,
  web_oficial text,
  cabina_max numeric(7, 2) not null default 60,
  facturada_nacional_max numeric(7, 2) not null default 130,
  facturada_europa_max numeric(7, 2) not null default 130,
  facturada_largo_max numeric(7, 2) not null default 150,
  cobra_por text not null default 'tramo' check (cobra_por in ('tramo', 'trayecto')),
  bebe_tasa numeric(7, 2),
  notas text,
  actualizada timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Estado de cada web consultada (ritmo, bloqueos, errores)
-- ---------------------------------------------------------------------
create table if not exists public.estado_fuentes (
  fuente text primary key,
  nombre text not null,
  activa boolean not null default true,
  intervalo_min int not null,
  pausa_min_s int not null,
  pausa_max_s int not null,
  max_peticiones int not null default 50,
  ultima_ronda timestamptz,
  ultima_ok timestamptz,
  bloqueada_hasta timestamptz,
  bloqueos_seguidos int not null default 0,
  ultimo_error text,
  descripcion text
);

-- ---------------------------------------------------------------------
-- Ejecuciones del robot (para el panel y el consumo de minutos)
-- ---------------------------------------------------------------------
create table if not exists public.ejecuciones (
  id bigint generated always as identity primary key,
  inicio timestamptz not null default now(),
  fin timestamptz,
  duracion_s int,
  resumen jsonb not null default '{}'::jsonb
);
create index if not exists ejecuciones_inicio_idx on public.ejecuciones (inicio desc);

-- Ajustes internos del robot (p. ej. último mensaje leído de Telegram)
create table if not exists public.ajustes (
  clave text primary key,
  valor jsonb
);

-- =====================================================================
-- Registro: un solo usuario y creación automática del perfil
-- =====================================================================
create or replace function public.solo_un_usuario()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if exists (select 1 from auth.users) then
    raise exception 'Registro cerrado: esta web es de un solo usuario.';
  end if;
  return new;
end;
$$;


create or replace function public.crear_perfil()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.perfiles (id) values (new.id) on conflict (id) do nothing;
  return new;
end;
$$;

-- Supabase no deja borrar triggers de auth.users (no somos sus dueños), así que
-- solo se crean si todavía no existen: el script se puede ejecutar varias veces.
do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'solo_un_usuario' and tgrelid = 'auth.users'::regclass) then
    create trigger solo_un_usuario before insert on auth.users
      for each row execute function public.solo_un_usuario();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'crear_perfil' and tgrelid = 'auth.users'::regclass) then
    create trigger crear_perfil after insert on auth.users
      for each row execute function public.crear_perfil();
  end if;
end;
$$;

-- Al cambiar algo de una búsqueda desde la web, se revisa en la siguiente ronda.
-- Si cambia el viaje en sí (ruta, fechas, pasajeros, maletas, filtros), el historial
-- anterior deja de compararse y los avisos empiezan de cero.
create or replace function public.reprogramar_busqueda()
returns trigger language plpgsql set search_path = public as $$
begin
  if auth.uid() is not null then
    new.proxima_revision := now();
    if (new.modo, new.ida_vuelta, new.origen, new.destino, new.origenes_extra, new.destinos_extra, new.fecha_ida, new.fecha_vuelta, new.flex_dias,
        new.chollo_desde, new.chollo_hasta, new.noches_min, new.noches_max,
        new.ida_salida_min, new.ida_salida_max, new.ida_llegada_min, new.ida_llegada_max,
        new.vuelta_salida_min, new.vuelta_salida_max, new.vuelta_llegada_min, new.vuelta_llegada_max,
        new.adultos, new.ninos, new.bebes, new.maletas_cabina, new.maletas_20kg, new.aplicar_descuentos,
        new.escalas_max, new.escala_max_horas, new.fechas_extra, new.tramos_viaje)
       is distinct from
       (old.modo, old.ida_vuelta, old.origen, old.destino, old.origenes_extra, old.destinos_extra, old.fecha_ida, old.fecha_vuelta, old.flex_dias,
        old.chollo_desde, old.chollo_hasta, old.noches_min, old.noches_max,
        old.ida_salida_min, old.ida_salida_max, old.ida_llegada_min, old.ida_llegada_max,
        old.vuelta_salida_min, old.vuelta_salida_max, old.vuelta_llegada_min, old.vuelta_llegada_max,
        old.adultos, old.ninos, old.bebes, old.maletas_cabina, old.maletas_20kg, old.aplicar_descuentos,
        old.escalas_max, old.escala_max_horas, old.fechas_extra, old.tramos_viaje) then
      new.historial_desde := now();
      new.mejor_precio := null;
      new.precio_actual := null;
      new.ultimo_aviso_precio := null;
      new.aviso_final_enviado := false;
      new.estado := 'Cambios guardados: pendiente de revisión';
      new.info := '{}'::jsonb;
    elsif new.modo_precio is distinct from old.modo_precio
       or new.presupuesto is distinct from old.presupuesto then
      new.ultimo_aviso_precio := null;
      new.aviso_final_enviado := false;
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists reprogramar_busqueda on public.busquedas;
create trigger reprogramar_busqueda before update on public.busquedas
  for each row execute function public.reprogramar_busqueda();

-- =====================================================================
-- Seguridad: cada usuario solo ve lo suyo. El robot usa la clave
-- "service_role", que se salta estas reglas.
-- =====================================================================
alter table public.perfiles enable row level security;
alter table public.busquedas enable row level security;
alter table public.precios enable row level security;
alter table public.avisos enable row level security;
alter table public.aerolineas enable row level security;
alter table public.estado_fuentes enable row level security;
alter table public.ejecuciones enable row level security;
alter table public.ajustes enable row level security;

drop policy if exists "perfil propio: leer" on public.perfiles;
create policy "perfil propio: leer" on public.perfiles
  for select to authenticated using (id = auth.uid());
drop policy if exists "perfil propio: editar" on public.perfiles;
create policy "perfil propio: editar" on public.perfiles
  for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "busquedas propias" on public.busquedas;
create policy "busquedas propias" on public.busquedas
  for all to authenticated using (usuario = auth.uid()) with check (usuario = auth.uid());

drop policy if exists "precios propios" on public.precios;
create policy "precios propios" on public.precios
  for select to authenticated using (usuario = auth.uid());

drop policy if exists "avisos propios" on public.avisos;
create policy "avisos propios" on public.avisos
  for select to authenticated using (usuario = auth.uid());

drop policy if exists "aerolineas: leer" on public.aerolineas;
create policy "aerolineas: leer" on public.aerolineas
  for select to authenticated using (true);
drop policy if exists "aerolineas: editar" on public.aerolineas;
create policy "aerolineas: editar" on public.aerolineas
  for all to authenticated using (true) with check (true);

drop policy if exists "fuentes: leer" on public.estado_fuentes;
create policy "fuentes: leer" on public.estado_fuentes
  for select to authenticated using (true);
drop policy if exists "fuentes: editar" on public.estado_fuentes;
create policy "fuentes: editar" on public.estado_fuentes
  for update to authenticated using (true) with check (true);

drop policy if exists "ejecuciones: leer" on public.ejecuciones;
create policy "ejecuciones: leer" on public.ejecuciones
  for select to authenticated using (true);

-- =====================================================================
-- Webs consultadas. intervalo_min = referencia + 20 minutos de margen.
-- =====================================================================
insert into public.estado_fuentes
  (fuente, nombre, activa, intervalo_min, pausa_min_s, pausa_max_s, max_peticiones, descripcion)
values
  ('google_flights', 'Google Flights', true, 2, 6, 16, 60,
   'Fuente principal: compara casi todas las aerolíneas (Ryanair, Vueling, Iberia, easyJet...). Cada búsqueda se revisa cada 20 min (cada 40 si el viaje es dentro de más de 2 meses); 6-16 s entre peticiones.'),
  ('ryanair', 'Ryanair (web oficial)', true, 10, 120, 140, 1,
   'Confirma el precio en la propia Ryanair. Una consulta cada 10 min como mucho (menos de lo que recomiendan).'),
  ('skyscanner', 'Skyscanner', false, 740, 30, 60, 2,
   'Desactivada: Skyscanner bloquea a los robots desde la primera petición (prueba del 6/10/2026). Puedes activarla para reintentar; si bloquea, el robot la deja descansar.')
on conflict (fuente) do update set
  nombre = excluded.nombre, descripcion = excluded.descripcion;

-- =====================================================================
-- Actualización v2 (robot continuo y web en tiempo real).
-- Sirve también para instalaciones anteriores: se puede ejecutar varias veces.
-- =====================================================================
alter table public.perfiles add column if not exists telegram_prueba boolean not null default false;

-- La web puede leer la "señal de vida" del robot (nada más de la tabla de ajustes)
drop policy if exists "ajustes: latido" on public.ajustes;
create policy "ajustes: latido" on public.ajustes
  for select to authenticated using (clave = 'latido');

-- Tiempo real: la web recibe al momento los precios nuevos y los cambios de las búsquedas
do $$
declare
  tabla text;
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach tabla in array array['precios', 'busquedas', 'avisos', 'ejecuciones', 'estado_fuentes'] loop
      if not exists (
        select 1 from pg_publication_tables
        where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = tabla
      ) then
        execute format('alter publication supabase_realtime add table public.%I', tabla);
      end if;
    end loop;
  end if;
end;
$$;

-- =====================================================================
-- Actualización v3: varios aeropuertos de salida y de llegada por búsqueda
-- =====================================================================
alter table public.busquedas add column if not exists origenes_extra text[] not null default '{}';
alter table public.busquedas add column if not exists destinos_extra text[] not null default '{}';
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'busquedas_extras_max') then
    alter table public.busquedas add constraint busquedas_extras_max check (
      cardinality(origenes_extra) <= 3 and cardinality(destinos_extra) <= 3
    and array_to_string(origenes_extra || destinos_extra, ',') ~ '^([A-Z]{3}(,|$))*$');
  end if;
end;
$$;

-- =====================================================================
-- Actualización v5: alarma en el móvil con ntfy (sustituye a la llamada de CallMeBot de la v4)
-- =====================================================================
alter table public.perfiles drop constraint if exists perfiles_telegram_usuario_formato;
alter table public.perfiles drop column if exists telegram_usuario;
alter table public.perfiles drop column if exists llamar_chollos;
alter table public.perfiles drop column if exists llamada_prueba;
alter table public.perfiles add column if not exists ntfy_tema text;
alter table public.perfiles add column if not exists alarma_chollos boolean not null default false;
alter table public.perfiles add column if not exists alarma_prueba boolean not null default false;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'perfiles_ntfy_tema_formato') then
    alter table public.perfiles add constraint perfiles_ntfy_tema_formato check (
      ntfy_tema is null or ntfy_tema ~ '^[A-Za-z0-9_-]{16,64}$');
  end if;
end;
$$;

-- =====================================================================
-- Actualización v6: horario «solo Telegram» para la alarma del móvil
-- (días 1 = lunes … 7 = domingo; si pasa de medianoche cuenta el día en que empieza)
-- =====================================================================
alter table public.perfiles add column if not exists ntfy_pausa boolean not null default false;
alter table public.perfiles add column if not exists ntfy_pausa_desde time not null default '09:00';
alter table public.perfiles add column if not exists ntfy_pausa_hasta time not null default '14:00';
alter table public.perfiles add column if not exists ntfy_pausa_dias smallint[] not null default '{1,2,3,4,5,6,7}';
alter table public.perfiles add column if not exists zona_horaria text not null default 'Europe/Madrid';
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'perfiles_ntfy_pausa_valida') then
    alter table public.perfiles add constraint perfiles_ntfy_pausa_valida check (
      ntfy_pausa_dias <@ array[1, 2, 3, 4, 5, 6, 7]::smallint[]
      and zona_horaria ~ '^[A-Za-z0-9_+/-]{1,64}$');
  end if;
end;
$$;

-- =====================================================================
-- Actualización v7: seguridad reforzada
-- =====================================================================
-- 1) Sin sesión no se puede ni mirar la estructura de las tablas (la web siempre entra con sesión;
--    el robot usa la clave secreta). Las reglas RLS ya impedían leer datos: esto cierra hasta el esquema.
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke all on sequences from anon;

-- 2) Datos válidos aunque alguien use la API directamente, sin pasar por la web
--    Antes se ajusta lo que ya hubiera fuera de las reglas (normalmente nada), para que el robot
--    pueda seguir actualizando esas filas.
update public.perfiles set nombre = left(nombre, 60) where char_length(nombre) > 60;
update public.perfiles set telegram_codigo = null where telegram_codigo !~ '^[A-Z0-9]{8,12}$';
update public.aerolineas set web_oficial = regexp_replace(web_oficial, '^http://', 'https://') where web_oficial ~ '^http://';
update public.aerolineas set web_oficial = null
  where web_oficial <> '' and not (web_oficial ~ '^https://[^[:space:]"''<>]+$' and char_length(web_oficial) <= 300);
update public.aerolineas set nombre = left(nombre, 80), criterio = left(criterio, 300), notas = left(notas, 1000)
  where char_length(nombre) > 80 or char_length(criterio) > 300 or char_length(notas) > 1000;
update public.busquedas set nombre = left(nombre, 80) where char_length(nombre) > 80;
update public.busquedas set nombre = 'Búsqueda' where char_length(nombre) = 0;
update public.estado_fuentes set intervalo_min = least(greatest(intervalo_min, 1), 10080),
  pausa_min_s = least(greatest(pausa_min_s, 1), 3600), max_peticiones = least(greatest(max_peticiones, 1), 500)
  where not (intervalo_min between 1 and 10080 and pausa_min_s between 1 and 3600 and max_peticiones between 1 and 500);
update public.estado_fuentes set pausa_max_s = least(greatest(pausa_max_s, pausa_min_s), 3600)
  where not (pausa_max_s between pausa_min_s and 3600);
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'aerolineas_web_https') then
    alter table public.aerolineas add constraint aerolineas_web_https check (
      web_oficial is null or web_oficial = '' or (web_oficial ~ '^https://[^[:space:]"''<>]+$' and char_length(web_oficial) <= 300)) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'aerolineas_textos_largo') then
    alter table public.aerolineas add constraint aerolineas_textos_largo check (
      char_length(nombre) between 1 and 80 and coalesce(char_length(criterio), 0) <= 300
      and coalesce(char_length(notas), 0) <= 1000) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'busquedas_nombre_largo') then
    alter table public.busquedas add constraint busquedas_nombre_largo check (char_length(nombre) between 1 and 80) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'perfiles_campos_validos') then
    alter table public.perfiles add constraint perfiles_campos_validos check (
      coalesce(char_length(nombre), 0) <= 60
      and (telegram_codigo is null or telegram_codigo ~ '^[A-Z0-9]{8,12}$')
      and (telegram_chat_id is null or telegram_chat_id ~ '^-?[0-9]{1,20}$')) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'estado_fuentes_limites') then
    alter table public.estado_fuentes add constraint estado_fuentes_limites check (
      intervalo_min between 1 and 10080 and pausa_min_s between 1 and 3600
      and pausa_max_s between pausa_min_s and 3600 and max_peticiones between 1 and 500) not valid;
  end if;
end;
$$;

-- 3) El chat de Telegram solo lo vincula el robot al recibir tu código: desde la web (o con tu sesión
--    robada) se puede desvincular, pero no desviar tus avisos a otro chat.
create or replace function public.proteger_perfil()
returns trigger language plpgsql set search_path = public as $$
begin
  if auth.uid() is not null and new.telegram_chat_id is not null
     and new.telegram_chat_id is distinct from old.telegram_chat_id then
    raise exception 'El chat de Telegram solo se vincula enviando el código al bot.';
  end if;
  return new;
end;
$$;
drop trigger if exists proteger_perfil on public.perfiles;
create trigger proteger_perfil before update on public.perfiles
  for each row execute function public.proteger_perfil();

-- =====================================================================
-- Actualización v8: aviso por Telegram cada vez que alguien entra en tu cuenta
-- =====================================================================
-- Supabase apunta cada acceso (hora, IP y tipo) en auth.audit_log_entries, una tabla que la API
-- no deja leer. Esta función le pasa al robot solo esos tres datos (ni correos ni identificadores).
-- Se omiten las renovaciones automáticas de la sesión (token_refreshed / token_revoked): no son entrar.
create or replace function public.accesos_desde(desde timestamptz)
returns table (created_at timestamptz, ip_address text, accion text)
language sql stable security definer set search_path = public, auth as $$
  select e.created_at, e.ip_address::text, e.payload ->> 'action'
  from auth.audit_log_entries e
  where e.created_at > desde
    and coalesce(e.payload ->> 'action', '') not in ('token_refreshed', 'token_revoked')
  order by e.created_at
  limit 200;
$$;
-- Solo el robot (clave secreta) puede usarla: ni sin sesión ni con tu sesión de la web
revoke execute on function public.accesos_desde(timestamptz) from public, anon, authenticated;
grant execute on function public.accesos_desde(timestamptz) to service_role;

-- =====================================================================
-- Actualización v9: varias fechas en una misma búsqueda y viajes con varios destinos
-- =====================================================================
-- fechas_extra: otras fechas del mismo viaje, [{"ida": "2026-11-20", "vuelta": "2026-11-23"}, ...] (hasta 5)
-- tramos_viaje: viaje con varios destinos, [{"origen": "SVQ", "destino": "KRK", "fecha": "2026-11-13"}, ...] (2 a 5)
alter table public.busquedas add column if not exists fechas_extra jsonb not null default '[]'::jsonb;
alter table public.busquedas add column if not exists tramos_viaje jsonb not null default '[]'::jsonb;

create or replace function public.fechas_extra_validas(f jsonb)
returns boolean language sql immutable set search_path = public as $$
  select jsonb_typeof(f) = 'array' and jsonb_array_length(f) <= 5
    and not exists (
      select 1 from jsonb_array_elements(f) e
      where jsonb_typeof(e) <> 'object'
         or coalesce(e ->> 'ida', '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
         or (coalesce(e ->> 'vuelta', '') <> '' and (e ->> 'vuelta' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
             or e ->> 'vuelta' < e ->> 'ida')))
$$;

create or replace function public.tramos_viaje_validos(t jsonb)
returns boolean language sql immutable set search_path = public as $$
  select jsonb_typeof(t) = 'array' and jsonb_array_length(t) <= 5 and jsonb_array_length(t) <> 1
    and not exists (
      select 1 from jsonb_array_elements(t) e
      where jsonb_typeof(e) <> 'object'
         or coalesce(e ->> 'origen', '') !~ '^[A-Z]{3}$' or coalesce(e ->> 'destino', '') !~ '^[A-Z]{3}$'
         or e ->> 'origen' = e ->> 'destino'
         or coalesce(e ->> 'fecha', '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    -- en orden: cada vuelo, el mismo día que el anterior o después
    and not exists (
      select 1 from jsonb_array_elements(t) with ordinality a(e, i)
      join jsonb_array_elements(t) with ordinality b(e, i) on b.i = a.i + 1
      where b.e ->> 'fecha' < a.e ->> 'fecha')
$$;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'busquedas_viaje_valido') then
    alter table public.busquedas add constraint busquedas_viaje_valido check (
      public.fechas_extra_validas(fechas_extra) and public.tramos_viaje_validos(tramos_viaje)
      -- un viaje con varios destinos va con fechas concretas, sin vuelta aparte ni fechas alternativas
      and (tramos_viaje = '[]'::jsonb or (modo = 'fechas' and not ida_vuelta and fechas_extra = '[]'::jsonb))
      and (fechas_extra = '[]'::jsonb or modo = 'fechas')) not valid;
  end if;
end;
$$;

-- Que la API de Supabase vea al momento las columnas nuevas
notify pgrst, 'reload schema';

-- =====================================================================
-- Lista blanca inicial de aerolíneas (ver docs/INVESTIGACION.md)
-- =====================================================================
insert into public.aerolineas (codigo, nombre, permitida, criterio, web_oficial, cabina_max, facturada_nacional_max, facturada_europa_max, facturada_largo_max, cobra_por, bebe_tasa, notas) values
  ('IB', 'Iberia', true, 'AirlineRatings 2026: top 25 tradicionales (nº20)', 'https://www.iberia.com', 0, 57, 95, 135, 'trayecto', null, 'Maleta de cabina incluida en sus tarifas. Facturada 23 kg: 18-57 € España, 20-95 € Europa, 50-135 € larga distancia (online).'),
  ('I2', 'Iberia Express', true, 'Grupo Iberia (IAG). Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.iberia.com', 0, 57, 95, 135, 'trayecto', null, 'Se vende en iberia.com. Mismas condiciones de equipaje que Iberia.'),
  ('YW', 'Air Nostrum (Iberia Regional)', true, 'Opera para Iberia. Auditoría IOSA, certificada en la UE', 'https://www.iberia.com', 0, 57, 95, 135, 'trayecto', null, 'Se vende en iberia.com.'),
  ('UX', 'Air Europa', true, 'AirlineRatings 7/7 (Seven Star PLUS, 2026)', 'https://www.aireuropa.com', 0, 60, 80, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente.'),
  ('X5', 'Air Europa Express', true, 'Grupo Air Europa, certificada en la UE', 'https://www.aireuropa.com', 0, 60, 80, 120, 'trayecto', null, 'Se vende en aireuropa.com.'),
  ('VY', 'Vueling', true, 'AirlineRatings 2026: top 25 low cost (nº12)', 'https://www.vueling.com', 50, 96, 96, 99, 'tramo', null, 'Basic solo incluye bolso 40x20x30. Facturada 20 kg: 14-96 € por vuelo (online). Cabina: estimación.'),
  ('V7', 'Volotea', true, 'AirlineRatings 7/7 y auditoría IOSA', 'https://www.volotea.com', 45, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('NT', 'Binter', true, 'AirlineRatings 7/7 y auditoría IOSA', 'https://www.bintercanarias.com', 0, 45, 60, 60, 'tramo', null, 'Estimación prudente; revisa según tarifa.'),
  ('FR', 'Ryanair', true, 'Grupo Ryanair: AirlineRatings 2026: top 25 low cost (nº18), certificada en la UE', 'https://www.ryanair.com', 40, 59.99, 59.99, 59.99, 'tramo', 25, 'Basic solo incluye bolso 40x30x20. Facturada 20 kg: 21,49-59,99 € por vuelo (online). Cabina 10 kg (Priority): estimación.'),
  ('RK', 'Ryanair UK', true, 'Grupo Ryanair: AirlineRatings 2026: top 25 low cost (nº18), certificada en la UE', 'https://www.ryanair.com', 40, 59.99, 59.99, 59.99, 'tramo', 25, 'Basic solo incluye bolso 40x30x20. Facturada 20 kg: 21,49-59,99 € por vuelo (online). Cabina 10 kg (Priority): estimación.'),
  ('AL', 'Malta Air (filial de Ryanair)', true, 'Grupo Ryanair: AirlineRatings 2026: top 25 low cost (nº18), certificada en la UE', 'https://www.ryanair.com', 40, 59.99, 59.99, 59.99, 'tramo', 25, 'Basic solo incluye bolso 40x30x20. Facturada 20 kg: 21,49-59,99 € por vuelo (online). Cabina 10 kg (Priority): estimación.'),
  ('LW', 'Lauda Europe (filial de Ryanair)', true, 'Grupo Ryanair: AirlineRatings 2026: top 25 low cost (nº18), certificada en la UE', 'https://www.ryanair.com', 40, 59.99, 59.99, 59.99, 'tramo', 25, 'Basic solo incluye bolso 40x30x20. Facturada 20 kg: 21,49-59,99 € por vuelo (online). Cabina 10 kg (Priority): estimación.'),
  ('RR', 'Buzz (filial de Ryanair)', true, 'Grupo Ryanair: AirlineRatings 2026: top 25 low cost (nº18), certificada en la UE', 'https://www.ryanair.com', 40, 59.99, 59.99, 59.99, 'tramo', 25, 'Basic solo incluye bolso 40x30x20. Facturada 20 kg: 21,49-59,99 € por vuelo (online). Cabina 10 kg (Priority): estimación.'),
  ('U2', 'easyJet', true, 'AirlineRatings 2026: top 25 low cost (nº5)', 'https://www.easyjet.com', 50, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('EC', 'easyJet Europe', true, 'AirlineRatings 2026: top 25 low cost (nº5)', 'https://www.easyjet.com', 50, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('DS', 'easyJet Switzerland', true, 'AirlineRatings 2026: top 25 low cost (nº5)', 'https://www.easyjet.com', 50, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('W6', 'Wizz Air', true, 'AirlineRatings 2026: top 25 low cost (nº9)', 'https://wizzair.com', 60, 122, 122, 122, 'tramo', null, 'Facturada 20 kg: hasta 122 € por vuelo según temporada. La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('W4', 'Wizz Air Malta', true, 'AirlineRatings 2026: top 25 low cost (nº9)', 'https://wizzair.com', 60, 122, 122, 122, 'tramo', null, 'Facturada 20 kg: hasta 122 € por vuelo según temporada. La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('W9', 'Wizz Air UK', true, 'AirlineRatings 2026: top 25 low cost (nº9)', 'https://wizzair.com', 60, 122, 122, 122, 'tramo', null, 'Facturada 20 kg: hasta 122 € por vuelo según temporada. La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('HV', 'Transavia', true, 'AirlineRatings 2026: top 25 low cost (nº20, grupo Transavia)', 'https://www.transavia.com', 45, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('TO', 'Transavia France', true, 'AirlineRatings 2026: top 25 low cost (nº20, grupo Transavia)', 'https://www.transavia.com', 45, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('EW', 'Eurowings', true, 'AirlineRatings 2026: top 25 low cost (nº21)', 'https://www.eurowings.com', 45, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('DY', 'Norwegian', true, 'AirlineRatings 2026: top 25 low cost (nº13)', 'https://www.norwegian.com', 40, 70, 70, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('D8', 'Norwegian Air Sweden', true, 'AirlineRatings 2026: top 25 low cost (nº13)', 'https://www.norwegian.com', 40, 70, 70, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('LS', 'Jet2', true, 'AirlineRatings 2026: top 25 low cost (nº17)', 'https://www.jet2.com', 0, 70, 70, 70, 'tramo', null, 'Incluye 10 kg de equipaje de mano.'),
  ('BY', 'TUI Airways', true, 'AirlineRatings 2026: top 25 low cost (nº11)', 'https://www.tui.co.uk', 0, 70, 70, 70, 'tramo', null, 'Estimación prudente.'),
  ('BT', 'airBaltic', true, 'AirlineRatings 2026: top 25 low cost (nº7)', 'https://www.airbaltic.com', 40, 70, 70, 70, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('TK', 'Turkish Airlines', true, 'AirlineRatings 2026: top 25 tradicionales (nº12, la más segura de Europa)', 'https://www.turkishairlines.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('VS', 'Virgin Atlantic', true, 'AirlineRatings 2026: top 25 tradicionales (nº13)', 'https://www.virginatlantic.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('TP', 'TAP Air Portugal', true, 'AirlineRatings 2026: top 25 tradicionales (nº16)', 'https://www.flytap.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('SK', 'SAS', true, 'AirlineRatings 2026: top 25 tradicionales (nº17)', 'https://www.flysas.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('BA', 'British Airways', true, 'AirlineRatings 2026: top 25 tradicionales (nº18)', 'https://www.britishairways.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('LH', 'Lufthansa', true, 'AirlineRatings 2026: top 25 tradicionales (nº21)', 'https://www.lufthansa.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('KL', 'KLM', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.klm.es', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('AF', 'Air France', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.airfrance.es', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('LX', 'SWISS', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.swiss.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('OS', 'Austrian Airlines', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.austrian.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('SN', 'Brussels Airlines', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.brusselsairlines.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('AZ', 'ITA Airways', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.ita-airways.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('EI', 'Aer Lingus', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.aerlingus.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('AY', 'Finnair', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.finnair.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('A3', 'Aegean Airlines', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.aegeanair.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('LO', 'LOT Polish Airlines', true, 'Certificada en la UE (EASA) y auditoría IOSA (miembro de IATA)', 'https://www.lot.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('KM', 'KM Malta Airlines', true, 'AirlineRatings 7/7 y auditoría IOSA', 'https://kmmaltairlines.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('EY', 'Etihad', true, 'AirlineRatings 2026: top 25 tradicionales (nº1)', 'https://www.etihad.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('CX', 'Cathay Pacific', true, 'AirlineRatings 2026: top 25 tradicionales (nº2)', 'https://www.cathaypacific.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('QF', 'Qantas', true, 'AirlineRatings 2026: top 25 tradicionales (nº3)', 'https://www.qantas.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('QR', 'Qatar Airways', true, 'AirlineRatings 2026: top 25 tradicionales (nº4)', 'https://www.qatarairways.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('EK', 'Emirates', true, 'AirlineRatings 2026: top 25 tradicionales (nº5)', 'https://www.emirates.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('NZ', 'Air New Zealand', true, 'AirlineRatings 2026: top 25 tradicionales (nº6)', 'https://www.airnewzealand.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('SQ', 'Singapore Airlines', true, 'AirlineRatings 2026: top 25 tradicionales (nº7)', 'https://www.singaporeair.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('BR', 'EVA Air', true, 'AirlineRatings 2026: top 25 tradicionales (nº8)', 'https://www.evaair.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('VA', 'Virgin Australia', true, 'AirlineRatings 2026: top 25 tradicionales (nº9)', 'https://www.virginaustralia.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('KE', 'Korean Air', true, 'AirlineRatings 2026: top 25 tradicionales (nº10)', 'https://www.koreanair.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('JX', 'STARLUX', true, 'AirlineRatings 2026: top 25 tradicionales (nº11)', 'https://www.starlux-airlines.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('NH', 'ANA', true, 'AirlineRatings 2026: top 25 tradicionales (nº14)', 'https://www.ana.co.jp', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('AS', 'Alaska Airlines', true, 'AirlineRatings 2026: top 25 tradicionales (nº15)', 'https://www.alaskaair.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('VN', 'Vietnam Airlines', true, 'AirlineRatings 2026: top 25 tradicionales (nº19)', 'https://www.vietnamairlines.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('AC', 'Air Canada', true, 'AirlineRatings 2026: top 25 tradicionales (nº22)', 'https://www.aircanada.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('DL', 'Delta', true, 'AirlineRatings 2026: top 25 tradicionales (nº23)', 'https://www.delta.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('AA', 'American Airlines', true, 'AirlineRatings 2026: top 25 tradicionales (nº24)', 'https://www.aa.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('FJ', 'Fiji Airways', true, 'AirlineRatings 2026: top 25 tradicionales (nº25)', 'https://www.fijiairways.com', 0, 70, 70, 120, 'trayecto', null, 'Maleta de cabina incluida. Facturada: estimación prudente para tarifas sin maleta.'),
  ('UO', 'HK Express', true, 'AirlineRatings 2026: top 25 low cost (nº1)', 'https://www.hkexpress.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('JQ', 'Jetstar', true, 'AirlineRatings 2026: top 25 low cost (nº2)', 'https://www.jetstar.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('TR', 'Scoot', true, 'AirlineRatings 2026: top 25 low cost (nº3)', 'https://www.flyscoot.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('FZ', 'flydubai', true, 'AirlineRatings 2026: top 25 low cost (nº4)', 'https://www.flydubai.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('WN', 'Southwest', true, 'AirlineRatings 2026: top 25 low cost (nº6)', 'https://www.southwest.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('VJ', 'VietJet Air', true, 'AirlineRatings 2026: top 25 low cost (nº8)', 'https://www.vietjetair.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('AK', 'AirAsia', true, 'AirlineRatings 2026: top 25 low cost (nº10)', 'https://www.airasia.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('B6', 'JetBlue', true, 'AirlineRatings 2026: top 25 low cost (nº14)', 'https://www.jetblue.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('XY', 'flynas', true, 'AirlineRatings 2026: top 25 low cost (nº15)', 'https://www.flynas.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('5J', 'Cebu Pacific', true, 'AirlineRatings 2026: top 25 low cost (nº16)', 'https://www.cebupacificair.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('9C', 'Spring Airlines', true, 'AirlineRatings 2026: top 25 low cost (nº19)', 'https://en.ch.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('Y4', 'Volaris', true, 'AirlineRatings 2026: top 25 low cost (nº22)', 'https://www.volaris.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('WS', 'WestJet', true, 'AirlineRatings 2026: top 25 low cost (nº23)', 'https://www.westjet.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('G3', 'GOL', true, 'AirlineRatings 2026: top 25 low cost (nº24)', 'https://www.voegol.com.br', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).'),
  ('H2', 'SKY Airline', true, 'AirlineRatings 2026: top 25 low cost (nº25)', 'https://www.skyairline.com', 50, 80, 80, 80, 'tramo', null, 'La tarifa básica solo incluye un bolso pequeño; maletas = máximo publicado (estimación).')
on conflict (codigo) do nothing;

-- Comprobación final (debe salir: 8 tablas, 77 aerolíneas, 3 webs, versión 2 = 1, versión 3 = 2, versión 5 = 3, versión 6 = 5, versión 7 = 6, versión 8 = 1, versión 9 = 2;
-- accesos registrados por Supabase: más de 0 si has usado la web este mes)
select 'Tablas creadas' as comprobacion, count(*) as total from information_schema.tables
  where table_schema = 'public' and table_name in
  ('perfiles','busquedas','precios','avisos','aerolineas','estado_fuentes','ejecuciones','ajustes')
union all select 'Aerolíneas en la lista blanca', count(*) from public.aerolineas
union all select 'Webs configuradas', count(*) from public.estado_fuentes
union all select 'Versión 2 instalada (tiempo real y Telegram)', count(*) from information_schema.columns
  where table_schema = 'public' and table_name = 'perfiles' and column_name = 'telegram_prueba'
union all select 'Versión 3 instalada (varios aeropuertos)', count(*) from information_schema.columns
  where table_schema = 'public' and table_name = 'busquedas' and column_name in ('origenes_extra', 'destinos_extra')
union all select 'Versión 5 instalada (alarma en el móvil)', count(*) from information_schema.columns
  where table_schema = 'public' and table_name = 'perfiles'
  and column_name in ('ntfy_tema', 'alarma_chollos', 'alarma_prueba')
union all select 'Versión 6 instalada (horario solo Telegram)', count(*) from information_schema.columns
  where table_schema = 'public' and table_name = 'perfiles'
  and column_name in ('ntfy_pausa', 'ntfy_pausa_desde', 'ntfy_pausa_hasta', 'ntfy_pausa_dias', 'zona_horaria')
union all select 'Versión 7 instalada (seguridad reforzada)', (select count(*) from pg_constraint where conname in
  ('aerolineas_web_https', 'aerolineas_textos_largo', 'busquedas_nombre_largo', 'perfiles_campos_validos',
   'estado_fuentes_limites')) + (select count(*) from pg_trigger where tgname = 'proteger_perfil')
union all select 'Versión 8 instalada (avisos de acceso)', count(*) from pg_proc
  where proname = 'accesos_desde' and pronamespace = 'public'::regnamespace
  and not has_function_privilege('anon', oid, 'execute') and not has_function_privilege('authenticated', oid, 'execute')
union all select 'Versión 9 instalada (varias fechas y varios destinos)', count(*) from information_schema.columns
  where table_schema = 'public' and table_name = 'busquedas' and column_name in ('fechas_extra', 'tramos_viaje')
union all select 'Accesos registrados por Supabase (últimos 30 días)', count(*) from auth.audit_log_entries
  where created_at > now() - interval '30 days';
