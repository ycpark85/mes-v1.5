using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OrderLineList.Dtos
{
    public class OrderLineDetailDto
    {
        [JsonPropertyName("order_line_id")]
        public long OrderLineId { get; set; }

        [JsonPropertyName("order_no")]
        public string OrderNo { get; set; } = string.Empty;

        [JsonPropertyName("line_no")]
        public int LineNo { get; set; }

        [JsonPropertyName("partner_id")]
        public long PartnerId { get; set; }

        [JsonPropertyName("partner_name")]
        public string PartnerName { get; set; } = string.Empty;

        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }

        [JsonPropertyName("source_erp_product_code")]
        public string? SourceErpProductCode { get; set; }
        [JsonPropertyName("source_product_name")]
        public string? SourceProductName { get; set; }
        [JsonPropertyName("source_product_spec")]
        public string? SourceProductSpec { get; set; }

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

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

        [JsonPropertyName("status_display")]
        public string StatusDisplay { get; set; } = string.Empty;

        [JsonPropertyName("is_active")]
        public bool IsActive { get; set; }

        [JsonPropertyName("can_edit")]
        public bool CanEdit { get; set; }

        [JsonPropertyName("can_save")]
        public bool CanSave { get; set; }

        [JsonPropertyName("can_cancel_order")]
        public bool CanCancelOrder { get; set; }

        [JsonPropertyName("can_create_base_lot")]
        public bool CanCreateBaseLot { get; set; }

        [JsonPropertyName("lots")]
        public List<OrderLineDetailLotDto> Lots { get; set; } = new();

        [JsonPropertyName("timeline")]
        public List<OrderLineTimelineItemDto> Timeline { get; set; } = new();
    }
}