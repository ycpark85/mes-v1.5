using System;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.InspectionSchedules.Dtos
{
    public class InspectionScheduleListItemDto
    {
        [JsonPropertyName("inspection_schedule_id")]
        public long InspectionScheduleId { get; set; }

        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("is_rework")]
        public bool IsRework { get; set; }

        [JsonPropertyName("outsource_work_group_id")]
        public long? OutsourceWorkGroupId { get; set; }

        [JsonPropertyName("outsource_work_group_item_id")]
        public long? OutsourceWorkGroupItemId { get; set; }

        [JsonPropertyName("bundle_no")]
        public string? BundleNo { get; set; }

        [JsonPropertyName("diecut_status")]
        public string? DiecutStatus { get; set; }

        [JsonPropertyName("plate_data_file_name")]
        public string? PlateDataFileName { get; set; }

        [JsonPropertyName("plate_data_file_path")]
        public string? PlateDataFilePath { get; set; }

        public bool HasBundle => !string.IsNullOrWhiteSpace(BundleNo);

        [JsonPropertyName("inspection_date")]
        public DateTime InspectionDate { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("day_seq")]
        public int? DaySeq { get; set; }

        [JsonPropertyName("due_date")]
        public DateTime DueDate { get; set; }

        [JsonPropertyName("partner_name")]
        public string PartnerName { get; set; } = string.Empty;

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

        [JsonPropertyName("product_spec")]
        public string? ProductSpec { get; set; }

        [JsonPropertyName("lot_qty")]
        public int LotQty { get; set; }

        [JsonPropertyName("order_qty")]
        public int OrderQty { get; set; }

        [JsonPropertyName("ship_qty")]
        public int ShipQty { get; set; }

        [JsonPropertyName("drawing_id")]
        public long DrawingId { get; set; }

        [JsonPropertyName("drawing_no")]
        public string? DrawingNo { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }


    }
}
