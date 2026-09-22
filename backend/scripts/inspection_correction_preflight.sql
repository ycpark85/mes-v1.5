-- Read-only. Compatible with the schema before and after 5a6b7c8d9e0f.
-- Review results; this script never adjusts quantities or releases reservations.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';

-- Product total versus physical LOT balances.
WITH lot_totals AS (
    SELECT product_id, SUM(current_qty) AS lot_qty
    FROM product_inventory_lot GROUP BY product_id
)
SELECT COALESCE(i.product_id, l.product_id) AS product_id,
       COALESCE(i.current_qty, 0) AS product_qty, COALESCE(l.lot_qty, 0) AS lot_qty,
       COALESCE(l.lot_qty, 0) - COALESCE(i.current_qty, 0) AS difference
FROM product_inventory i FULL JOIN lot_totals l USING (product_id)
WHERE COALESCE(i.current_qty, 0) <> COALESCE(l.lot_qty, 0)
ORDER BY product_id;

-- Reservations exceeding a LOT's physical balance, including unresolved LOT references.
SELECT s.product_id, s.product_inventory_lot_id, l.lot_no,
       COALESCE(l.current_qty, 0) AS physical_qty, SUM(s.ship_qty) AS reserved_qty,
       ARRAY_AGG(DISTINCT s.order_line_id) AS order_line_ids
FROM shipment_line s LEFT JOIN product_inventory_lot l USING (product_inventory_lot_id)
WHERE s.source_type = 'STOCK' AND s.status = 'WAITING'
GROUP BY s.product_id, s.product_inventory_lot_id, l.lot_no, l.current_qty
HAVING l.lot_no IS NULL OR SUM(s.ship_qty) > l.current_qty
ORDER BY s.product_id, s.product_inventory_lot_id;

-- Closed/canceled orders retaining waiting stock: review business evidence, never auto-confirm.
SELECT s.shipment_line_id, s.order_line_id, o.status AS order_status,
       s.stock_lot_no, s.ship_qty, s.created_at
FROM shipment_line s JOIN order_line o USING (order_line_id)
WHERE s.source_type = 'STOCK' AND s.status = 'WAITING' AND o.status IN ('DONE', 'CANCELED')
ORDER BY s.order_line_id, s.shipment_line_id;

-- Historical manual movements without LOT attribution.
SELECT inventory_movement_id, product_id, movement_type, qty, created_at
FROM product_inventory_movement
WHERE movement_type IN ('ADJUST_IN', 'ADJUST_OUT') AND product_inventory_lot_id IS NULL
ORDER BY product_id, created_at;

-- Result shipment lines and signed ledger must agree; reversals remain in the ledger.
WITH posted AS (
    SELECT inspection_result_id, SUM(-qty) AS qty FROM product_inventory_movement
    WHERE movement_type = 'SHIP_OUT' AND inspection_result_id IS NOT NULL GROUP BY inspection_result_id
), shipped AS (
    SELECT inspection_result_id, SUM(shipped_qty) AS qty FROM shipment_line
    WHERE status = 'DONE' AND inspection_result_id IS NOT NULL GROUP BY inspection_result_id
)
SELECT COALESCE(p.inspection_result_id, s.inspection_result_id) AS inspection_result_id,
       COALESCE(p.qty, 0) AS ledger_qty, COALESCE(s.qty, 0) AS shipped_qty
FROM posted p FULL JOIN shipped s USING (inspection_result_id)
WHERE COALESCE(p.qty, 0) <> COALESCE(s.qty, 0);
ROLLBACK;
