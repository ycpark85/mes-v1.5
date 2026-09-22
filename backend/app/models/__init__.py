from .process import Process
from .routing_template import RoutingTemplate
from .routing_template_step import RoutingTemplateStep
from .drawing import Drawing
from .drawing_revision import DrawingRevision
from .product import Product
from .partner import Partner
from .defect_type import DefectType
from .order_line import OrderLine
from .order_line_change_log import OrderLineChangeLog
from app.models.order_line_plan_history import OrderLinePlanHistory
from .lot import Lot
from .lot_step import LotStep
from .inspection_schedule import InspectionSchedule
from .inspection_result import InspectionResult
from .inspection_result_revision import InspectionResultRevision
from .inspection_defect import InspectionDefect
from .inspection_defect_attachment import InspectionDefectAttachment
from .inspection_certificate import InspectionCertificate
from .drawing_rivision_file import DrawingRevisionFile
from .outsource_purchase_order import OutsourcePurchaseOrder
from .outsource_work_instruction import OutsourceWorkInstruction
from .outsource_work_instruction_item import OutsourceWorkInstructionItem
from .outsource_work_instruction_file import OutsourceWorkInstructionFile
from .outsource_purchase_order_item import OutsourcePurchaseOrderItem
from .outsource_work_group import OutsourceWorkGroup
from .outsource_work_group_item import OutsourceWorkGroupItem
from .outsource_purchase_order_group import OutsourcePurchaseOrderGroup
from .outsource_processing_cost_group import OutsourceProcessingCostGroup
from .outsource_processing_cost_work_group import OutsourceProcessingCostWorkGroup
from .outsource_processing_cost_allocation import OutsourceProcessingCostAllocation
from .product_inventory import ProductInventory
from .product_inventory_lot import ProductInventoryLot
from .product_inventory_movement import ProductInventoryMovement
from .raw_material import RawMaterial
from .raw_material_location import RawMaterialLocation
from .raw_material_inventory import RawMaterialInventory
from .raw_material_inventory_lot import RawMaterialInventoryLot
from .raw_material_inventory_movement import RawMaterialInventoryMovement
from .outsource_work_group_raw_material_allocation import OutsourceWorkGroupRawMaterialAllocation
from .outsource_work_group_change_log import OutsourceWorkGroupChangeLog
from .shipment_line import ShipmentLine
from .production_progress_snapshot import ProductionProgressSnapshot
from .user import User
from .role import Role
from .user_role import UserRole
from .permission import Permission
from .role_permission import RolePermission
from .shipment_coa import ShipmentCoa
from .auth_audit_log import AuthAuditLog
from .vendor_user_access import VendorUserAccess
from .vendor_portal_audit_log import VendorPortalAuditLog

__all__ = [
    "Process", 
    "RoutingTemplate", 
    "RoutingTemplateStep",
    "Drawing",
    "DrawingRevision",
    "Product",
    "Partner",
    "DefectType",
    "OrderLine",
    "OrderLineChangeLog",
    "OrderLinePlanHistory",
    "Lot",
    "LotStep",
    "InspectionSchedule",
    "InspectionResult",
    "InspectionResultRevision",
    "InspectionDefect",
    "InspectionDefectAttachment",
    "InspectionCertificate",
    "DrawingRevisionFile",
    "OutsourceWorkInstruction",
    "OutsourceWorkInstructionItem",
    "OutsourceWorkInstructionFile",
    "OutsourcePurchaseOrder",
    "OutsourcePurchaseOrderItem",
    "OutsourceWorkGroup",
    "OutsourceWorkGroupItem",
    "OutsourcePurchaseOrderGroup",
    "OutsourceProcessingCostGroup",
    "OutsourceProcessingCostWorkGroup",
    "OutsourceProcessingCostAllocation",
    "ProductInventory",
    "ProductInventoryLot",
    "ProductInventoryMovement",
    "RawMaterial",
    "RawMaterialLocation",
    "RawMaterialInventory",
    "RawMaterialInventoryLot",
    "RawMaterialInventoryMovement",
    "OutsourceWorkGroupRawMaterialAllocation",
    "OutsourceWorkGroupChangeLog",
    "ShipmentLine",
    "ProductionProgressSnapshot",
    "User",
    "Role",
    "UserRole",
    "Permission",
    "RolePermission",
    "ShipmentCoa",
    "AuthAuditLog",
    "VendorUserAccess",
    "VendorPortalAuditLog"
]
