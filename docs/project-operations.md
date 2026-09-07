# Project Operations

## MES v1.5 Baseline

- MES v1.5 uses Git commit `4da47c94d361ec3e2b9eb3785fdacd5f53122f80` as its functional baseline.
- The immutable baseline tag is `v1.5-baseline-4da47c9`.
- Local development uses the independent `mes-v1.5` repository, its own `backend/.venv` and `backend/.env`, and the external `mes-v1.5-data` storage root.
- The shared development database is currently aligned to Alembic head `29d3e4f5a6b7`; schema changes require a verified backup before migration.
- Production backend deployment remains a reviewed fast-forward pull of `main`; internal and vendor WPF clients are built on the development computer and copied as separate release artifacts.
- The detailed development, deployment, rollback, and project-separation procedure is in `docs/mes-v1.5-development-deployment.md`.

## Alembic Schema Verification

- SQLAlchemy model and Alembic migration changes are complete only when `alembic check` reports no pending upgrade operations against the target database.
- Partial unique indexes that enforce business rules must be declared in model metadata as well as migrations; otherwise autogenerate may propose deleting them.
- Migration `29d3e4f5a6b7` aligns plan-history lookup and active outsource-instruction uniqueness indexes.
- Apply index replacement migrations in the V2 deployment maintenance window because normal PostgreSQL index creation briefly locks writes on the affected table.

## Split Inspection Settlement

- Every inspection round settles its sellable quantity immediately, including a split inspection round.
- The operator allocates the round's sellable quantity to production shipment, inventory stock-in, and disposal; their sum must equal the current sellable quantity plus any explicitly shown legacy unsettled carry-in.
- Existing-stock shipment is independent from the inspected production quantity and may be combined with production shipment without exceeding the order's remaining shipment target.
- Inspection result detail separates LOT inspection totals from order shipment progress. Shipment progress is displayed as target quantity, shipment completed before the selected result, selected-round shipment, cumulative shipment, and remaining shipment.
- Shipment movements are the source of truth. The selected result's shipment is excluded from the prior-shipment baseline and added exactly once, so `remaining shipment = target - prior shipment - selected-round shipment`.
- The LOT section is labeled `LOT 누적 처리현황`. `누적 검사완료 수량` is the inspected total, `누적 미검수 처리수량` is the quantity explicitly processed without inspection, and `누적 처리수량 (미검수 포함)` is their sum. Pending inspection quantities are excluded. The same total is labeled `이번 처리수량` for the selected round and `처리수량` in round history; the API field remains `received_qty`.
- A split round changes the completed schedule to `PARTIAL_DONE`, creates the next schedule as `RECEIVED`, and keeps unused stock reservations available for the later round.
- Completing the customer shipment target does not complete the LOT while inspection work remains. The order line becomes `DONE` only after all active LOTs are done and recorded shipment movements meet the partner-specific shipment target.
- `inspection_result.settled_at` and `settled_by` identify rounds whose shipment, stock-in, and disposal settlement has been applied.
- Migration `4f5a6b7c8d9e` marks historical completed results and zero-sellable results as settled. Positive historical split results remain explicit carry-in and are marked settled in the same transaction as the next saved settlement.
- A split round cannot contain uninspected quantity. The final round must make cumulative inspected plus uninspected quantity exactly equal the LOT quantity.

## Authentication Session Revocation

- Account deactivation is checked on every authenticated request and immediately blocks the account.
- Access tokens also contain the user's `auth_version`; a mismatch with `users.auth_version` returns HTTP 401.
- Administrator password reset, actual user-role changes, vendor-account access changes, and account activation changes revoke all existing tokens for that user.
- Role activation and role-permission changes revoke existing tokens only for users assigned to that role.
- Profile-only edits and saving an unchanged role/vendor configuration do not revoke sessions.
- A user's own password change revokes all old sessions, returns a new access token, and the MES WPF client replaces its current token before continuing.
- Applying the `18c2d3e4f5a6` migration makes tokens issued by older server versions invalid. Plan for a one-time login prompt after deployment.

## WPF ClickOnce Deployment

The WPF client is published with `ClickOnceProfile`.

- The current staging folder is `C:\mes_publish_test\wpf\`.
- `PublishUrl` is the ClickOnce staging folder: `C:\mes_publish_test\wpf\`.
- `PublishDir` must remain the project-local ClickOnce intermediate folder: `bin\Release\net8.0-windows\win-x64\app.publish\`.
- Do not set `PublishDir` to the same folder as `PublishUrl`; doing so can mix raw publish files into the ClickOnce root.
- The ClickOnce root should contain only `Application Files`, `Mes.Wpf.application`, `setup.exe`, and other ClickOnce bootstrap files.
- `InstallUrl` and `UpdateUrl` point to `\\172.30.1.240\mes_wpf\`.
- If a publish prompt asks to overwrite an older deployment version, check for stale ClickOnce manifests under `bin\Release\net8.0-windows\win-x64\app.publish` and clean the build output before publishing again.
- The ClickOnce deployment version is controlled by `ApplicationVersion` and `ApplicationRevision` in the publish profile.

## Vendor Portal External Access

External vendor access is handled by a separate vendor WPF app and a dedicated vendor portal API. The internal MES WPF client remains for internal users only.

- The vendor endpoint is planned as `https://vendor-mes.semiindustry.com`.
- The vendor WPF project is `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Vendor.Wpf`.
- The vendor WPF app uses the public HTTPS host as its API base URL and calls only login plus vendor-portal routes.
- The selected external access method is Cloudflare Free plan plus Cloudflare Tunnel because the company internet line does not have a fixed public IP.
- Domain purchase/renewal remains at Gabia, but authoritative DNS should move to Cloudflare by changing Gabia nameservers to Cloudflare nameservers.
- Do not configure Gabia DNS host records or DNSSEC for this rollout.
- The firewall should not expose inbound vendor-portal ports; `cloudflared` should create outbound tunnel connections to Cloudflare.
- Cloudflare Tunnel should publish only `vendor-mes.semiindustry.com` to the internal FastAPI service or a local reverse proxy.
- If a local reverse proxy is used for path allowlisting, allow `POST /api/v1/auth/login`, `GET /api/v1/health` for monitoring, and `/api/v1/vendor-portal/*`.
- Internal API paths, database ports, RDP, development ports, `/docs`, and `/openapi.json` must remain unavailable from the internet.
- Vendor portal API endpoints must enforce vendor account and partner-scope checks server-side.
- Existing Bohyun outsource status rules should be shared through a backend service so internal WPF and vendor WPF produce identical state transitions.
- Login and vendor-action audit logs use the same request metadata policy: User-Agent is sanitized, capped at 2,000 characters, and marked with `user_agent_truncated` when shortened.
- Audit logging remains in the same transaction as the protected action so a vendor status change cannot commit without its audit record.

Vendor account maintenance:

- Operational vendor accounts must be created and maintained from the internal MES WPF 회원관리 menu.
- In 회원관리, check `외주업체 계정` and select the linked active VENDOR partner, such as 보현문화.
- Saving a vendor account updates `users`, `user_roles`, and `vendor_user_access` in one backend transaction.
- The `VENDOR_PORTAL` role is created by auth seed data and is automatically included when the user is saved as a vendor account.
- `VENDOR_PORTAL` must not be granted internal MES menu permissions.
- To revoke vendor access, uncheck `외주업체 계정` or deactivate the user account. This deactivates the vendor access grant without exposing internal menus.
- `backend/scripts/create_vendor_portal_user.py` is for development, testing, or emergency recovery only; it is not the normal operating process.

Detailed plan: `docs/vendor-portal-external-access-plan.md`.

## Raw Material Inventory Management (Inactive in MES v1.5)

- The raw-material master and inventory menus, WPF pages, API routes, schemas, and application services are not part of the MES v1.5 runtime scope.
- Raw-material permission codes are no longer seeded, and `/api/v1/raw-materials/*` routes are not registered.
- Outsource work instruction create, update, and cancel flows do not accept allocations and do not create raw-material inventory movements.
- Existing raw-material and allocation tables, SQLAlchemy models, and Alembic history remain in place. This avoids a destructive migration and preserves compatibility evidence for later review.
- At removal time, raw-material masters, inventory rows, inventory LOTs, outsource allocations, and related allocation movements were all confirmed as zero rows.
- Purchase-order fields named `raw_material_text` or `raw_material_inbound_text` describe the existing cutting-order form's material specification text; they are not raw-material inventory allocation features.

Outsource work instruction list, update, and cancel rules:

- Outsource work instruction list is managed by `outsource_work_group`, because work grouping, Bohyun outsource management, and later cost flows are group-based.
- Registered work groups can be updated only before vendor receipt and before a purchase order group is created.
- The update scope allows `sheet_qty`, `length_m`, `sheet_cut_count`, `fabric_lot_no`, and `remark` changes. Work LOT composition, process type, and partner changes remain cancel-and-recreate flows.
- Update reason is required. Each update writes before/after snapshots to `outsource_work_group_change_log`.
- A registered work group has `status IS NULL` and is displayed as `REGISTERED` or "지시등록".
- Canceling a work group sets `outsource_work_group.status` to `CANCELED` and records `canceled_at` and `canceled_reason`.
- Canceling does not delete the work instruction or work group history.
- The related active `outsource_work_instruction_item` rows are deactivated so the same LOT and process can be registered again.
- Candidate LOT lookup excludes only active, non-canceled work groups. Therefore canceled work instructions allow their LOTs to appear again in the outsource-work-instruction candidate list.
- Bohyun outsource management and purchase-order target lists exclude canceled work groups.
- Cancel is blocked once the work group or connected purchase-order group is at vendor-received, work-done, or shipped status.

Outsource purchase order connection rules:

- Purchase-order targets are grouped by `outsource_work_group`, not only by instruction number, because one instruction can contain multiple work groups.
- Printed-product routing keeps the primary outsource work instruction as `PRINT`, but purchase-order targets expose both `CUT` and `PRINT` because the operational flow is cutting, printing, then Bohyun die-cut management.
- Creating an outsource purchase order writes both LOT-level `outsource_purchase_order_item` rows and work-group-level `outsource_purchase_order_group` rows.
- All LOTs in the same outsource work group must be purchase ordered together.
- A work group already connected to `outsource_purchase_order_group` for the same purchase-order process is excluded from that process target list; any purchase-order group link blocks registered-work-instruction updates.

Current WPF outsource purchase order API usage:

- `OutsourcePurchaseOrderPage` uses purchase-order target lookup, purchase-order create, and purchase-order Excel download.
- `OutsourcePurchaseOrderListPage` uses purchase-order list lookup and purchase-order Excel download.
- The single purchase-order detail API, `GET /api/v1/outsource-work-instructions/purchase-orders/{id}`, is not currently called by the WPF client.
- Do not remove or repurpose the detail API without a separate compatibility decision. It should remain a candidate for either screen connection or later deprecation documentation.

Current WPF outsource API cleanup notes:

- The active WPF outsource work-instruction registration screen uses `POST /api/v1/outsource-work-instructions/batch`.
- The former single work-instruction create API, `POST /api/v1/outsource-work-instructions`, was removed because the WPF client uses the batch endpoint and the batch flow supersedes the old process-type-specific create flow.
- The active WPF outsource work-group list uses group list, group detail, group update, group cancel, and work-group plate-data download APIs.
- MES WPF file downloads stream to a temporary sibling file and replace the destination only after a complete transfer; they must not buffer the full file in a `byte[]`.
- File and generated-Excel endpoints close their DB session after lookup/generation and before returning `FileResponse` or `StreamingResponse`.
- Plate-data uploads are copied in 1 MB chunks, enforce `PLATE_DATA_MAX_MB` while copying, and remove partial files on failure.
- The active WPF Bohyun outsource-management screens use Bohyun group list, inbound, work-done, and ship-batch APIs.
- The unused purchase-order item status APIs, `vendor-receive`, `work-done`, and `ship`, were removed after confirming that no frontend, vendor app, script, external client, or direct operational workflow calls them.
- Their item-level transition service functions, request schema, tests, and WPF route constants were removed together.
- The purchase-order detail API remains available because it may be connected to a screen later.

Legacy outsource status audit:

- Run `python scripts/audit_outsource_legacy_status.py --sample-limit 20` from the `backend` directory before removing the remaining legacy item-status data fallback.
- The script is read-only and rolls back the session after collecting counts and samples.
- Review `progressed_purchase_order_item_count`, `legacy_schedule_fallback_count`, and status mismatch counts before deciding whether legacy item-level status behavior can be removed.
- A mismatch where `outsource_purchase_order_item.status` is `NULL` and `outsource_work_group.status` is progressed can be valid for the current work-group flow, but any read model that still combines both status sources must be reviewed carefully.
- If mismatch counts are non-zero, prioritize unifying read logic around `outsource_work_group.status` before removing deprecated item-level status APIs.

Production daily progress status:

- Production progress prioritizes completed inspection results first, then active inspection schedules, then outsource work status.
- Inspection schedule `RECEIVED` is displayed as inspection waiting, and `IN_PROGRESS` or `PARTIAL_DONE` is displayed as inspection in progress.
- For current outsource flows, `outsource_work_group.status` is the authoritative work status source.
- `outsource_purchase_order_item.status` remains only as a legacy fallback when a LOT has no matching outsource work group.
- This prevents a current work group status such as `SHIPPED` from being downgraded by a legacy purchase-order item row whose status is still `NULL`.

Outsource management refactor closure:

- Current WPF outsource work instruction, work group, Bohyun status, purchase-order, inspection handoff, production-progress, and processing-cost flows were refactored around service/query modules.
- Canceled outsource work groups are excluded from new outsource and inspection targets, while the original operational history remains available.
- Unused purchase-order item status APIs and their dedicated service code were removed after external usage was ruled out.
- Purchase-order detail API remains available because it may be connected or reviewed later.
- Processing-cost Excel download is intentionally left as a future feature because the current WPF button is disabled and no API is connected.
- Order-line management was refactored around service modules after outsource management. Current order-line routing delegates registration, bulk import, planning, base LOT creation, update, cancel, short-close, and detail queries to service/query modules.
- Inspection-result list/detail queries and attachment file handling were subsequently moved to dedicated query/service modules, so inspection-result routing now remains at the request and transaction boundary.

Out of current scope:

- Work-in-process ledger.
- Monthly or quarterly closing.
- Manufacturing overhead allocation.

Cost/closing preparation:

- Raw-material cost and movement tables remain preserved schema only and are not populated by active MES v1.5 workflows.

## Outsource Work Group Representative Product

Bundle outsource work groups have one representative LOT.

- Single-LOT work groups use the only LOT as the representative automatically.
- Bundle work groups require the user to select one LOT and click the representative product button before saving.
- The representative product is used as the display product name in Bohyun outsource management, outsource shipment lists, purchase order forms, and outsource processing cost targets.
- Cost allocation remains LOT-level. The representative product affects display and vendor-facing identification, not allocation math.

## Bohyun Outsource Management

Bohyun outsource management is an operational inbound, work-done, and shipment menu, not a cost-process menu.

- All outsource work instruction groups for coated Tyvek products flow into Bohyun outsource management, whether the product is blank or printed.
- Bohyun management uses the existing outsource work group as the operational unit.
- A separate `DIECUT` outsource work group is not required for Bohyun operations.
- Process filters in Bohyun management are limited to the operational outsource instruction processes (`CUT`, `PRINT`).

## Inspection Result Quantity Rules

Inspection result quantities separate internal receiving control from quality judgment.

- `good_qty`: good quantity confirmed by inspection.
- `defect_ship_qty`: defective quantity allowed to ship as-is.
- `defect_qty`: defective quantity not allowed to ship.
- `uninspected_qty`: quantity not inspected after the shipment requirement is met. It is tracked separately for uninspected disposal statistics.
- `discard_qty`: sellable quantity disposal used by shipment/inventory settlement. It is not the same as `uninspected_qty`.
- Total disposal quantity for operational review is `discard_qty + uninspected_qty`.

Quality statistics use only inspected quantities:

- `inspected_qty = good_qty + defect_ship_qty + defect_qty`
- good rate and defect rate use `inspected_qty` as the denominator.
- `uninspected_qty` is excluded from good/defect quality statistics.
- Disposal statistics can include `uninspected_qty`, but quality statistics must not.

Internal official received quantity is calculated from inspection results:

- `received_qty = good_qty + defect_ship_qty + defect_qty + uninspected_qty`
- outsource process loss should compare calculated output quantity against this internal `received_qty`, not against vendor-reported work-done quantity.
- vendor work-done quantity remains an operational reference value.

Inspection result management refactor notes:

- Inspection-result list and detail read logic is separated into `inspection_result_query.py`.
- The inspection-result list includes both `PARTIAL_DONE` and `DONE` result rows and is paged with `page` and `size`. Its response summary fields are totals for the full filtered result, not only the current page.
- Each list/detail result exposes its LOT inspection round, total round count, split/final classification, next inspection date, and partial reason. The detail response also contains the chronological round summary for the LOT.
- A split result requires both the next inspection date and a non-blank partial reason in the backend service; final-result saves clear split-only fields.
- `inspection_result_query.py` owns the result list query, prior partial/done accumulated summary, round history, and inventory/shipment summary shown in the inspection-result dialog.
- Defect photo upload/download file validation and storage-path resolution are separated into `inspection_result_attachment_service.py`.
- The inspection-result router delegates list/detail read models to the query service and file handling to the attachment service.
- Inspection-result save and settlement rules remain in `inspection_result_service.py`; this refactor step did not change inventory settlement, shipment waiting, defect-line saving, or attachment persistence behavior.
- Inspection-result management opens completed results in a read-only detail window. Users with `INSPECTIONS.WRITE` can open a separate edit window; a successful save closes the edit window and reloads the detail and management list.
- Result detail responses preserve result memo, defect quantity, defect disposition, and attachment identifiers. Stored defect images can be opened from both read-only and edit windows.
- Completed-result updates send the previously loaded `updated_at` value. The backend rejects stale writes with HTTP 409 so one user cannot silently overwrite another user's change.
- Inspection result management refactoring is considered closed when the router remains limited to request parsing, service delegation, transaction commit/rollback, and `FileResponse` construction.
- Current WPF usage covers inspection-result list lookup, result detail lookup, photo upload, result save, stock-lot lookup, and LOT-detail attachment image opening.
- Keep the attachment content API because LOT detail history can use stored inspection-defect attachment ids to open defect images.
- Manual WPF confirmation should focus on inspection-result management list filters, inspection-result detail opening, accumulated quantity display, stock shipment quantity display, result shipment quantity display, stock-in quantity display, and photo attachment preview/download.

## Inventory Availability and Order Planning

Order planning separates physical inventory from available inventory.

- Physical inventory is `product_inventory.current_qty`.
- Reserved inventory is stock shipment quantity in `shipment_line` where `source_type = STOCK` and `status = WAITING`.
- Available inventory is physical inventory minus reserved inventory.
- Automatic order planning must use available inventory, not physical inventory.

Stock usage rules:

- No available inventory: registration keeps the existing automatic-production behavior and creates the primary LOT immediately.
- Any positive available inventory leaves a normal order line in decision-waiting state. Registration must not create a stock shipment line or mark the order line `DONE` before a user confirms the plan.
- Enough inventory: the user chooses either stock shipment completion or full-order stock replenishment production.
- Partial inventory: the user chooses partial stock plus shortage production, partial-stock-only close, or full-order stock replenishment production.
- Stock-only shipment and close: when the processing plan is confirmed, stock shipment lines are created and immediately confirmed. Inventory is deducted and the order line becomes `DONE` in the same transaction because no production LOT or inspection result follows.
- Partial stock plus production: when the processing plan is confirmed, stock shipment lines remain in `WAITING` status as reserved inventory. The reserved quantity is excluded from availability for later orders.
- Full-order stock replenishment production does not reserve or deduct existing inventory. It creates one primary LOT using the original `order_qty`, not the calculated shipment target quantity.
- When inspection result is saved for partial stock plus production, the reserved stock shipment lines are consumed first and changed to `DONE`; only any remaining requested stock shipment quantity is allocated from FIFO available inventory.
- Unused stock reservations for the order line are canceled when final inspection settlement no longer uses them.

Order-line management refactor notes:

- Order-line registration policy, automatic primary LOT creation, and automatic stock-shipment waiting creation are handled by `order_line_creation_service`.
- Order-line bulk validation and bulk commit rules are handled by `bulk/order_line_bulk_service`.
- Order-line cancellation rules are handled by `order_line_cancel_service`.
- Order-line delete rules are handled by `order_line_delete_service`.
- Order-line update rules are handled by `order_line_update_service`.
- Allowed order-plan choices are calculated by `order_line_plan_policy` and are returned by the server. WPF must render only those server-provided choices.
- Order-line plan confirmation and its inventory/reservation changes are handled by `order_line_plan_service`.
- Order-line list lookup is handled directly by `order_line_list_query`.
- OrderLine response assembly for partner/product display fields and optional plan summary is handled by `order_line_response_builder`.
- Order-line detail DTO assembly is handled by `order_line_detail_query` so detail lookup, detail update responses, and cancel responses share the same display flag and timeline rules.
- Order-line detail edit rules are handled by `order_line_detail_update_service`.
- Order-line short-close rules and remaining shipment quantity calculation are handled by `order_line_short_close_service`.
- Base LOT creation from an order-line plan is handled by `order_line_base_lot_service`.
- LOT creation context DTO assembly is handled by `order_line_lot_context_query`.
- `OPEN` order lines may update the normal order fields. `CLOSED` order lines may update only `due_date`, `memo`, and `customer_po`.
- `DONE` and `CANCELED` order lines may update only `memo` and `customer_po`.
- The removed generic fulfillment-plan PATCH flow must not be reintroduced. A user decision uses the explicit plan-confirm endpoint so validation, history, inventory changes, and status changes stay in one transaction.
- Bulk commit re-runs validation, applies approved ERP product-name/spec changes per row choice, creates all order lines in the same ERP order-number group together, and returns per-group success or error results.
- Write endpoints roll back the DB session on handled HTTP/business errors and integrity errors before returning the API error.
- Delete integrity-error messages use a safe order number/ID label so the original database error is not masked by response-message construction.
- When an order-line due date changes, only LOTs whose steps have not started are synchronized to the new due date.
- Order-line cancellation is allowed only when the order is not `DONE` or already `CANCELED`, and all connected LOTs are already `CANCELED` if LOTs exist.
- Order-line delete deletes all lines with the same `order_no` together after checking blockers across LOT, inspection schedule/result, shipment, inventory movement, COA, inspection certificate, and outsource connection data.
- Order-line delete is blocked when operational data exists, including progressed LOTs, progressed inspection schedules, confirmed shipment, inventory movement, COA, inspection certificate, or outsource connection data.
- Base LOT creation requires an active `OPEN` order line, no existing primary LOT, a saved processing-plan decision, an active product, and a positive planned production quantity.
- LOT creation context includes partner/product/order data, drawing current revision file references, and primary LOT candidates for rework creation.
- Detail edit may change due date, order quantity, and memo only when the order line is not `DONE` or `CANCELED`; due-date changes still synchronize only not-yet-started LOTs.
- Both the general order-line update API and the detail update API use the same quantity-change policy and append-only due-date/memo audit writer, so an alternate update route cannot bypass LOT synchronization or timeline history.
- An order-quantity change before LOT creation invalidates the saved processing-plan decision, cancels waiting stock reservations, returns a reservation-closed order line to `OPEN`, and records an order-line quantity-change audit row without a LOT id.
- After LOT creation, the existing order-detail edit screen may change quantity only when exactly one active primary LOT remains, every LOT step is still `WAITING`, no active outsource work group or inspection exists, and no shipment or inventory movement has started. The quantity-change service recalculates the production quantity, updates the LOT quantity, and appends both the fulfillment-plan snapshot and the linked order-line audit row in the same transaction.
- For `PARTIAL_STOCK_PLUS_PRODUCTION`, `STOCK/WAITING` shipment lines with zero shipped quantity are reversible reservations rather than completed inventory movements. A quantity edit keeps the validated reservation total, recalculates the ship target and shortage-production quantity, updates the waiting primary LOT, and appends the new plan/audit snapshots in one transaction. The edit remains blocked when any inventory movement or started shipment exists, when the reservation no longer matches the latest plan, or when the new ship target is not greater than the reserved stock and the production LOT would become unnecessary.
- `order_line_change_log` stores before/after values for quantity, due-date, and memo edits together with the authenticated login id. Order detail exposes these as explicit change events, and a quantity row linked to a LOT is also exposed as `LOT_QUANTITY_CHANGED` in that LOT's timeline.
- Legacy quantity-correction memos without a LOT id remain readable. They are linked only when the order line has exactly one primary LOT, preventing an ambiguous history from being shown on the wrong LOT.
- Quantity changes are blocked after outsource work, inspection, shipment, inventory movement, rework, or multi-LOT execution has started. Those cases require an additional LOT or an operational reduction/short-close flow instead of rewriting the released LOT quantity.
- Short-close is allowed only for `CLOSED` order lines with positive remaining shipment quantity. It changes the order line to `DONE` and appends `[SHORT_CLOSE] remaining_ship_qty=...` to memo.
- Detail timeline sorting normalizes naive and timezone-aware datetimes before sorting.
- Service tests cover no-inventory automatic LOT creation, enough-inventory decision waiting, stock shipment completion with inventory deduction, full-order stock replenishment LOT quantity, partial-inventory decision waiting, closed-order due-date synchronization, closed-order quantity-change rejection, detail action flags, LOT current-process display, plan-history timeline inclusion, canceled-order detail flags, order-line cancellation rules, same-order-number delete cascading, progressed-LOT delete blocking, plan-based base LOT creation, missing-decision base LOT blocking, LOT creation context drawing/candidate fields, detail edit due-date synchronization, detail edit blocked status, bulk commit success, bulk product-name conflict blocking, response display field assembly, response lookup blocking, short-close success, and short-close no-remaining-quantity blocking.

Order-line management refactor closure:

- The order-line router is considered closed when it stays limited to request parsing, service calls, transaction handling, and response return.
- The removed `order_line_crud.list_with_search` wrapper must not be reintroduced; list lookup should use `order_line_list_query` directly.
- Final verification should include backend compile, order-line service tests, full backend tests, and WPF solution build.
- Recommended manual confirmation screens are order-line list, detail lookup, normal edit, detail edit, fulfillment-plan save/confirm, base LOT creation, short-close, cancel, delete, bulk validate, and bulk commit.
- Remaining known warnings are Pydantic class-based `Config` deprecation warnings; WPF solution build currently passes without warnings in the final verification.

## Production Progress Status

The Production Management menu includes `생산진행현황` (`Production Progress Status`).

This menu is an operational progress view, not a completed-history report.

- The screen reads from `production_progress_snapshot`, a production progress read model.
- Source tables remain the system of record. The snapshot is regenerated from source data when needed.
- Run `python scripts/rebuild_production_progress_snapshots.py` from the backend directory after introducing the table to existing data, after bulk data repair, or when snapshot drift is suspected.
- When an order line due date is changed from the order list or order detail screen, the order due date, not-yet-started LOT due dates, and `production_progress_snapshot.due_date` are updated in the same transaction.
- Inspection schedule dates, inspection results, shipment results, and inventory movements are not automatically changed by an order due-date change.
- Default status filter is `IN_PROGRESS`.
- `IN_PROGRESS` means inspection result registration is not completed.
- `COMPLETED` means inspection result registration is completed.
- Shipment and delivery status are outside this menu's completion rule.
- Default sort order is due-date urgency:
  - overdue due dates first
  - D-DAY
  - D-1, D-2, D-3
  - later due dates in ascending due-date order

Top filters:

- partner
- product
- status (`IN_PROGRESS`, `COMPLETED`)

Grid columns:

- due date
- due slack
- partner
- product
- order quantity
- available inventory
- production quantity
- work type
- current process
- progress rate

Due slack display:

- `D-4` or more: relaxed, green text.
- `D-3` through `D-1`: imminent, orange text.
- `D-DAY` and overdue (`D+N`): urgent, red text.

Current process has seven display states:

- `LOT_CREATED`: LOT created.
- `OUTSOURCE_ORDERED`: outsource work instruction is registered.
- `DIECUT_RECEIVED`: Bohyun/vendor inbound is completed.
- `OUTSOURCE_DONE`: Bohyun/vendor work is completed.
- `INSPECTION_WAITING`: company inbound is completed and inspection is waiting.
- `INSPECTION_IN_PROGRESS`: inspection is in progress.
- `COMPLETED`: inspection result registration is completed.

Work type display:

- `BASIC`: 기본작업
- `REWORK`: 재작업

Rework LOTs can be created only after the original LOT work is completed. Therefore, original LOTs and rework LOTs are not expected to progress at the same time. If a rework LOT exists and is still active, production progress status displays the rework LOT's current process. If rework was completed, completed rows display `REWORK` so users can identify that the order was completed through rework.

For order lines with multiple LOTs in the same work type, the current process is the earliest unfinished bottleneck process among those LOTs.

## Product History Monitoring

Product history monitoring is a product-to-LOT trace view.

- The product search can filter by product keyword and partner keyword.
- Partner keyword filtering uses historical order lines. It returns products that have active order line history for matching partner names or business numbers.
- After selecting a product, the user loads the latest LOT history for that product.
- LOT detail and product history screens use the common `GET /api/v1/lots/{lot_id}/detail` trace API.
- Order detail and LOT detail timelines expose append-only outsource work-group `UPDATE` and `CANCEL` logs with before/after values, the required reason, and the authenticated login id. Legacy canceled groups without a `CANCEL` log use their stored cancellation timestamp and reason as a read fallback. A bundled work group is shown against each linked LOT so the affected LOT remains explicit.
- LOT management list and basic LOT detail lookup are assembled by `lot_query.py`; the router only receives filters and delegates the query.
- LOT management list status treats a LOT as `IN_PROGRESS` when it belongs to an active, non-canceled outsource work group, even if the stored `lot.status` is still `WAITING`.
- Canceling an outsource work group atomically deletes its linked unstarted inspection schedules (`WAITING`, `RECEIVED`, or legacy `CANCELED`) instead of retaining canceled schedule rows. This keeps the existing `(lot_id, inspection_date)` uniqueness rule available for a replacement outsource instruction on the same date. The cancellation audit remains in the append-only outsource work-group change log and LOT timeline. Deletion is blocked if a linked inspection has progressed or if an inspection result or product inventory movement references the schedule. When no other active outsource work or inspection remains, a `WAITING` or `RECEIVED` LOT returns to stored status `WAITING` and is displayed as `CREATED` so it can be instructed again.
- Existing legacy rows are audited and removed with `scripts/cleanup_legacy_canceled_inspection_schedules.py`. It defaults to read-only dry-run and selects only `CANCELED` schedules linked to `CANCELED` outsource work groups. Apply mode requires the exact dry-run count, `APP_ENV`, database name, and backup root; it locks and revalidates targets, blocks referenced schedules, writes a complete JSON recovery snapshot before commit, deletes the rows in one transaction, and resequences affected inspection dates.
- After deployment on Windows, double-click `deploy/windows/Run-LegacyCanceledInspectionCleanup.cmd` in the production source checkout, or invoke `Invoke-LegacyCanceledInspectionCleanup.ps1` directly. The wrapper discovers the deployed backend script, prints the dry-run target rows, stops on any reference blocker, requires the operator to re-enter the exact safe count, creates the recovery snapshot under `C:\mes\deploy-backups\inspection-cleanup`, applies the cleanup, and verifies that no legacy candidates remain. Use the PowerShell wrapper with `-DryRunOnly` when inspection without deletion is required.
- Stored LOT status is limited to `WAITING`, `RECEIVED`, `IN_PROGRESS`, `PARTIAL_DONE`, `DONE`, and `CANCELED`; `CREATED` and `INSPECTION_DONE` are list display states only.
- Historical `PARTIAL_DONE` inspection schedules do not block LOT completion; when the follow-up inspection is `DONE`, the stored LOT status becomes `DONE`.
- Inspection schedule and inspection result flows share the same LOT status synchronization service. The split-to-final sequence is covered by an integration test that verifies `PARTIAL_DONE + DONE` completes both the LOT and, when all non-canceled LOTs are done, the order line.
- The legacy `POST /api/v1/lot-steps/{id}/start` and `POST /api/v1/lot-steps/{id}/complete` manual process-control APIs were removed after confirming they are not used externally.
- Current outsource process control must use outsource work instruction groups, Bohyun inbound/work-done/shipment status, inspection schedule receive/start, and inspection result registration instead of manual LOT-step start/complete.
- Keep `lot_step` rows as routing/process snapshots for LOT creation, detail display, and not-started checks, but do not use the legacy LOT-step APIs as the operational progress source.
- `lot_step` rows remain part of the routing snapshot and history model even though the manual transition API no longer exists.

- LOT trace detail assembly is handled by `lot_trace_query.py`, including LOT basics, latest order planning snapshot, current product stock, outsource work history, inspection totals, defects, and defect attachment image URLs.
- LOT trace detail also exposes chronological `timeline` events and `inspection_rounds`. Timeline events are assembled on the server from LOT creation/terminal status, outsource instruction/receipt/completion/shipment timestamps, and every inspection schedule/result so the client does not infer business history from display flags.
- The WPF LOT detail window uses a timeline-first layout: fixed KPI summary, chronological event list, compact core information, outsource summary, all inspection rounds, and defect-image actions. Rework LOT creation events include the parent LOT and stored rework reason.
- LOT-detail defect rows preserve their originating inspection result and expose inspection round, inspection date, and split/final classification. The WPF defect table orders rows by inspection round so defects from split and final inspections are not mixed into an unlabeled LOT-wide list.
- The WPF LOT detail window shows the memo entered during inspection-result registration in a dedicated section below the defect table. Each completed inspection-result round remains visible even when its memo is blank, while pending schedules are excluded. Split reasons remain in the inspection-round table's final column and are not mixed into the result-memo section.
- The LOT router should keep the trace-detail endpoint limited to request handling and service delegation.
- Manual rework LOT creation through `POST /api/v1/lots` is handled by `lot_rework_service.py`.
- Rework LOT creation requires a selected primary parent LOT in `DONE` or `CANCELED` status, creates routing steps from the product routing template, and changes a `DONE` order line back to `CLOSED` so rework can proceed.
- Manual confirmation should open LOT detail from LOT management and product history monitoring, then verify order/product fields, outsource work rows, inspection totals, defect rows, and defect image opening.
- Manual rework confirmation should create a rework LOT from an eligible parent LOT and verify the new child LOT appears with generated LOT number, copied routing steps, and parent LOT linkage.

## Time Policy

- Persisted event timestamps are created as timezone-aware UTC values.
- PostgreSQL `timestamp with time zone` columns store the instant independently of the database session display timezone.
- Existing timestamps are not shifted because the current PostgreSQL `Asia/Seoul` session already interpreted older naive values as Korea local time.
- Business calendar dates such as LOT creation date, inspection date, order date, and due date remain date-only values based on the Korea business day.
- Inspection start keeps the same-day-only rule, but PostgreSQL's transaction timestamp converted explicitly to `Asia/Seoul` is the authoritative business date. A database/application date disagreement selects the database date and records both dates with the request ID; a rejected start also records the schedule ID, LOT ID, inspection date, and selected business date.
- Date-range filters over event timestamps convert Korea midnight boundaries to UTC and use a half-open range (`start <= value < next day`).
- MES and vendor WPF API clients convert timestamp values carrying `Z` or an explicit offset to Korea time when deserializing. Date-only JSON values are left unchanged.

## Refactoring Closure

### Product, list paging, and drawing-file consistency

- Product list read models are assembled by `product_query.py`. The paged list uses one count query and one projection query for product, drawing number, routing-template name, and current product inventory; partner filtering uses an `EXISTS` condition so multiple order lines do not duplicate products.
- The product-history product grid displays `current_stock_qty` immediately to the right of the drawing number.
- The main product, drawing, partner, process, defect type, routing template, routing-step template, user, role, inventory, pending-new-drawing, production-daily, and product-history lists expose previous/next paging controls and use the API response `total`, `page`, and `size` values. Failed page loads restore the previously displayed page. Lookup lists and selected-record detail collections keep their existing bounded fetch behavior.
- New drawing revisions with selected DRAWING, ORIGINAL, and PLATE files use `POST /api/v1/drawings/{drawing_id}/revisions/bundle`. The backend writes all selected files before one DB commit, rolls the DB transaction back on failure, and removes newly stored files that do not have a committed revision row.
- Existing single-file upload and replacement endpoints also remove the newly written file when their DB operation fails. Replacement removes the old file only after the new database reference commits.
- Drawing WPF screens share one multipart-content builder so field names and file disposal behavior remain consistent.
- Inspection sellable-quantity normalization and validation is isolated in `inspection_quantity_policy.py`; the inspection-result service converts policy failures to HTTP 422 and retains the legacy prior-round stock allocation behavior.
- Outsource partner names for CUT, PRINT, and DIECUT are defined once in `routing_policy.py`. Changing partner identity from a name-based rule to a stable database code remains a schema/data migration and requires a separate migration plan.

The current operational refactoring scope is closed for the active MES flows covered below.

- Order-line registration, planning, bulk import, update, cancel, delete, short-close, and LOT creation.
- LOT list/detail/trace/rework and production-progress status calculation.
- Outsource work instruction, work group, purchase order, Bohyun inbound/work-done/shipment, and processing-cost allocation/closing.
- Inspection work-instruction target, inspection schedule, stock-LOT lookup, inspection result, attachment, shipment, and inventory settlement queries.
- Product inventory adjustment and raw-material master/inventory/movement flows.
- User role assignment and vendor-partner access management.

Active routers in this scope should contain only request parsing, authorization dependencies, service/query delegation, transaction commit/rollback, response conversion, and file-response construction. Business rules and read-model assembly belong in service/query modules.

Common technical cleanup completed with this scope:

- All SQLAlchemy models and Alembic autogenerate use the single `app.db.base.Base` metadata registry.
- Pydantic response models use Pydantic 2 `ConfigDict` instead of deprecated class-based `Config` declarations.
- Inspection stock-LOT assembly is owned by `inspection_schedule_query.py`.
- User list/detail/role/vendor-access reads are owned by `user_management_query.py`; user create/update/password-reset/deactivation rules are owned by `user_management_service.py`.

The following are classified legacy or compatibility items and are intentionally retained after closure:

- Purchase-order detail API that is not currently connected to WPF.
- Legacy purchase-order item status fallback used only when no current work-group status exists.

The detail API is retained for possible future screen use. The data fallback requires a legacy-data audit before removal and is not an authoritative source for the current operational flow.

## Outsource Processing Cost Management

The Production Management menu includes `Outsource Processing Cost Management`.

### Scope

- Manage standard processing cost and actual processing cost separately.
- Manage supply amount only. VAT and tax invoices are outside this feature.
- Register costs by process:
  - `CUT`: cutting cost
  - `PRINT`: printing cost
  - `DIECUT`: die-cutting cost
- The cost process is a cost category, not necessarily the same as the operational outsource work group process.
- `CUT` and `DIECUT` cost targets include all outsource work groups.
- `PRINT` cost targets include only `PRINT` outsource work groups.
- Use a cost group as the settlement unit.
- Register cost targets by outsource work group for all processes.
- Allow multiple outsource work groups to be combined into one cost group for SCM settlement.
- Use manually selected settlement month as the monthly closing basis.
- For bundle targets, display the representative LOT and representative product name in the target list while keeping all LOTs available for allocation and detail review.
- Target selection shows LOT-level allocation basis preview even before a cost group is saved. Standard and actual allocated amounts are filled after cost registration.

### Allocation Rules

- `CUT`: allocate by area, calculated as product width x product length x instructed output quantity.
- `PRINT`: allocate by area, calculated as product width x product length x instructed output quantity.
- `DIECUT`: allocate by area, calculated as product width x product length x instructed output quantity.

All allocation inputs are saved as snapshots when a cost group is created:

- LOT number
- product code/name/spec
- product width and length
- cuts per sheet
- sheet quantity
- instructed output quantity
- allocation basis type and value
- allocation ratio
- standard allocated amount
- actual allocated amount

### Closing Rules

- `DRAFT`: editable.
- `CLOSED`: monthly closed. Normal edits are blocked.
- `CANCELED`: canceled. Data remains for auditability.
- Actual processing cost must be entered before monthly closing.
- A cost variance is a review item, not a closing blocker. If standard cost and actual cost differ, the user can still close the group after confirming the variance.
- `COST_VARIANCE` is a query-only status for open variance review. It returns `DRAFT` groups where standard cost and actual cost are both entered and differ.
- Closed groups can be reopened by users with write permission.

### Permissions

Current WPF outsource processing cost API usage:

- `OutsourceProcessingCostManagementView` uses cost target lookup, cost group list lookup, cost group create, cost group update, close, reopen, and cancel APIs.
- Processing-cost targets are paged with `page` and `size`; checked target keys are retained across target pages until the search condition changes or the group is created.
- Internal and vendor Bohyun group lists are paged. The vendor shipment print flow fetches every filtered page before building the print document, and `processing_fee_total` represents the full filtered result.
- The `Outsource Processing Cost Management` screen currently shows an `Excel download` button placeholder, but the button is disabled and no API is connected for processing-cost Excel download.
- Processing-cost Excel download should be treated as a future feature, not as an active regression-test item.

- `OUTSOURCE_PROCESSING_COSTS.VIEW`: view menu and data.
- `OUTSOURCE_PROCESSING_COSTS.WRITE`: create, update, close, reopen, and cancel cost groups.

## Database Runtime Limits

- PostgreSQL uses an explicit pool per API worker: `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`, `DB_POOL_TIMEOUT_SECONDS=10`, and `DB_POOL_RECYCLE_SECONDS=1800` by default.
- Maximum application connections are approximately `worker count * (pool size + max overflow)`. A worker is one API server process, not one MES user.
- Start production with one worker. Before increasing workers, confirm that the PostgreSQL connection budget also covers administration, migration, backup, and monitoring connections.
- New connections use a 5-second connect timeout. Normal statements use 30 seconds, lock waits use 5 seconds, and idle transactions use 60 seconds by default.
- Bulk validation/import endpoints use `DB_BULK_STATEMENT_TIMEOUT_SECONDS=120` only for their current transaction and return to the normal timeout after commit or rollback.
- These values are environment settings. Increase them only from measured evidence; do not remove the limits to work around a slow query.

Pool and timeout failures:

- A pool checkout timeout returns HTTP 503. This means all connections available to that API process were busy for the configured wait period.
- PostgreSQL query cancellation with SQLSTATE `57014` returns HTTP 504. Other database operational failures return HTTP 503.
- The request database dependency explicitly rolls back an active transaction before closing the session when an exception escapes.
- A client timeout does not prove that a write failed. The database may have committed immediately before the network response was lost. Check the target list or detail before retrying any bulk or status-changing request.

## Desktop API Request Limits

The internal MES WPF client uses request-specific limits instead of one global timeout:

- Normal lookup and save requests: 45 seconds.
- Bulk validation and registration requests: 150 seconds.
- Multipart uploads and streamed downloads: 300 seconds.

These values are configured under `Api` in each WPF `appsettings*.json` file as `NormalTimeoutSeconds`, `BulkTimeoutSeconds`, and `FileTransferTimeoutSeconds`. The vendor WPF currently has normal requests only and uses `NormalTimeoutSeconds=45`.

- `HttpClient.Timeout` remains infinite; every request receives its own cancellation token with the operation-specific limit.
- File downloads stream to a sibling temporary file and replace the destination only after a complete transfer. A timeout or failure removes the partial file.
- Timeout messages and network-connection messages are distinct.
- Server error messages include the response `X-Request-ID` when available so support can find the matching server log.
- Adding a new bulk endpoint requires using `PostBulkAsync`; adding a new file transfer requires the multipart or download API so it receives the file-transfer limit.

## Runtime Health and Request Tracing

Health endpoints have different purposes:

- `GET /api/v1/health` is a liveness check. It confirms that the API process can respond and does not query PostgreSQL.
- `GET /api/v1/ready` is a readiness check. It runs `SELECT 1`; it returns 200 with `{"status":"ready"}` when the database is available and 503 with `{"status":"unavailable"}` otherwise.
- A process manager or internal load balancer should stop sending new business traffic to an instance whose readiness check fails. External vendor monitoring may use liveness, but database readiness should remain on the internal monitoring path.

Every HTTP request receives an `X-Request-ID` response header. A caller-provided ID is accepted only when it is 1 to 64 characters using letters, digits, `.`, `_`, or `-`; otherwise the server creates a new ID.

Request logs contain only request ID, method, route template, status, elapsed milliseconds, and unexpected error type. They do not record query strings, request bodies, SQL text, SQL parameters, tokens, or passwords.

- Requests at or above `SLOW_REQUEST_THRESHOLD_MS=2000` are warning logs.
- SQL statements at or above `SLOW_QUERY_THRESHOLD_MS=1000` are warning logs linked to the current request ID.
- Slow-query logs contain only the statement type, elapsed time, and failure flag. SQL text and parameters are intentionally excluded.
- When a user reports an API error, record the displayed request ID and search `mes.request` and `mes.database` logs for that same ID.

## Long-Term Database Monitoring

The application now bounds connections and records slow operations, but ten-year operation also requires recurring database administration outside the application process.

- Before V2 production rollout, enable PostgreSQL `pg_stat_statements` in the server maintenance window if the installed PostgreSQL package supports it. This is a server configuration change and restart, not an Alembic migration.
- Review the highest total-time and highest mean-time normalized queries monthly at first. Use `EXPLAIN (ANALYZE, BUFFERS)` only on a safe copy or during a controlled window for expensive write queries.
- Add or change indexes only from measured query plans. Re-run `alembic check` and metadata-alignment tests after every index change.
- Monitor database size, largest tables and indexes, dead tuples, autovacuum activity, connection usage, lock waits, and backup age.
- Keep automated backups and perform a restore rehearsal at least quarterly. A backup that has never been restored is not considered verified.
- As data grows, archive or partition only after retention rules and actual table growth justify it. Do not delete audit, inventory movement, allocation, or status history merely to improve screen speed.

Backup and isolated restore commands, safety guards, and the verified local drill are documented in `docs/backup-restore-runbook.md`.

## Operations Monitoring And Deployment Automation

Long-term database and backup checks are implemented as an external read-only command, not as a privileged API endpoint or FastAPI startup task.

- `check_mes_operations.py` checks connection usage, lock waits, long queries, idle transactions, autovacuum/statistics settings, dead tuples, index validity, planner statistics, `pg_monitor`, `pg_stat_statements`, DB incidents, backup age, restore-rehearsal age, and monitored-volume free space.
- The check uses a read-only transaction with a 10-second statement timeout and emits no SQL text, parameters, connection URLs, or passwords.
- Normal, warning, and critical results use exit codes `0`, `1`, and `2`; JSON history can be stored outside the release tree for trend review.
- `configure_postgres_monitoring.py` is idempotent and runs only from the approved deployment process. It never runs during application startup.
- PostgreSQL preload changes return exit code `3`; service restart requires a separate deployment approval before extension finalization.
- The monitor login must be separate from the application and deployment roles and receives `pg_monitor` plus database `CONNECT`, not application-table write permission.
- A successful isolated restore can atomically update the restore-rehearsal record only after generated DB/file cleanup succeeds.
- Windows scheduled tasks run one online daily backup and one daily read-only operations check. Deployment and quarterly baseline backups remain maintenance-mode operations.
- Scheduled-task registration is repeatable and supports explicit removal without deleting backups, monitoring history, or logs.
- `Invoke-MesDeployment.ps1` assumes a reviewed release is already staged. It performs preflight, API service stop, maintenance backup, explicitly approved monitoring setup/restart, explicitly approved migration, task registration, API restart, and optional health/readiness verification.

Detailed configuration, thresholds, commands, failure handling, and service-account rules are documented in `docs/operations-monitoring-deployment.md`.

## V2 Pre-Deployment Gate

V2 remains local until the feature set is complete. Before the first server deployment:

1. Run `Test-MesRelease.ps1 -RequireCleanWorktree` from the exact release revision and retain its successful JSON report. This gate runs the complete backend suite, Alembic head/metadata checks, NuGet restore, both WPF Release builds, source policy, output validation, and validation worktree-integrity check.
2. Run `New-MesReleasePackage.ps1` and retain the immutable ZIP, sidecar manifest, package SHA-256, and matching validation report. Revalidate the ZIP against the expected full commit before server staging.
3. Run `Test-MesReleaseInstallation.ps1` in a new isolated root and retain its successful report. This must prove verified staging, activation pointer switching, explicit application rollback, and injected-failure automatic pointer recovery without touching the production database or services.
4. Run `Test-MesRuntimeRehearsal.ps1` with a local non-production PostgreSQL env file and retain its successful report. This must prove offline dependency installation, runtime verification, API health/readiness, startup-failure isolation, and an unchanged active pointer without migration, lifespan startup, or service changes.
5. Run `Test-MesReleaseActivationRehearsal.ps1` and retain its successful report. This must prove a healthy candidate activation and automatic previous-release recovery after an injected candidate startup failure.
6. Run `Test-MesGoLiveReadiness.ps1`; require one exact commit and package hash across the quality gate and all three rehearsal reports.
7. Create a production backup and complete a restore rehearsal on a separate database.
8. Verify the target database current/heads and review the planned migrations before running `alembic upgrade head`; run `current --check-heads` and `alembic check` after upgrade.
9. Confirm any migration is backward compatible before approving automatic application rollback, or prepare a manual database recovery decision instead.
10. Confirm the PostgreSQL connection budget using `worker count * (DB_POOL_SIZE + DB_MAX_OVERFLOW)` and start with one API worker.
11. Confirm production secrets, allowed hosts, storage roots, file permissions, and HTTPS or tunnel routing.
12. Verify `/api/v1/health`, `/api/v1/ready`, login, one read flow, one reversible write flow, one upload, and one download.
13. Watch 5xx responses, readiness failures, connection usage, slow requests, and slow queries during the initial operating window. Keep the database and application rollback plan ready until the window closes.

The local release quality gate is documented in `docs/release-validation.md`, artifact creation in `docs/release-package.md`, installation rollback rehearsal in `docs/release-installation-rehearsal.md`, runtime/API rehearsal in `docs/runtime-rehearsal.md`, release activation in `docs/release-activation.md`, final evidence in `docs/go-live-readiness.md`, and server operations in `docs/operations-monitoring-deployment.md`.
