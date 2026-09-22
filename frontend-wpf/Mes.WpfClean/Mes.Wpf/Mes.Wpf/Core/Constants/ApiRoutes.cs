namespace Mes.Wpf.Core.Constants
{
    public static class ApiRoutes
    {
        public const string RuntimeInfo = "api/v1/runtime-info";
        public const string DefectTypes = "api/v1/defect-types";

        public const string Processes = "api/v1/processes";

        public const string RoutingTemplates = "api/v1/routing-templates";
        public const string RoutingTemplateSteps = "api/v1/routing-template-steps";

        public const string Partners = "api/v1/partners";
        public const string PartnersBulk = "api/v1/partners/bulk";

        public const string Drawings = "api/v1/drawings";
        public const string PendingNewDrawings = "api/v1/drawings/pending-new";

        public const string Products = "api/v1/products";
        public const string ProductsBulk = "api/v1/products/bulk";

        public const string OrderLines = "api/v1/order-lines";

        public const string Lots = "api/v1/lots";
        public const string ProductionDaily = "api/v1/production-daily";

        public const string InspectionSchedules = "api/v1/inspection-schedules";
        public const string InspectionWorkInstructionTargets = "api/v1/inspection-schedules/work-instruction-targets";
        public const string InspectionResults = "api/v1/inspection-schedules/results/list";

        public const string OutsourceWorkInstructionCandidates = "api/v1/outsource-work-instructions/candidates";
        public const string OutsourceWorkInstructionGroups = "api/v1/outsource-work-instructions/groups";
        public const string OutsourceWorkInstructionPlateUpload = "api/v1/outsource-work-instructions/upload-plate-data";
        public const string OutsourcePurchaseOrderTargets = "api/v1/outsource-work-instructions/purchase-order-targets";
        public const string OutsourceWorkInstructionBatch = "api/v1/outsource-work-instructions/batch";
        public const string OutsourcePurchaseOrders = "api/v1/outsource-work-instructions/purchase-orders";
        public const string OutsourcePurchaseOrderExcel = "api/v1/outsource-work-instructions/purchase-orders";
        public const string BohyunOutsourceGroups = "api/v1/outsource-work-instructions/bohyun-groups";
        public const string OutsourceProcessingCosts = "api/v1/outsource-processing-costs";
        public const string OutsourceProcessingCostTargets = "api/v1/outsource-processing-costs/targets";

        public const string DashboardSummary = "api/v1/dashboard/summary";

        public const string Inventories = "api/v1/inventories";
        public const string InventoryMovements = "api/v1/inventories/movements";
        public const string InventoryConsistency = "api/v1/inventories/consistency";
        public const string Shipments = "api/v1/shipments";
        public const string InitialInventoryBulk = "api/v1/inventories/initial-bulk";

        public const string OrderLinesBulkValidate = "api/v1/order-lines/bulk/validate";
        public const string OrderLinesBulkCommit = "api/v1/order-lines/bulk/commit";

        public const string AuthLogin = "api/v1/auth/login";
        public const string AuthMe = "api/v1/auth/me";
        public const string AuthChangePassword = "api/v1/auth/change-password";

        public const string Users = "api/v1/users";
        public const string UserRoleOptions = "api/v1/users/role-options";

        public const string Roles = "api/v1/roles";
        public const string Permissions = "api/v1/permissions";


    }
}
