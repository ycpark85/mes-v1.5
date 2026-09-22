using System;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.Inventories.Dtos
{
    public class InventoryMovementDto
    {
        [JsonPropertyName("inventory_movement_id")]
        public long InventoryMovementId { get; set; }

        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }

        [JsonPropertyName("product_inventory_lot_id")]
        public long? ProductInventoryLotId { get; set; }

        [JsonPropertyName("stock_lot_no")]
        public string? StockLotNo { get; set; }

        [JsonPropertyName("product_code")]
        public string? ProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("movement_type")]
        public string MovementType { get; set; } = string.Empty;

        [JsonPropertyName("qty")]
        public long Qty { get; set; }

        [JsonPropertyName("balance_after")]
        public long BalanceAfter { get; set; }

        [JsonPropertyName("lot_balance_after")]
        public long? LotBalanceAfter { get; set; }

        [JsonPropertyName("source_type")]
        public string? SourceType { get; set; }

        [JsonPropertyName("source_id")]
        public long? SourceId { get; set; }

        [JsonPropertyName("order_line_id")]
        public long? OrderLineId { get; set; }

        [JsonPropertyName("inspection_schedule_id")]
        public long? InspectionScheduleId { get; set; }

        [JsonPropertyName("inspection_result_id")]
        public long? InspectionResultId { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("created_at")]
        public DateTimeOffset CreatedAt { get; set; }

        public DateTime LocalCreatedAt => CreatedAt.ToOffset(TimeSpan.FromHours(9)).DateTime;
        public long? InQty => MovementType is "INITIAL_STOCK" or "INSPECTION_IN" or "ADJUST_IN" ? Qty : null;
        public long? OutQty => MovementType is "SHIP_OUT" or "ADJUST_OUT" ? -Qty : null;
        public string MovementLabel => MovementType switch
        {
            "INITIAL_STOCK" => "기초재고",
            "INSPECTION_IN" => Qty < 0 ? "입고 정정" : "검수입고",
            "SHIP_OUT" => Qty > 0 ? "출고 정정" : "출고",
            "ADJUST_IN" => "재고증가",
            "ADJUST_OUT" => "재고감소",
            _ => MovementType
        };
        public string ReferenceLabel => InspectionResultId.HasValue ? "검수실적"
            : MovementType is "ADJUST_IN" or "ADJUST_OUT" ? "재고조정"
            : MovementType == "INITIAL_STOCK" ? "기초재고등록" : "출하";
    }
}
