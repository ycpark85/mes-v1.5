using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OrderLineList.Dtos
{
    public class OrderLineShortCloseRequest
    {
        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("expected_updated_at")]
        public System.DateTimeOffset? ExpectedUpdatedAt { get; set; }

        [JsonPropertyName("expected_ship_target_qty")]
        public int? ExpectedShipTargetQty { get; set; }

        [JsonPropertyName("expected_shipped_qty")]
        public int? ExpectedShippedQty { get; set; }
    }
}
