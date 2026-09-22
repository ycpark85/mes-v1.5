using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.Inventories.Dtos
{
    public class InventoryMovementListDto
    {
        [JsonPropertyName("items")]
        public List<InventoryMovementDto> Items { get; set; } = new();

        [JsonPropertyName("total")]
        public int Total { get; set; }

        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }
        [JsonPropertyName("product_inventory_lot_id")]
        public long? ProductInventoryLotId { get; set; }
        [JsonPropertyName("stock_lot_no")]
        public string? StockLotNo { get; set; }
        [JsonPropertyName("current_qty")]
        public long? CurrentQty { get; set; }
        [JsonPropertyName("lot_updated_at")]
        public System.DateTimeOffset? LotUpdatedAt { get; set; }
        [JsonPropertyName("history_warning")]
        public string? HistoryWarning { get; set; }
        [JsonPropertyName("stock_snapshot")]
        public InventoryLotListDto? StockSnapshot { get; set; }
    }
}
