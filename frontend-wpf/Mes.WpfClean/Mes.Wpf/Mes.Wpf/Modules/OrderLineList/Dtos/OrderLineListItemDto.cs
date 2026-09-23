using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OrderLineList.Dtos
{
    public class OrderLineListItemDto
    {
        [JsonPropertyName("order_line_id")]
        public long OrderLineId { get; set; }

        [JsonPropertyName("order_no")]
        public string OrderNo { get; set; } = string.Empty;

        [JsonPropertyName("line_no")]
        public int LineNo { get; set; }

        [JsonPropertyName("partner_id")]
        public long PartnerId { get; set; }

        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }

        [JsonPropertyName("order_date")]
        public DateTime OrderDate { get; set; }

        [JsonPropertyName("due_date")]
        public DateTime DueDate { get; set; }

        [JsonPropertyName("order_qty")]
        public int OrderQty { get; set; }

        [JsonPropertyName("uom")]
        public string Uom { get; set; } = string.Empty;

        [JsonPropertyName("customer_po")]
        public string? CustomerPo { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("is_active")]
        public bool IsActive { get; set; }

        [JsonPropertyName("priority")]
        public int Priority { get; set; }

        [JsonPropertyName("partner_name")]
        public string? PartnerName { get; set; }

        [JsonPropertyName("product_code")]
        public string? ProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("has_lot")]
        public bool HasLot { get; set; }

        [JsonPropertyName("lot_count")]
        public int LotCount { get; set; }

        [JsonPropertyName("fulfillment_mode")]
        public string? FulfillmentMode { get; set; }

        [JsonPropertyName("production_policy")]
        public string? ProductionPolicy { get; set; }

        [JsonPropertyName("extra_production_qty")]
        public int ExtraProductionQty { get; set; }

        [JsonPropertyName("decision_made")]
        public bool DecisionMade { get; set; }

        [JsonPropertyName("decision_made_at")]
        public DateTime? DecisionMadeAt { get; set; }

        [JsonPropertyName("decision_made_by")]
        public string? DecisionMadeBy { get; set; }

        [JsonPropertyName("available_inventory_qty")]
        public int AvailableInventoryQty { get; set; }

        [JsonPropertyName("recommended_fulfillment_mode")]
        public string? RecommendedFulfillmentMode { get; set; }

        [JsonPropertyName("recommended_production_qty")]
        public int RecommendedProductionQty { get; set; }

        [JsonPropertyName("planned_production_qty")]
        public int PlannedProductionQty { get; set; }

        [JsonPropertyName("planned_stock_ship_qty")]
        public int PlannedStockShipQty { get; set; }

        [JsonPropertyName("decision_required")]
        public bool DecisionRequired { get; set; }

        [JsonPropertyName("allowed_plan_types")]
        public List<string> AllowedPlanTypes { get; set; } = new();

        [JsonPropertyName("target_ship_qty")]
        public int TargetShipQty { get; set; }

        [JsonPropertyName("expected_ship_qty")]
        public int ExpectedShipQty { get; set; }

        [JsonPropertyName("expected_short_qty")]
        public int ExpectedShortQty { get; set; }

        [JsonPropertyName("ship_target_qty")]
        public int ShipTargetQty { get; set; }

        [JsonPropertyName("already_shipped_qty")]
        public int AlreadyShippedQty { get; set; }

        [JsonPropertyName("remaining_ship_qty")]
        public int RemainingShipQty { get; set; }

        [JsonPropertyName("needs_shortage_action")]
        public bool NeedsShortageAction { get; set; }

        [JsonPropertyName("shortage_closed")]
        public bool ShortageClosed { get; set; }

        [JsonPropertyName("short_close_state")]
        public string ShortCloseState { get; set; } = "NONE";

        [JsonPropertyName("manual_closed")]
        public bool ManualClosed { get; set; }

        [JsonPropertyName("work_queue")]
        public string? WorkQueue { get; set; }

        [JsonPropertyName("updated_at")]
        public DateTimeOffset? UpdatedAt { get; set; }

        public string DecisionStatusDisplay => DecisionMade ? "결정완료" : "결정필요";

        [JsonPropertyName("plan_type")]
        public string? PlanType { get; set; }

        [JsonPropertyName("plan_type_display")]
        public string? PlanTypeDisplay { get; set; }




        public string StatusDisplay => Status switch
        {
            "OPEN" => "LOT 생성대기",
            "CLOSED" when WorkQueue == "CLOSE_DECISION" => "종료판단대기",
            "CLOSED" => "생산중",
            "DONE" when ManualClosed => "완료(수동)",
            "DONE" when ShortCloseState == "REVIEW_REQUIRED" => "완료(종료 확인 필요)",
            "DONE" => "완료",
            "CANCELED" => "취소",
            _ => Status
        };

        public string FulfillmentModeDisplay => FulfillmentMode switch
        {
            "INVENTORY_FIRST" => "재고 우선",
            "PRODUCTION_FIRST" => "생산 우선",
            "HYBRID" => "혼합",
            _ => "-"
        };

        public string ProductionPolicyDisplay => ProductionPolicy switch
        {
            "ORDER_ONLY" => "주문분만 생산",
            "ALLOW_STOCK_BUILD" => "추가 생산 허용",
            "INVENTORY_ONLY_CLOSE" => "재고만 출고 후 종료",
            _ => "-"
        };

        public string RecommendedFulfillmentModeDisplay => RecommendedFulfillmentMode switch
        {
            "INVENTORY_FIRST" => "재고 우선",
            "PRODUCTION_FIRST" => "생산 우선",
            "HYBRID" => "혼합",
            _ => "-"
        };

        public string ShortageStatusDisplay
        {
            get
            {
                if (ShortCloseState == "REVIEW_REQUIRED")
                    return "과거 부족종료 확인 필요";
                if (ManualClosed)
                    return "완료(수동)";
                if (ShortageClosed)
                {
                    return "부족종료";
                }

                if (NeedsShortageAction)
                {
                    return "종료판단대기";
                }

                return "-";
            }
        }

       
    }
    public class OrderLinePlanConfirmRequest
    {
        [JsonPropertyName("plan_type")]
        public string PlanType { get; set; } = string.Empty;

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }
    }
    

}
