using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.Lots.Dtos
{
    public class LotCreateContextDto
    {
        [JsonPropertyName("order_line_id")]
        public long OrderLineId { get; set; }

        [JsonPropertyName("order_no")]
        public string OrderNo { get; set; } = string.Empty;

        [JsonPropertyName("partner_id")]
        public long PartnerId { get; set; }

        [JsonPropertyName("partner_name")]
        public string PartnerName { get; set; } = string.Empty;

        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

        [JsonPropertyName("order_qty")]
        public int OrderQty { get; set; }

        [JsonPropertyName("uom")]
        public string Uom { get; set; } = string.Empty;

        [JsonPropertyName("due_date")]
        public DateTime DueDate { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("panel_width_mm")]
        public int? PanelWidthMm { get; set; }

        [JsonPropertyName("panel_length_mm")]
        public int? PanelLengthMm { get; set; }

        [JsonPropertyName("cut_qty_per_panel")]
        public int? CutQtyPerPanel { get; set; }

        [JsonPropertyName("product_spec")]
        public string? ProductSpec { get; set; }

        [JsonPropertyName("drawing")]
        public LotCreateDrawingDto? Drawing { get; set; }

        [JsonPropertyName("primary_lot_candidates")]
        public List<LotCreatePrimaryCandidateDto> PrimaryLotCandidates { get; set; } = new();

        [JsonPropertyName("can_create_primary_lot")]
        public bool CanCreatePrimaryLot { get; set; }
    }

    public class LotCreateDrawingDto
    {
        [JsonPropertyName("drawing_id")]
        public long? DrawingId { get; set; }

        [JsonPropertyName("drawing_no")]
        public string? DrawingNo { get; set; }

        [JsonPropertyName("current_revision_id")]
        public long? CurrentRevisionId { get; set; }

        [JsonPropertyName("current_revision_no")]
        public string? CurrentRevisionNo { get; set; }

        [JsonPropertyName("drawing_file_id")]
        public long? DrawingFileId { get; set; }

        [JsonPropertyName("drawing_file_name")]
        public string? DrawingFileName { get; set; }

        [JsonPropertyName("original_file_id")]
        public long? OriginalFileId { get; set; }

        [JsonPropertyName("original_file_name")]
        public string? OriginalFileName { get; set; }

        [JsonPropertyName("plate_file_id")]
        public long? PlateFileId { get; set; }

        [JsonPropertyName("plate_file_name")]
        public string? PlateFileName { get; set; }
    }

    public class LotCreatePrimaryCandidateDto
    {
        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("lot_qty")]
        public int LotQty { get; set; }

        [JsonPropertyName("uom")]
        public string Uom { get; set; } = string.Empty;

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("can_create_rework")]
        public bool CanCreateRework { get; set; }
    }
}