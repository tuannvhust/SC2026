-- Đưa customers.name về ngay sau customer_id và đổi status provisional thành active.
-- PostgreSQL không đổi vị trí cột bằng ALTER COLUMN, nên tạo lại bảng.

ALTER TABLE public.callbacks
  DROP CONSTRAINT callbacks_customer_id_fkey;
ALTER TABLE public.conversation_sessions
  DROP CONSTRAINT conversation_sessions_customer_id_fkey;
ALTER TABLE public.episodes
  DROP CONSTRAINT episodes_customer_id_fkey;
ALTER TABLE public.orders
  DROP CONSTRAINT orders_customer_id_fkey;
ALTER TABLE public.profile_facts
  DROP CONSTRAINT profile_facts_customer_id_fkey;

CREATE TABLE public.customers_ordered (
    customer_id text PRIMARY KEY,
    name text,
    honorific text,
    status text,
    phone text,
    zalo_id text UNIQUE,
    fb_id text UNIQUE,
    region text,
    address_line text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.customers_ordered (
    customer_id,
    name,
    honorific,
    status,
    phone,
    zalo_id,
    fb_id,
    region,
    address_line,
    created_at,
    updated_at
)
SELECT
    customer_id,
    name,
    honorific,
    CASE WHEN status = 'provisional' THEN 'active' ELSE status END,
    phone,
    zalo_id,
    fb_id,
    region,
    address_line,
    created_at,
    updated_at
FROM public.customers;

DROP TABLE public.customers;
ALTER TABLE public.customers_ordered RENAME TO customers;

ALTER TABLE public.customers
  RENAME CONSTRAINT customers_ordered_pkey TO customers_pkey;
ALTER TABLE public.customers
  RENAME CONSTRAINT customers_ordered_zalo_id_key TO customers_zalo_id_key;
ALTER TABLE public.customers
  RENAME CONSTRAINT customers_ordered_fb_id_key TO customers_fb_id_key;

ALTER TABLE public.callbacks
  ADD CONSTRAINT callbacks_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE CASCADE;
ALTER TABLE public.conversation_sessions
  ADD CONSTRAINT conversation_sessions_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE SET NULL;
ALTER TABLE public.episodes
  ADD CONSTRAINT episodes_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE SET NULL;
ALTER TABLE public.orders
  ADD CONSTRAINT orders_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE RESTRICT;
ALTER TABLE public.profile_facts
  ADD CONSTRAINT profile_facts_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE CASCADE;

ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE public.customers TO anon, authenticated, service_role;
