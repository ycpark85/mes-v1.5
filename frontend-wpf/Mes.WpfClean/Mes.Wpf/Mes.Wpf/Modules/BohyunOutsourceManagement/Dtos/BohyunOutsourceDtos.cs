using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.BohyunOutsourceManagement.Dtos
{
    public class BohyunOutsourceListDto
    {
        [JsonPropertyName("items")]
        public List<BohyunOutsourceListItemDto> Items { get; set; } = new();

        [JsonPropertyName("total_count")]
        public int TotalCount { get; set; }

        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }

        [JsonPropertyName("processing_fee_total")]
        public decimal ProcessingFeeTotal { get; set; }
    }

    public class BohyunOutsourceListItemDto
    {
        [JsonPropertyName("outsource_work_group_id")]
        public long OutsourceWorkGroupId { get; set; }

        [JsonPropertyName("outsource_work_instruction_id")]
        public long OutsourceWorkInstructionId { get; set; }

        [JsonPropertyName("representative_lot_id")]
        public long? RepresentativeLotId { get; set; }

        [JsonPropertyName("representative_product_name")]
        public string? RepresentativeProductName { get; set; }

        [JsonPropertyName("instruction_no")]
        public string InstructionNo { get; set; } = string.Empty;

        [JsonPropertyName("instruction_date")]
        public DateTime? InstructionDate { get; set; }

        [JsonPropertyName("process_type")]
        public string ProcessType { get; set; } = string.Empty;

        [JsonPropertyName("partner_id")]
        public long PartnerId { get; set; }

        [JsonPropertyName("partner_name")]
        public string PartnerName { get; set; } = string.Empty;

        [JsonPropertyName("inbound_source_name")]
        public string InboundSourceName { get; set; } = string.Empty;

        [JsonPropertyName("is_bundle")]
        public bool IsBundle { get; set; }

        [JsonPropertyName("group_seq")]
        public string? GroupSeq { get; set; }

        [JsonPropertyName("sheet_qty")]
        public int SheetQty { get; set; }

        [JsonPropertyName("work_done_sheet_qty")]
        public int? WorkDoneSheetQty { get; set; }

        [JsonPropertyName("length_m")]
        public decimal? LengthM { get; set; }

        [JsonPropertyName("sheet_cut_count")]
        public int SheetCutCount { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("vendor_received_at")]
        public DateTime? VendorReceivedAt { get; set; }

        [JsonPropertyName("work_done_at")]
        public DateTime? WorkDoneAt { get; set; }

        [JsonPropertyName("shipped_at")]
        public DateTime? ShippedAt { get; set; }

        [JsonPropertyName("outsource_processing_fee")]
        public decimal? OutsourceProcessingFee { get; set; }

        [JsonPropertyName("work_done_remark")]
        public string WorkDoneRemark { get; set; } = string.Empty;

        [JsonPropertyName("lot_nos")]
        public List<string> LotNos { get; set; } = new();

        [JsonPropertyName("product_names")]
        public List<string> ProductNames { get; set; } = new();

        [JsonPropertyName("items")]
        public List<BohyunOutsourceGroupItemDto> Items { get; set; } = new();
    }

    public class BohyunOutsourceGroupItemDto
    {
        [JsonPropertyName("outsource_work_group_item_id")]
        public long OutsourceWorkGroupItemId { get; set; }

        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("order_no")]
        public string OrderNo { get; set; } = string.Empty;

        [JsonPropertyName("line_no")]
        public int? LineNo { get; set; }

        [JsonPropertyName("product_id")]
        public long? ProductId { get; set; }

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

        [JsonPropertyName("cuts_per_sheet")]
        public int CutsPerSheet { get; set; }

        [JsonPropertyName("expected_output_qty")]
        public int? ExpectedOutputQty { get; set; }

        [JsonPropertyName("actual_output_qty")]
        public int? ActualOutputQty { get; set; }

        [JsonPropertyName("remark")]
        public string Remark { get; set; } = string.Empty;
    }

    public class BohyunOutsourceRowModel : ViewModelBase
    {
        private bool _isChecked;

        public bool IsChecked
        {
            get => _isChecked;
            set => SetProperty(ref _isChecked, value);
        }

        public long OutsourceWorkGroupId { get; set; }
        public long OutsourceWorkInstructionId { get; set; }
        public long? RepresentativeLotId { get; set; }
        public string? RepresentativeProductName { get; set; }

        public string InstructionNo { get; set; } = string.Empty;
        public DateTime? InstructionDate { get; set; }

        public string ProcessType { get; set; } = string.Empty;

        public long PartnerId { get; set; }
        public string PartnerName { get; set; } = string.Empty;

        public string InboundSourceName { get; set; } = string.Empty;

        public bool IsBundle { get; set; }
        public string? GroupSeq { get; set; }

        public int SheetQty { get; set; }
        public int? WorkDoneSheetQty { get; set; }

        public decimal? LengthM { get; set; }
        public int SheetCutCount { get; set; }

        public string Status { get; set; } = string.Empty;

        public DateTime? VendorReceivedAt { get; set; }
        public DateTime? WorkDoneAt { get; set; }
        public DateTime? ShippedAt { get; set; }

        public decimal? OutsourceProcessingFee { get; set; }
        public string WorkDoneRemark { get; set; } = string.Empty;

        public List<string> LotNos { get; set; } = new();
        public List<string> ProductNames { get; set; } = new();

        public List<BohyunOutsourceGroupItemDto> Items { get; set; } = new();

        public string StatusName => Status switch
        {
            "WAITING_INBOUND" => "입고대기",
            "INBOUNDED" => "입고완료",
            "WORK_DONE" => "작업완료",
            "SHIPPED" => "출고완료",
            _ => Status
        };

        public string ProcessTypeName => ProcessType switch
        {
            "CUT" => "재단",
            "PRINT" => "인쇄",
            "DIECUT" => "도무송",
            _ => ProcessType
        };

        public string WorkTypeName => IsBundle ? "묶음" : "개별";

        public string LotNosText => LotNos == null || LotNos.Count == 0
            ? string.Empty
            : string.Join(", ", LotNos);

        public string ProductNamesText => ProductNames == null || ProductNames.Count == 0
            ? RepresentativeProductName ?? string.Empty
            : string.Join(", ", ProductNames.Distinct());

        public bool CanInbound => Status == "WAITING_INBOUND";
        public string ProductCodesText => string.Join(", ", Items.Select(x => x.ProductCode).Where(x => !string.IsNullOrWhiteSpace(x)).Distinct());
        public string MesProductCodesText => string.Join(", ", Items.Select(x => x.MesProductCode).Where(x => !string.IsNullOrWhiteSpace(x)).Distinct());
        public bool CanWorkDone => Status == "INBOUNDED";
        public bool CanShip => Status == "WORK_DONE";

        public static BohyunOutsourceRowModel FromDto(BohyunOutsourceListItemDto dto)
        {
            return new BohyunOutsourceRowModel
            {
                OutsourceWorkGroupId = dto.OutsourceWorkGroupId,
                OutsourceWorkInstructionId = dto.OutsourceWorkInstructionId,
                RepresentativeLotId = dto.RepresentativeLotId,
                RepresentativeProductName = dto.RepresentativeProductName,
                InstructionNo = dto.InstructionNo,
                InstructionDate = dto.InstructionDate,
                ProcessType = dto.ProcessType,
                PartnerId = dto.PartnerId,
                PartnerName = dto.PartnerName,
                InboundSourceName = dto.InboundSourceName,
                IsBundle = dto.IsBundle,
                GroupSeq = dto.GroupSeq,
                SheetQty = dto.SheetQty,
                WorkDoneSheetQty = dto.WorkDoneSheetQty,
                LengthM = dto.LengthM,
                SheetCutCount = dto.SheetCutCount,
                Status = dto.Status,
                VendorReceivedAt = dto.VendorReceivedAt,
                WorkDoneAt = dto.WorkDoneAt,
                ShippedAt = dto.ShippedAt,
                OutsourceProcessingFee = dto.OutsourceProcessingFee,
                WorkDoneRemark = dto.WorkDoneRemark,
                LotNos = dto.LotNos ?? new List<string>(),
                ProductNames = dto.ProductNames ?? new List<string>(),
                Items = dto.Items ?? new List<BohyunOutsourceGroupItemDto>()
            };
        }
    }
}
