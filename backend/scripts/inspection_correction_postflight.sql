-- Read-only, run after 5a6b7c8d9e0f. Unresolved rows require evidence-based review.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT r.inspection_result_id, r.inspection_schedule_id, s.lot_id,
       r.good_qty, r.defect_ship_qty, r.settled_at
FROM inspection_result r JOIN inspection_schedule s USING (inspection_schedule_id)
WHERE r.settled_at IS NOT NULL AND r.settlement_owner_id IS NULL
ORDER BY s.lot_id, s.inspection_date, r.inspection_result_id;

SELECT source.inspection_result_id AS source_id, source.settlement_owner_id AS owner_id,
       source.settled_sellable_qty
FROM inspection_result source
JOIN inspection_result owner ON owner.inspection_result_id = source.settlement_owner_id
JOIN inspection_schedule ss ON ss.inspection_schedule_id = source.inspection_schedule_id
JOIN inspection_schedule os ON os.inspection_schedule_id = owner.inspection_schedule_id
WHERE ss.lot_id <> os.lot_id
   OR source.settled_sellable_qty <> source.good_qty + source.defect_ship_qty
   OR (source.inspection_result_id <> owner.inspection_result_id
       AND (ss.inspection_date, ss.inspection_schedule_id) >= (os.inspection_date, os.inspection_schedule_id));

SELECT r.inspection_result_id, r.shortage_reason, r.updated_at
FROM inspection_result r WHERE r.shortage_reason IS NOT NULL ORDER BY r.updated_at DESC;
ROLLBACK;
