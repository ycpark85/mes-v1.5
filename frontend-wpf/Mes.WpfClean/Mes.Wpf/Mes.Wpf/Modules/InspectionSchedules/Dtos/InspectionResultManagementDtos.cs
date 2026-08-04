using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.InspectionSchedules.Dtos
{
    public class InspectionResultManagementListDto
    {
        [JsonPropertyName("items")]
        public List<InspectionResultManagementItemDto> Items { get; set; } = new();

        [JsonPropertyName("total_count")]
        public int TotalCount { get; set; }

        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }

        [JsonPropertyName("total_good_qty")]
        public int TotalGoodQty { get; set; }

        [JsonPropertyName("total_uninspected_qty")]
        public int TotalUninspectedQty { get; set; }

        [JsonPropertyName("total_received_qty")]
        public int TotalReceivedQty { get; set; }

        [JsonPropertyName("total_result_ship_qty")]
        public int TotalResultShipQty { get; set; }

        [JsonPropertyName("total_discard_qty")]
        public int TotalDiscardQty { get; set; }

        [JsonPropertyName("total_stock_in_qty")]
        public int TotalStockInQty { get; set; }

        [JsonPropertyName("total_defect_qty")]
        public int TotalDefectQty { get; set; }
    }

    public class InspectionResultManagementItemDto
    {
        public int RowNo { get; set; }

        [JsonPropertyName("inspection_result_id")]
        public long InspectionResultId { get; set; }

        [JsonPropertyName("inspection_schedule_id")]
        public long InspectionScheduleId { get; set; }

        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("inspection_date")]
        public DateTime InspectionDate { get; set; }

        [JsonPropertyName("schedule_status")]
        public string ScheduleStatus { get; set; } = string.Empty;

        [JsonPropertyName("inspection_round")]
        public int InspectionRound { get; set; }

        [JsonPropertyName("inspection_round_count")]
        public int InspectionRoundCount { get; set; }

        [JsonPropertyName("is_partial")]
        public bool IsPartial { get; set; }

        [JsonPropertyName("next_inspection_date")]
        public DateTime? NextInspectionDate { get; set; }

        [JsonPropertyName("partial_reason")]
        public string? PartialReason { get; set; }

        [JsonIgnore]
        public string InspectionRoundDisplay => $"{InspectionRound}차";

        [JsonIgnore]
        public string ResultTypeDisplay => IsPartial ? "분할" : "최종";

        [JsonPropertyName("due_date")]
        public DateTime DueDate { get; set; }

        [JsonPropertyName("partner_name")]
        public string PartnerName { get; set; } = string.Empty;

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

        [JsonPropertyName("lot_qty")]
        public int LotQty { get; set; }

        [JsonPropertyName("order_qty")]
        public int OrderQty { get; set; }

        [JsonPropertyName("good_qty")]
        public int GoodQty { get; set; }

        [JsonPropertyName("uninspected_qty")]
        public int UninspectedQty { get; set; }

        [JsonPropertyName("received_qty")]
        public int ReceivedQty { get; set; }

        [JsonPropertyName("result_ship_qty")]
        public int ResultShipQty { get; set; }

        [JsonPropertyName("discard_qty")]
        public int DiscardQty { get; set; }

        public int TotalDisposalQty => DiscardQty + UninspectedQty;

        [JsonPropertyName("stock_in_qty")]
        public int StockInQty { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("created_by")]
        public string? CreatedBy { get; set; }

        [JsonPropertyName("created_at")]
        public DateTime CreatedAt { get; set; }

        [JsonPropertyName("updated_at")]
        public DateTime UpdatedAt { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }
    }
}
