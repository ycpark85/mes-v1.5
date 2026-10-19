using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.InspectionSchedules.Dtos
{
    public class InspectionWorkInstructionLotListItemDto
    {
        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("outsource_work_group_id")]
        public long? OutsourceWorkGroupId { get; set; }

        [JsonPropertyName("outsource_work_group_item_id")]
        public long? OutsourceWorkGroupItemId { get; set; }

        [JsonPropertyName("bundle_no")]
        public string? BundleNo { get; set; }

        [JsonPropertyName("product_code")]
        public string? ProductCode { get; set; }

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("partner_name")]
        public string? PartnerName { get; set; }

        [JsonPropertyName("lot_qty")]
        public decimal LotQty { get; set; }

        [JsonPropertyName("due_date")]
        public DateTime? DueDate { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }
    }

    public class InspectionWorkInstructionLotListResponseDto
    {
        [JsonPropertyName("items")]
        public List<InspectionWorkInstructionLotListItemDto> Items { get; set; } = new();

        [JsonPropertyName("meta")]
        public PageMetaDto? Meta { get; set; }
    }

    public class PageMetaDto
    {
        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }

        [JsonPropertyName("total")]
        public int Total { get; set; }
    }
}