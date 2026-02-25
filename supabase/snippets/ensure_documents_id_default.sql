-- Ensure public.documents.id has an auto-increment default
-- Compatible with existing bigint PK data.

do $$
begin
  if not exists (
    select 1
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'S'
      and c.relname = 'documents_id_seq'
      and n.nspname = 'public'
  ) then
    create sequence public.documents_id_seq;
  end if;

  alter sequence public.documents_id_seq owned by public.documents.id;

  perform setval(
    'public.documents_id_seq',
    coalesce((select max(id) from public.documents), 0) + 1,
    false
  );

  alter table public.documents
    alter column id set default nextval('public.documents_id_seq');
end $$;

