using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.Products.Dtos
{
    public class ProductCreateRequest
    {
        [JsonPropertyName("is_unprinted_managed")]
        public bool IsUnprintedManaged { get; set; }
        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

        [JsonPropertyName("uom")]
        public string Uom { get; set; } = string.Empty;

        [JsonPropertyName("drawing_id")]
        public long DrawingId { get; set; }

        [JsonPropertyName("routing_template_id")]
        public long RoutingTemplateId { get; set; }

        [JsonPropertyName("panel_width_mm")]
        public int? PanelWidthMm { get; set; }

        [JsonPropertyName("panel_length_mm")]
        public int? PanelLengthMm { get; set; }

        [JsonPropertyName("product_spec")]
        public string? ProductSpec { get; set; }

        [JsonPropertyName("cut_qty_per_panel")]
        public int? CutQtyPerPanel { get; set; }

        [JsonPropertyName("is_active")]
        public bool IsActive { get; set; } = true;

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }
    }
}