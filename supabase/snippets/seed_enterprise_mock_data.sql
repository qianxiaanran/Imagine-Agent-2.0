BEGIN;

DO $$
DECLARE
    v_dept_start BIGINT;
    v_role_start BIGINT;
    v_emp_start BIGINT;
    v_customer_start BIGINT;
    v_supplier_start BIGINT;
    v_product_start BIGINT;
    v_inventory_start BIGINT;
    v_order_start BIGINT;
    v_item_start BIGINT;
    v_purchase_start BIGINT;

    v_dept_add INT := 10;
    v_role_add INT := 8;
    v_emp_add INT := 180;
    v_customer_add INT := 1500;
    v_supplier_add INT := 600;
    v_product_add INT := 1000;
    v_order_add INT := 8000;
    v_purchase_add INT := 3500;
BEGIN
    SELECT COALESCE(MAX(dept_id), 0) INTO v_dept_start FROM public.departments;
    SELECT COALESCE(MAX(role_id), 0) INTO v_role_start FROM public.roles;
    SELECT COALESCE(MAX(emp_id), 0) INTO v_emp_start FROM public.employees;
    SELECT COALESCE(MAX(cust_id), 0) INTO v_customer_start FROM public.customers;
    SELECT COALESCE(MAX(supp_id), 0) INTO v_supplier_start FROM public.suppliers;
    SELECT COALESCE(MAX(prod_id), 0) INTO v_product_start FROM public.products;
    SELECT COALESCE(MAX(inv_id), 0) INTO v_inventory_start FROM public.inventory;
    SELECT COALESCE(MAX(order_id), 0) INTO v_order_start FROM public.orders;
    SELECT COALESCE(MAX(item_id), 0) INTO v_item_start FROM public.order_items;
    SELECT COALESCE(MAX(purchase_id), 0) INTO v_purchase_start FROM public.purchases;

    INSERT INTO public.departments (dept_id, dept_name, parent_dept_id, manager_id, location, description)
    SELECT
        v_dept_start + g AS dept_id,
        'Dept-' || LPAD((v_dept_start + g)::TEXT, 3, '0') AS dept_name,
        NULL::BIGINT,
        NULL::BIGINT,
        CASE g % 4
            WHEN 0 THEN 'Shenzhen'
            WHEN 1 THEN 'Guangzhou'
            WHEN 2 THEN 'Shanghai'
            ELSE 'Hangzhou'
        END AS location,
        'Seeded department ' || (v_dept_start + g)
    FROM generate_series(1, v_dept_add) AS g;

    INSERT INTO public.roles (role_id, role_name, permissions, description)
    SELECT
        v_role_start + g AS role_id,
        'Role-' || LPAD((v_role_start + g)::TEXT, 3, '0') AS role_name,
        CASE g % 4
            WHEN 0 THEN 'sales:read,sales:write'
            WHEN 1 THEN 'purchase:read,purchase:write'
            WHEN 2 THEN 'inventory:read,inventory:write'
            ELSE 'analytics:read'
        END AS permissions,
        'Seeded role ' || (v_role_start + g)
    FROM generate_series(1, v_role_add) AS g;

    INSERT INTO public.employees (
        emp_id, emp_no, emp_name, gender, birth_date, position,
        dept_id, role_id, hire_date, salary, phone, email, status
    )
    WITH dept_pool AS (
        SELECT dept_id, ROW_NUMBER() OVER (ORDER BY dept_id) - 1 AS rn FROM public.departments
    ),
    role_pool AS (
        SELECT role_id, ROW_NUMBER() OVER (ORDER BY role_id) - 1 AS rn FROM public.roles
    ),
    meta AS (
        SELECT (SELECT COUNT(*) FROM dept_pool) AS dept_total, (SELECT COUNT(*) FROM role_pool) AS role_total
    )
    SELECT
        v_emp_start + g AS emp_id,
        'EMP' || LPAD((v_emp_start + g)::TEXT, 6, '0') AS emp_no,
        'Employee-' || LPAD((v_emp_start + g)::TEXT, 6, '0') AS emp_name,
        CASE g % 2 WHEN 0 THEN 'M' ELSE 'F' END AS gender,
        (DATE '1986-01-01' + ((g * 19) % 9000))::DATE AS birth_date,
        CASE g % 5
            WHEN 0 THEN 'Sales Rep'
            WHEN 1 THEN 'Account Manager'
            WHEN 2 THEN 'Buyer'
            WHEN 3 THEN 'Warehouse Planner'
            ELSE 'Data Analyst'
        END AS position,
        dp.dept_id,
        rp.role_id,
        (CURRENT_DATE - ((g * 7) % 1800))::DATE AS hire_date,
        (7000 + ((g * 173) % 18000))::NUMERIC(14,2) AS salary,
        '138' || LPAD(((v_emp_start + g) % 100000000)::TEXT, 8, '0') AS phone,
        'employee' || (v_emp_start + g) || '@example.local' AS email,
        CASE g % 6 WHEN 0 THEN 'Inactive' ELSE 'Active' END AS status
    FROM generate_series(1, v_emp_add) AS g
    JOIN meta m ON TRUE
    JOIN dept_pool dp ON dp.rn = ((g * 5) % m.dept_total)
    JOIN role_pool rp ON rp.rn = ((g * 3) % m.role_total);

    INSERT INTO public.customers (
        cust_id, cust_no, cust_name, cust_type, cust_level,
        contact_person, phone, email, address, tax_id, payment_terms,
        credit_limit, sales_id
    )
    WITH emp_pool AS (
        SELECT emp_id, ROW_NUMBER() OVER (ORDER BY emp_id) - 1 AS rn FROM public.employees
    ),
    meta AS (
        SELECT COUNT(*) AS emp_total FROM emp_pool
    )
    SELECT
        v_customer_start + g AS cust_id,
        'CUST' || LPAD((v_customer_start + g)::TEXT, 7, '0') AS cust_no,
        'Customer-' || LPAD((v_customer_start + g)::TEXT, 7, '0') AS cust_name,
        CASE g % 4
            WHEN 0 THEN 'Enterprise'
            WHEN 1 THEN 'Retail'
            WHEN 2 THEN 'Distributor'
            ELSE 'Ecommerce'
        END AS cust_type,
        CASE g % 5
            WHEN 0 THEN 'A'
            WHEN 1 THEN 'B'
            WHEN 2 THEN 'C'
            WHEN 3 THEN 'VIP'
            ELSE 'Standard'
        END AS cust_level,
        'Contact-' || (v_customer_start + g) AS contact_person,
        '139' || LPAD(((v_customer_start + g) % 100000000)::TEXT, 8, '0') AS phone,
        'customer' || (v_customer_start + g) || '@example.local' AS email,
        'Address block #' || (v_customer_start + g) AS address,
        'TAXC' || LPAD((v_customer_start + g)::TEXT, 10, '0') AS tax_id,
        CASE g % 4
            WHEN 0 THEN 'Prepaid'
            WHEN 1 THEN 'Net 15'
            WHEN 2 THEN 'Net 30'
            ELSE 'Net 45'
        END AS payment_terms,
        (30000 + ((g * 997) % 500000))::NUMERIC(14,2) AS credit_limit,
        ep.emp_id
    FROM generate_series(1, v_customer_add) AS g
    JOIN meta m ON TRUE
    LEFT JOIN emp_pool ep ON m.emp_total > 0 AND ep.rn = ((g * 11) % m.emp_total);

    INSERT INTO public.suppliers (
        supp_id, supp_no, supp_name, contact_person, phone, email,
        address, tax_id, bank_info, qualification, rating
    )
    SELECT
        v_supplier_start + g AS supp_id,
        'SUPP' || LPAD((v_supplier_start + g)::TEXT, 7, '0') AS supp_no,
        'Supplier-' || LPAD((v_supplier_start + g)::TEXT, 7, '0') AS supp_name,
        'SupplierContact-' || (v_supplier_start + g) AS contact_person,
        '137' || LPAD(((v_supplier_start + g) % 100000000)::TEXT, 8, '0') AS phone,
        'supplier' || (v_supplier_start + g) || '@example.local' AS email,
        'Supplier address #' || (v_supplier_start + g) AS address,
        'TAXS' || LPAD((v_supplier_start + g)::TEXT, 10, '0') AS tax_id,
        'Bank-' || ((g % 9) + 1) || '-ACCT-' || LPAD((v_supplier_start + g)::TEXT, 9, '0') AS bank_info,
        CASE g % 4
            WHEN 0 THEN 'ISO9001'
            WHEN 1 THEN 'ISO14001'
            WHEN 2 THEN 'RoHS'
            ELSE 'REACH'
        END AS qualification,
        (3 + (g % 3) + ((g % 10)::NUMERIC / 10.0))::NUMERIC(3,1) AS rating
    FROM generate_series(1, v_supplier_add) AS g;

    INSERT INTO public.products (
        prod_id, prod_no, prod_name, category, specification, unit,
        purchase_price, selling_price, tax_rate, min_stock, status
    )
    SELECT
        v_product_start + g AS prod_id,
        'PROD' || LPAD((v_product_start + g)::TEXT, 8, '0') AS prod_no,
        'Product-' || LPAD((v_product_start + g)::TEXT, 8, '0') AS prod_name,
        CASE g % 6
            WHEN 0 THEN 'Electronics'
            WHEN 1 THEN 'Office'
            WHEN 2 THEN 'Software'
            WHEN 3 THEN 'Accessories'
            WHEN 4 THEN 'Services'
            ELSE 'Industrial'
        END AS category,
        'Spec-' || ((g % 25) + 1) AS specification,
        CASE g % 4
            WHEN 0 THEN 'pcs'
            WHEN 1 THEN 'box'
            WHEN 2 THEN 'set'
            ELSE 'license'
        END AS unit,
        (20 + ((g * 13) % 1800))::NUMERIC(14,2) AS purchase_price,
        (35 + ((g * 17) % 2600))::NUMERIC(14,2) AS selling_price,
        CASE g % 3
            WHEN 0 THEN 0.06
            WHEN 1 THEN 0.09
            ELSE 0.13
        END::NUMERIC(5,2) AS tax_rate,
        (10 + ((g * 7) % 160))::INT AS min_stock,
        CASE g % 8 WHEN 0 THEN 'Paused' ELSE 'OnSale' END AS status
    FROM generate_series(1, v_product_add) AS g;

    INSERT INTO public.inventory (inv_id, prod_id, warehouse, quantity, last_check_date)
    WITH new_products AS (
        SELECT prod_id, ROW_NUMBER() OVER (ORDER BY prod_id) AS rn
        FROM public.products
        WHERE prod_id > v_product_start AND prod_id <= v_product_start + v_product_add
    ),
    wh AS (
        SELECT * FROM (VALUES ('WH-NORTH', 1), ('WH-SOUTH', 2)) AS t(warehouse, wid)
    )
    SELECT
        v_inventory_start + ROW_NUMBER() OVER (ORDER BY np.prod_id, wh.wid) AS inv_id,
        np.prod_id,
        wh.warehouse,
        (80 + ((np.rn * 29 + wh.wid * 7) % 1200))::INT AS quantity,
        (CURRENT_DATE - (((np.rn + wh.wid) % 90)::INT))::DATE AS last_check_date
    FROM new_products np
    CROSS JOIN wh;

    INSERT INTO public.orders (
        order_id, order_no, order_date, cust_id, emp_id,
        total_amount, tax_amount, discount, payment_status, delivery_status, remarks
    )
    WITH customer_pool AS (
        SELECT cust_id, ROW_NUMBER() OVER (ORDER BY cust_id) - 1 AS rn FROM public.customers
    ),
    employee_pool AS (
        SELECT emp_id, ROW_NUMBER() OVER (ORDER BY emp_id) - 1 AS rn FROM public.employees
    ),
    meta AS (
        SELECT
            (SELECT COUNT(*) FROM customer_pool) AS customer_total,
            (SELECT COUNT(*) FROM employee_pool) AS employee_total
    )
    SELECT
        v_order_start + g AS order_id,
        'SO' || TO_CHAR(CURRENT_DATE, 'YYYYMM') || LPAD((v_order_start + g)::TEXT, 8, '0') AS order_no,
        (CURRENT_DATE - ((g * 3) % 365))::DATE AS order_date,
        cp.cust_id,
        ep.emp_id,
        (120 + ((g * 97) % 4800))::NUMERIC(14,2) AS total_amount,
        (16 + ((g * 13) % 620))::NUMERIC(14,2) AS tax_amount,
        ((g % 5) * 6)::NUMERIC(14,2) AS discount,
        CASE g % 4
            WHEN 0 THEN 'Paid'
            WHEN 1 THEN 'Pending'
            WHEN 2 THEN 'Unpaid'
            ELSE 'Partial'
        END AS payment_status,
        CASE g % 4
            WHEN 0 THEN 'Delivered'
            WHEN 1 THEN 'Pending'
            WHEN 2 THEN 'Partial'
            ELSE 'Shipped'
        END AS delivery_status,
        'Seeded sales order #' || (v_order_start + g) AS remarks
    FROM generate_series(1, v_order_add) AS g
    JOIN meta m ON TRUE
    JOIN customer_pool cp ON cp.rn = ((g * 17) % m.customer_total)
    LEFT JOIN employee_pool ep ON m.employee_total > 0 AND ep.rn = ((g * 19) % m.employee_total);

    INSERT INTO public.order_items (
        item_id, order_id, prod_id, quantity, unit_price, total_price, delivery_quantity
    )
    WITH product_pool AS (
        SELECT
            prod_id,
            COALESCE(selling_price, 0)::NUMERIC(14,2) AS unit_price,
            ROW_NUMBER() OVER (ORDER BY prod_id) - 1 AS rn
        FROM public.products
    ),
    meta AS (
        SELECT COUNT(*) AS product_total FROM product_pool
    ),
    new_orders AS (
        SELECT order_id
        FROM public.orders
        WHERE order_id > v_order_start AND order_id <= v_order_start + v_order_add
    ),
    order_lines AS (
        SELECT o.order_id, line_no
        FROM new_orders o
        CROSS JOIN LATERAL generate_series(1, 2 + (o.order_id % 4)) AS line_no
    )
    SELECT
        v_item_start + ROW_NUMBER() OVER (ORDER BY ol.order_id, ol.line_no) AS item_id,
        ol.order_id,
        pp.prod_id,
        qty.qty,
        pp.unit_price,
        ROUND((qty.qty::NUMERIC * pp.unit_price), 2) AS total_price,
        GREATEST(qty.qty - ((ol.order_id + ol.line_no) % 3), 0) AS delivery_quantity
    FROM order_lines ol
    JOIN meta m ON TRUE
    JOIN product_pool pp ON pp.rn = ((ol.order_id * 31 + ol.line_no * 7) % m.product_total)
    CROSS JOIN LATERAL (
        SELECT (1 + ((ol.order_id + ol.line_no * 3) % 12))::INT AS qty
    ) AS qty;

    UPDATE public.orders o
    SET
        total_amount = s.subtotal,
        tax_amount = ROUND((s.subtotal * 0.13), 2),
        discount = CASE
            WHEN (o.order_id % 5) = 0 THEN ROUND((s.subtotal * 0.03), 2)
            ELSE 0
        END
    FROM (
        SELECT order_id, ROUND(SUM(total_price)::NUMERIC, 2) AS subtotal
        FROM public.order_items
        WHERE order_id > v_order_start AND order_id <= v_order_start + v_order_add
        GROUP BY order_id
    ) s
    WHERE o.order_id = s.order_id;

    INSERT INTO public.purchases (
        purchase_id, purchase_no, purchase_date, supp_id, emp_id,
        total_amount, status, remarks
    )
    WITH supplier_pool AS (
        SELECT supp_id, ROW_NUMBER() OVER (ORDER BY supp_id) - 1 AS rn FROM public.suppliers
    ),
    employee_pool AS (
        SELECT emp_id, ROW_NUMBER() OVER (ORDER BY emp_id) - 1 AS rn FROM public.employees
    ),
    meta AS (
        SELECT
            (SELECT COUNT(*) FROM supplier_pool) AS supplier_total,
            (SELECT COUNT(*) FROM employee_pool) AS employee_total
    )
    SELECT
        v_purchase_start + g AS purchase_id,
        'PO' || TO_CHAR(CURRENT_DATE, 'YYYYMM') || LPAD((v_purchase_start + g)::TEXT, 8, '0') AS purchase_no,
        (CURRENT_DATE - ((g * 2) % 365))::DATE AS purchase_date,
        sp.supp_id,
        ep.emp_id,
        (300 + ((g * 149) % 19000))::NUMERIC(14,2) AS total_amount,
        CASE g % 4
            WHEN 0 THEN 'Received'
            WHEN 1 THEN 'Pending'
            WHEN 2 THEN 'Processing'
            ELSE 'Closed'
        END AS status,
        'Seeded purchase order #' || (v_purchase_start + g) AS remarks
    FROM generate_series(1, v_purchase_add) AS g
    JOIN meta m ON TRUE
    JOIN supplier_pool sp ON sp.rn = ((g * 13) % m.supplier_total)
    LEFT JOIN employee_pool ep ON m.employee_total > 0 AND ep.rn = ((g * 23) % m.employee_total);

    RAISE NOTICE 'Seed complete: departments +%, roles +%, employees +%, customers +%, suppliers +%, products +%, orders +%, order_items +(dynamic), purchases +%',
        v_dept_add, v_role_add, v_emp_add, v_customer_add, v_supplier_add, v_product_add, v_order_add, v_purchase_add;
END $$;

COMMIT;
