-- 失物招领共享频道表结构 + 行级安全策略
-- 在 Supabase 的 SQL Editor 里直接执行一次即可。
-- 说明：这是竞赛演示用途，RLS 策略放开为公开读写，方便访客直接发布/浏览；
--       正式上线应改成「登录后写、公开读」，并限制 update/delete。

create table if not exists public.lost_found (
  id             uuid primary key default gen_random_uuid(),
  type           text not null check (type in ('lost', 'found')),       -- lost=寻物 found=拾到
  item_type      text not null,                                          -- 校园卡/手机/钱包/...
  title          text not null,
  description    text,
  location       text,
  lost_time      text,
  contact        text,
  secret_question text,                                                   -- 防冒领隐藏问题（拾到者设）
  secret_answer  text,                                                    -- 隐藏问题答案
  status         text not null default 'open' check (status in ('open', 'matched', 'resolved')),
  matched_with   uuid,                                                    -- 匹配到的对面帖子 id
  confirmed      boolean not null default false,                          -- 本帖子一方是否已确认交接（双方都确认才 resolved）
  secret_token   text,                                                    -- 发布口令：只有知道口令的人能管理（标记找回/确认/删除）这条帖子
  created_at     timestamptz not null default now()
);

alter table public.lost_found enable row level security;

-- 演示用：公开读 / 公开写 / 公开改 / 公开删（正式上线请收紧）
create policy "public_select" on public.lost_found for select using (true);
create policy "public_insert" on public.lost_found for insert with check (true);
create policy "public_update" on public.lost_found for update using (true);
create policy "public_delete" on public.lost_found for delete using (true);

-- 已建过表的项目：补上「双方确认」和「发布口令」字段（幂等，可重复执行）
alter table public.lost_found add column if not exists confirmed boolean not null default false;
alter table public.lost_found add column if not exists secret_token text;
