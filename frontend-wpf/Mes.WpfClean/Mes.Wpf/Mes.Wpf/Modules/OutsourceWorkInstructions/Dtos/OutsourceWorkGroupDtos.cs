using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OutsourceWorkInstructions.Dtos
{
    public sealed class OutsourceWorkGroupListDto
    {
        [JsonPropertyName("items")]
        public List<OutsourceWorkGroupListItemDto> Items { get; set; } = new();

        [JsonPropertyName("total_count")]
        public int TotalCount { get; set; }
    }

    public class OutsourceWorkGroupListItemDto
    {
        [JsonPropertyName("outsource_work_group_id")]
        public long OutsourceWorkGroupId { get; set; }

        [JsonPropertyName("outsource_work_instruction_id")]
        public long OutsourceWorkInstructionId { get; set; }

        [JsonPropertyName("instruction_no")]
        public string InstructionNo { get; set; } = string.Empty;

        [JsonPropertyName("instruction_date")]
        public DateTime InstructionDate { get; set; }

        [JsonPropertyName("process_type")]
        public string ProcessType { get; set; } = string.Empty;

        [JsonPropertyName("partner_name")]
        public string? PartnerName { get; set; }

        [JsonPropertyName("group_seq")]
        public string GroupSeq { get; set; } = string.Empty;

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("status_name")]
        public string StatusName { get; set; } = string.Empty;

        [JsonPropertyName("is_bundle")]
        public bool IsBundle { get; set; }

        [JsonPropertyName("representative_lot_no")]
        public string? RepresentativeLotNo { get; set; }

        [JsonPropertyName("representative_product_name")]
        public string? RepresentativeProductName { get; set; }

        [JsonPropertyName("lot_nos_text")]
        public string LotNosText { get; set; } = string.Empty;

        [JsonPropertyName("product_names_text")]
        public string ProductNamesText { get; set; } = string.Empty;

        [JsonPropertyName("sheet_qty")]
        public int SheetQty { get; set; }

        [JsonPropertyName("length_m")]
        public decimal? LengthM { get; set; }

        [JsonPropertyName("sheet_cut_count")]
        public int SheetCutCount { get; set; }

        [JsonPropertyName("fabric_lot_no")]
        public string? FabricLotNo { get; set; }

        [JsonPropertyName("can_cancel")]
        public bool CanCancel { get; set; }

        [JsonPropertyName("cancel_block_reason")]
        public string? CancelBlockReason { get; set; }

        [JsonPropertyName("can_update")]
        public bool CanUpdate { get; set; }

        [JsonPropertyName("update_block_reason")]
        public string? UpdateBlockReason { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        public string BundleText => IsBundle ? "묶음" : "개별";
    }

    public sealed class OutsourceWorkGroupDetailDto : OutsourceWorkGroupListItemDto
    {
        [JsonPropertyName("lots")]
        public List<OutsourceWorkGroupLotDto> Lots { get; set; } = new();

        [JsonPropertyName("files")]
        public List<OutsourceWorkInstructionFileDto> Files { get; set; } = new();
    }

    public sealed class OutsourceWorkGroupLotDto
    {
        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("order_no")]
        public string? OrderNo { get; set; }

        [JsonPropertyName("line_no")]
        public int? LineNo { get; set; }

        [JsonPropertyName("product_code")]
        public string? ProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("lot_qty")]
        public int? LotQty { get; set; }

        [JsonPropertyName("cuts_per_sheet")]
        public int CutsPerSheet { get; set; }

        [JsonPropertyName("expected_output_qty")]
        public int? ExpectedOutputQty { get; set; }
    }

    public sealed class OutsourceWorkGroupCancelRequest
    {
        [JsonPropertyName("reason")]
        public string Reason { get; set; } = string.Empty;
    }

    public sealed class OutsourceWorkGroupUpdateRequest
    {
        [JsonPropertyName("sheet_qty")]
        public int SheetQty { get; set; }

        [JsonPropertyName("length_m")]
        public decimal? LengthM { get; set; }

        [JsonPropertyName("sheet_cut_count")]
        public int SheetCutCount { get; set; }

        [JsonPropertyName("fabric_lot_no")]
        public string? FabricLotNo { get; set; }

        [JsonPropertyName("remark")]
        public string? Remark { get; set; }

        [JsonPropertyName("reason")]
        public string Reason { get; set; } = string.Empty;
    }
}
