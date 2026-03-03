BEGIN;

-- Core lookup and join indexes
CREATE INDEX IF NOT EXISTS idx_departments_parent_dept_id ON public.departments(parent_dept_id);
CREATE INDEX IF NOT EXISTS idx_departments_manager_id ON public.departments(manager_id);
CREATE INDEX IF NOT EXISTS idx_roles_role_name ON public.roles(role_name);

CREATE INDEX IF NOT EXISTS idx_employees_emp_no ON public.employees(emp_no);
CREATE INDEX IF NOT EXISTS idx_employees_dept_id ON public.employees(dept_id);
CREATE INDEX IF NOT EXISTS idx_employees_role_id ON public.employees(role_id);
CREATE INDEX IF NOT EXISTS idx_employees_status_hire_date ON public.employees(status, hire_date DESC);

CREATE INDEX IF NOT EXISTS idx_customers_cust_no ON public.customers(cust_no);
CREATE INDEX IF NOT EXISTS idx_customers_sales_id ON public.customers(sales_id);
CREATE INDEX IF NOT EXISTS idx_customers_type_level ON public.customers(cust_type, cust_level);
CREATE INDEX IF NOT EXISTS idx_customers_cust_name_lower ON public.customers((lower(cust_name)));

CREATE INDEX IF NOT EXISTS idx_suppliers_supp_no ON public.suppliers(supp_no);
CREATE INDEX IF NOT EXISTS idx_suppliers_rating ON public.suppliers(rating);
CREATE INDEX IF NOT EXISTS idx_suppliers_supp_name_lower ON public.suppliers((lower(supp_name)));

CREATE INDEX IF NOT EXISTS idx_products_prod_no ON public.products(prod_no);
CREATE INDEX IF NOT EXISTS idx_products_category_status ON public.products(category, status);
CREATE INDEX IF NOT EXISTS idx_products_prod_name_lower ON public.products((lower(prod_name)));

CREATE INDEX IF NOT EXISTS idx_inventory_prod_id ON public.inventory(prod_id);
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse ON public.inventory(warehouse);
CREATE INDEX IF NOT EXISTS idx_inventory_prod_warehouse ON public.inventory(prod_id, warehouse);

-- Sales order hotspots
CREATE INDEX IF NOT EXISTS idx_orders_order_no ON public.orders(order_no);
CREATE INDEX IF NOT EXISTS idx_orders_order_date_desc ON public.orders(order_date DESC, order_id DESC);
CREATE INDEX IF NOT EXISTS idx_orders_cust_order_date_desc ON public.orders(cust_id, order_date DESC, order_id DESC);
CREATE INDEX IF NOT EXISTS idx_orders_emp_order_date_desc ON public.orders(emp_id, order_date DESC, order_id DESC);
CREATE INDEX IF NOT EXISTS idx_orders_payment_delivery_date ON public.orders(payment_status, delivery_status, order_date DESC);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON public.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_prod_id ON public.order_items(prod_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_prod ON public.order_items(order_id, prod_id);

-- Purchase order hotspots
CREATE INDEX IF NOT EXISTS idx_purchases_purchase_no ON public.purchases(purchase_no);
CREATE INDEX IF NOT EXISTS idx_purchases_purchase_date_desc ON public.purchases(purchase_date DESC, purchase_id DESC);
CREATE INDEX IF NOT EXISTS idx_purchases_supp_purchase_date_desc ON public.purchases(supp_id, purchase_date DESC, purchase_id DESC);
CREATE INDEX IF NOT EXISTS idx_purchases_emp_purchase_date_desc ON public.purchases(emp_id, purchase_date DESC, purchase_id DESC);
CREATE INDEX IF NOT EXISTS idx_purchases_status_purchase_date ON public.purchases(status, purchase_date DESC);

ANALYZE public.departments;
ANALYZE public.roles;
ANALYZE public.employees;
ANALYZE public.customers;
ANALYZE public.suppliers;
ANALYZE public.products;
ANALYZE public.inventory;
ANALYZE public.orders;
ANALYZE public.order_items;
ANALYZE public.purchases;

COMMIT;
