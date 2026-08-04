from fastapi import APIRouter, Depends

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as user_router
from app.api.v1.permissions import router as permission_router
from app.api.v1.roles import router as role_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.partners_lagacy import router as partner_router
from app.api.v1.processes import router as process_router
from app.api.v1.routing_templates import router as routing_template_router
from app.api.v1.drawings import router as drawing_router
from app.api.v1.drawing_revisions import router as drawing_revision_router
from app.api.v1.products import router as product_router
from app.api.v1.order_lines import router as order_line_router
from app.api.v1.lots import router as lot_router
from app.api.v1.inspection_schedules import router as inspection_schedule_router
from app.api.v1.inspection_results import router as inspection_result_router
from app.api.v1.defect_types import router as defect_type_router
from app.api.v1.outsource_work_instructions import router as outsource_work_instruction_router
from app.api.v1.outsource_processing_costs import router as outsource_processing_cost_router
from app.api.v1.production_daily import router as production_daily_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.inventories import router as inventory_router
from app.api.v1.shipments import router as shipment_router
from app.api.v1.vendor_portal import router as vendor_portal_router

from app.core.auth import  require_any_permission, require_method_any_permission, require_permission

router = APIRouter()

# 인증 예외
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(vendor_portal_router)

# 회원 / 역할 / 권한 관리는 각 endpoint 내부에서 세부 권한 검증
router.include_router(user_router)
router.include_router(permission_router)
router.include_router(role_router)

# 주요 업무 API VIEW 권한 적용
router.include_router(
    dashboard_router,
    dependencies=[Depends(require_permission("DASHBOARD.VIEW"))],
)

router.include_router(
    defect_type_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("DEFECT_TYPES.VIEW",),
                write_permission_codes=("DEFECT_TYPES.WRITE",),
            )
        )
    ],
)

router.include_router(
    process_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("PROCESSES.VIEW",),
                write_permission_codes=("PROCESSES.WRITE",),
            )
        )
    ],
)

router.include_router(
    partner_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("PARTNERS.VIEW",),
                write_permission_codes=("PARTNERS.WRITE",),
            )
        )
    ],
)

router.include_router(
    routing_template_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=(
                    "ROUTING_TEMPLATES.VIEW",
                    "ROUTING_TEMPLATE_STEPS.VIEW",
                ),
                write_permission_codes=("ROUTING_TEMPLATES.WRITE",),
            )
        )
    ],
)

router.include_router(
    drawing_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("DRAWINGS.VIEW",),
                write_permission_codes=("DRAWINGS.WRITE",),
            )
        )
    ],
)

router.include_router(
    drawing_revision_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("DRAWINGS.VIEW",),
                write_permission_codes=("DRAWINGS.WRITE",),
            )
        )
    ],
)

router.include_router(
    product_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=(
                    "PRODUCTS.VIEW",
                    "PRODUCT_MONITORING.VIEW",
                ),
                write_permission_codes=("PRODUCTS.WRITE",),
            )
        )
    ],
)

router.include_router(
    order_line_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=(
                    "ORDER_LINE_CREATE.VIEW",
                    "ORDER_LINE_LIST.VIEW",
                ),
                write_permission_codes=("ORDER_LINES.WRITE",),
            )
        )
    ],
)

router.include_router(
    lot_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("LOTS.VIEW",),
                write_permission_codes=("LOTS.WRITE",),
            )
        )
    ],
)

router.include_router(
    production_daily_router,
    dependencies=[Depends(require_permission("PRODUCTION_DAILY.VIEW"))],
)

router.include_router(
    inspection_schedule_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=(
                    "INSPECTION_WORK_INSTRUCTIONS.VIEW",
                    "INSPECTION_SCHEDULES.VIEW",
                    "INSPECTION_RESULTS.VIEW",
                ),
                write_permission_codes=("INSPECTIONS.WRITE",),
            )
        )
    ],
)

router.include_router(
    inspection_result_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=(
                    "INSPECTION_WORK_INSTRUCTIONS.VIEW",
                    "INSPECTION_SCHEDULES.VIEW",
                    "INSPECTION_RESULTS.VIEW",
                ),
                write_permission_codes=("INSPECTIONS.WRITE",),
            )
        )
    ],
)

router.include_router(
    outsource_work_instruction_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=(
                    "OUTSOURCE_WORK_INSTRUCTIONS.VIEW",
                    "OUTSOURCE_PURCHASE_ORDERS.VIEW",
                    "OUTSOURCE_PURCHASE_ORDER_LIST.VIEW",
                    "BOHYUN_OUTSOURCE_MANAGEMENT.VIEW",
                    "BOHYUN_OUTSOURCE_SHIPMENT_LIST.VIEW",
                ),
                write_permission_codes=("OUTSOURCE_WORK_INSTRUCTIONS.WRITE",),
            )
        )
    ],
)

router.include_router(
    inventory_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("INVENTORIES.VIEW",),
                write_permission_codes=("INVENTORIES.WRITE",),
            )
        )
    ],
)

router.include_router(
    shipment_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("SHIPMENTS.VIEW",),
                write_permission_codes=("SHIPMENTS.WRITE",),
            )
        )
    ],
)

router.include_router(
    outsource_processing_cost_router,
    dependencies=[
        Depends(
            require_method_any_permission(
                read_permission_codes=("OUTSOURCE_PROCESSING_COSTS.VIEW",),
                write_permission_codes=("OUTSOURCE_PROCESSING_COSTS.WRITE",),
            )
        )
    ],
)
