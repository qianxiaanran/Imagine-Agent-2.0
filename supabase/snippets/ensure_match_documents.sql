-- Ensure RPC function used by Backend/documents_processing.py exists.
-- Expected signature in code:
-- public.match_documents(filter, match_count, match_threshold, query_embedding)

create or replace function public.match_documents(
  filter jsonb,
  match_count int,
  match_threshold float,
  query_embedding vector(512)
)
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language sql
stable
as $$
  select
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) as similarity
  from public.documents d
  where d.metadata @> filter
    and (1 - (d.embedding <=> query_embedding)) > match_threshold
  order by d.embedding <=> query_embedding
  limit greatest(match_count, 1);
$$;

grant execute on function public.match_documents(jsonb, int, float, vector)
to anon, authenticated, service_role;

-- Refresh PostgREST schema cache for RPC discovery.
notify pgrst, 'reload schema';
