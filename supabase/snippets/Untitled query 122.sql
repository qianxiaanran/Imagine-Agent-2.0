-- 1) 将 auth.users 的 app_metadata.role 设为 admin
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
                      || jsonb_build_object('role', 'admin')
where id = '9374a7f3-0e5f-42bf-9661-db6a783b9a29';

-- 2) 同步 profiles.role（没有则插入，有则更新）
insert into public.profiles (id, email, role, status, created_at, updated_at)
select
  id,
  email,
  'admin' as role,
  'active' as status,
  now(),
  now()
from auth.users
where id = '9374a7f3-0e5f-42bf-9661-db6a783b9a29'
on conflict (id) do update
set role = 'admin',
    status = 'active',
    updated_at = now();

-- 3) 验证
select
  u.id,
  u.email,
  u.raw_app_meta_data->>'role' as app_role,
  p.role as profile_role,
  p.status
from auth.users u
left join public.profiles p on p.id = u.id
where u.id = '9374a7f3-0e5f-42bf-9661-db6a783b9a29';
