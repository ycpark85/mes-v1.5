using System;
using System.Collections.ObjectModel;
using System.Text.Json.Serialization;
using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.InspectionSchedules.Dtos
{
    public class InspectionResultResponse
    {
        [JsonPropertyName("result")]
        public InspectionResultDto? Result { get; set; }

        [JsonPropertyName("schedule_status")]
        public string? ScheduleStatus { get; set; }

        [JsonPropertyName("inspection_round")]
        public int InspectionRound { get; set; }

        [JsonPropertyName("inspection_round_count")]
        public int InspectionRoundCount { get; set; }

        [JsonPropertyName("rounds")]
        public ObservableCollection<InspectionRoundSummaryDto> Rounds { get; set; } = new();

        [JsonPropertyName("accumulated")]
        public InspectionAccumulatedSummaryDto? Accumulated { get; set; }

        [JsonPropertyName("inventory")]
        public InspectionInventorySummaryDto? Inventory { get; set; }
    }

    public class InspectionAccumulatedSummaryDto
    {
        [JsonPropertyName("good_qty")]
        public int GoodQty { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("defect_ship_qty")]
        public int DefectShipQty { get; set; }

        [JsonPropertyName("inspected_qty")]
        public int InspectedQty { get; set; }

        [JsonPropertyName("uninspected_qty")]
        public int UninspectedQty { get; set; }

        [JsonPropertyName("received_qty")]
        public int ReceivedQty { get; set; }

        [JsonPropertyName("discard_qty")]
        public int DiscardQty { get; set; }
    }

    public class InspectionInventorySummaryDto
    {
        [JsonPropertyName("view_mode")]
        public string? ViewMode { get; set; }

        [JsonPropertyName("stock_as_of")]
        public DateTimeOffset? StockAsOf { get; set; }

        [JsonPropertyName("stock_lots")]
        public ObservableCollection<InspectionStockLotDto>? StockLots { get; set; }

        [JsonPropertyName("product_id")]
        public int ProductId { get; set; }

        [JsonPropertyName("order_line_id")]
        public int OrderLineId { get; set; }

        [JsonPropertyName("physical_stock_qty")]
        public int PhysicalStockQty { get; set; }

        [JsonPropertyName("stock_error")]
        public string? StockError { get; set; }

        [JsonPropertyName("settlement_error")]
        public string? SettlementError { get; set; }

        [JsonPropertyName("current_stock_qty")]
        public int CurrentStockQty { get; set; }

        [JsonPropertyName("order_qty")]
        public int OrderQty { get; set; }

        [JsonPropertyName("ship_target_qty")]
        public int ShipTargetQty { get; set; }

        [JsonPropertyName("prior_shipped_qty")]
        public int PriorShippedQty { get; set; }

        [JsonPropertyName("current_result_shipped_qty")]
        public int CurrentResultShippedQty { get; set; }

        [JsonPropertyName("remaining_before_current_result_qty")]
        public int RemainingBeforeCurrentResultQty { get; set; }

        [JsonPropertyName("prior_unsettled_sellable_qty")]
        public int PriorUnsettledSellableQty { get; set; }

        [JsonPropertyName("current_result_stock_ship_qty")]
        public int CurrentResultStockShipQty { get; set; }

        [JsonPropertyName("current_result_result_ship_qty")]
        public int CurrentResultResultShipQty { get; set; }

        [JsonPropertyName("current_result_stock_in_qty")]
        public int CurrentResultStockInQty { get; set; }

        [JsonPropertyName("current_result_discard_qty")]
        public int CurrentResultDiscardQty { get; set; }
    }

    public class InspectionResultDto
    {
        [JsonPropertyName("inspection_result_id")]
        public int InspectionResultId { get; set; }

        [JsonPropertyName("inspection_schedule_id")]
        public int InspectionScheduleId { get; set; }

        [JsonPropertyName("good_qty")]
        public int GoodQty { get; set; }

        [JsonPropertyName("defect_ship_qty")]
        public int DefectShipQty { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("uninspected_qty")]
        public int UninspectedQty { get; set; }

        [JsonPropertyName("received_qty")]
        public int ReceivedQty { get; set; }

        [JsonPropertyName("discard_qty")]
        public int DiscardQty { get; set; }

        [JsonPropertyName("is_partial")]
        public bool IsPartial { get; set; }

        [JsonPropertyName("next_inspection_date")]
        public DateTime? NextInspectionDate { get; set; }

        [JsonPropertyName("shortage_reason")]
        public string? ShortageReason { get; set; }

        [JsonPropertyName("partial_reason")]
        public string? PartialReason { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("updated_at")]
        public DateTimeOffset UpdatedAt { get; set; }

        [JsonPropertyName("settled_at")]
        public DateTimeOffset? SettledAt { get; set; }

        [JsonPropertyName("settled_by")]
        public string? SettledBy { get; set; }

        [JsonPropertyName("defects")]
        public ObservableCollection<InspectionResultDefectDto> Defects { get; set; } = new();
    }

    public class InspectionResultDefectDto
    {
        [JsonPropertyName("inspection_defect_id")]
        public int InspectionDefectId { get; set; }

        [JsonPropertyName("defect_type_id")]
        public int DefectTypeId { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("disposition")]
        public string? Disposition { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("attachments")]
        public ObservableCollection<DefectAttachmentOutDto> Attachments { get; set; } = new();
    }

    public class DefectAttachmentOutDto
    {
        [JsonPropertyName("inspection_defect_attachment_id")]
        public int InspectionDefectAttachmentId { get; set; }

        [JsonPropertyName("file_uri")]
        public string FileUri { get; set; } = string.Empty;

        [JsonPropertyName("file_name")]
        public string? FileName { get; set; }

        [JsonPropertyName("mime_type")]
        public string? MimeType { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("created_at")]
        public DateTime CreatedAt { get; set; }
    }

    public class DefectAttachmentUploadResponse
    {
        [JsonPropertyName("file_uri")]
        public string FileUri { get; set; } = string.Empty;

        [JsonPropertyName("file_name")]
        public string FileName { get; set; } = string.Empty;

        [JsonPropertyName("mime_type")]
        public string? MimeType { get; set; }

        [JsonPropertyName("file_size")]
        public int FileSize { get; set; }
    }

    public class InspectionResultUpsertRequest
    {
        [JsonPropertyName("quantity_rule_version")]
        public int QuantityRuleVersion { get; set; } = Mes.Wpf.Core.Configuration.ClientRuntime.InspectionQuantityRuleVersion;
        [JsonPropertyName("good_qty")]
        public int GoodQty { get; set; }

        [JsonPropertyName("defect_ship_qty")]
        public int DefectShipQty { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("uninspected_qty")]
        public int UninspectedQty { get; set; }

        [JsonPropertyName("stock_ship_qty")]
        public int StockShipQty { get; set; }

        [JsonPropertyName("result_ship_qty")]
        public int ResultShipQty { get; set; }

        [JsonPropertyName("stock_in_qty")]
        public int StockInQty { get; set; }

        [JsonPropertyName("discard_qty")]
        public int DiscardQty { get; set; }

        [JsonPropertyName("is_partial")]
        public bool IsPartial { get; set; }

        [JsonPropertyName("next_inspection_date")]
        public DateTime? NextInspectionDate { get; set; }

        [JsonPropertyName("shortage_reason")]
        public string? ShortageReason { get; set; }

        [JsonPropertyName("partial_reason")]
        public string? PartialReason { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("expected_updated_at")]
        public DateTimeOffset? ExpectedUpdatedAt { get; set; }

        [JsonPropertyName("defects")]
        public ObservableCollection<InspectionResultDefectRequest> Defects { get; set; } = new();
    }

    public class InspectionResultDefectRequest
    {
        [JsonPropertyName("defect_type_id")]
        public int DefectTypeId { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("disposition")]
        public string Disposition { get; set; } = "NOT_SHIPPABLE";

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("attachments")]
        public ObservableCollection<DefectAttachmentRequest> Attachments { get; set; } = new();
    }

    public class DefectAttachmentRequest
    {
        [JsonPropertyName("file_uri")]
        public string FileUri { get; set; } = string.Empty;

        [JsonPropertyName("file_name")]
        public string? FileName { get; set; }

        [JsonPropertyName("mime_type")]
        public string? MimeType { get; set; }

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }
    }

    public class InspectionResultUpsertResponse
    {
        [JsonPropertyName("schedule_status")]
        public string? ScheduleStatus { get; set; }

        [JsonPropertyName("created_next_schedule_id")]
        public int? CreatedNextScheduleId { get; set; }
    }

    public class InspectionResultDefectEditModel : ViewModelBase
    {
        private int? _defectTypeId;
        private int _defectQty;
        private string _disposition = "NOT_SHIPPABLE";
        private string _defectCode = string.Empty;
        private string _category1Name = string.Empty;
        private string _category2Name = string.Empty;
        private string _defectTypeMemo = string.Empty;
        private ObservableCollection<DefectAttachmentEditModel> _attachments = new();

        public int? DefectTypeId
        {
            get => _defectTypeId;
            set => SetProperty(ref _defectTypeId, value);
        }

        public int DefectQty
        {
            get => _defectQty;
            set => SetProperty(ref _defectQty, value);
        }

        public string Disposition
        {
            get => _disposition;
            set => SetProperty(ref _disposition, value);
        }

        public string DefectCode
        {
            get => _defectCode;
            set => SetProperty(ref _defectCode, value);
        }

        public string Category1Name
        {
            get => _category1Name;
            set => SetProperty(ref _category1Name, value);
        }

        public string Category2Name
        {
            get => _category2Name;
            set => SetProperty(ref _category2Name, value);
        }

        public string DefectTypeMemo
        {
            get => _defectTypeMemo;
            set => SetProperty(ref _defectTypeMemo, value);
        }

        public string Memo
        {
            get => DefectTypeMemo;
            set => DefectTypeMemo = value;
        }

        public ObservableCollection<DefectAttachmentEditModel> Attachments
        {
            get => _attachments;
            set => SetProperty(ref _attachments, value);
        }

        public void Clear()
        {
            DefectTypeId = null;
            DefectQty = 0;
            Disposition = "NOT_SHIPPABLE";
            DefectCode = string.Empty;
            Category1Name = string.Empty;
            Category2Name = string.Empty;
            DefectTypeMemo = string.Empty;
            Attachments.Clear();
        }
    }

    public class DefectAttachmentEditModel : ViewModelBase
    {
        private int? _inspectionDefectAttachmentId;
        private string _fileUri = string.Empty;
        private string _fileName = string.Empty;
        private string _mimeType = string.Empty;
        private string _memo = string.Empty;
        private string _localFilePath = string.Empty;

        public int? InspectionDefectAttachmentId
        {
            get => _inspectionDefectAttachmentId;
            set => SetProperty(ref _inspectionDefectAttachmentId, value);
        }

        public string FileUri
        {
            get => _fileUri;
            set => SetProperty(ref _fileUri, value);
        }

        public string FileName
        {
            get => _fileName;
            set => SetProperty(ref _fileName, value);
        }

        public string MimeType
        {
            get => _mimeType;
            set => SetProperty(ref _mimeType, value);
        }

        public string Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public string LocalFilePath
        {
            get => _localFilePath;
            set => SetProperty(ref _localFilePath, value);
        }
    }


    public class InspectionRoundSummaryDto
    {
        [JsonPropertyName("inspection_result_id")]
        public long InspectionResultId { get; set; }

        [JsonPropertyName("inspection_schedule_id")]
        public long InspectionScheduleId { get; set; }

        [JsonPropertyName("inspection_date")]
        public DateTime InspectionDate { get; set; }

        [JsonPropertyName("schedule_status")]
        public string ScheduleStatus { get; set; } = string.Empty;

        [JsonPropertyName("inspection_round")]
        public int InspectionRound { get; set; }

        [JsonPropertyName("is_partial")]
        public bool IsPartial { get; set; }

        [JsonPropertyName("next_inspection_date")]
        public DateTime? NextInspectionDate { get; set; }

        [JsonPropertyName("shortage_reason")]
        public string? ShortageReason { get; set; }

        [JsonPropertyName("partial_reason")]
        public string? PartialReason { get; set; }

        [JsonPropertyName("good_qty")]
        public int GoodQty { get; set; }

        [JsonPropertyName("defect_ship_qty")]
        public int DefectShipQty { get; set; }

        [JsonPropertyName("defect_qty")]
        public int DefectQty { get; set; }

        [JsonPropertyName("received_qty")]
        public int ReceivedQty { get; set; }

        [JsonIgnore]
        public string ResultTypeDisplay => IsPartial ? "분할" : "최종";
    }
    public class InspectionStockLotDto : ViewModelBase
    {
        private int _allocatedShipQty;

        [JsonPropertyName("product_inventory_lot_id")]
        public long ProductInventoryLotId { get; set; }

        [JsonPropertyName("production_lot_id")]
        public long? ProductionLotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;

        [JsonPropertyName("physical_qty")]
        public int PhysicalQty { get; set; }

        [JsonPropertyName("reserved_qty")]
        public int ReservedQty { get; set; }

        [JsonPropertyName("other_reserved_qty")]
        public int OtherReservedQty { get; set; }

        [JsonPropertyName("stock_qty")]
        public int StockQty { get; set; }

        [JsonPropertyName("allocated_ship_qty")]
        public int AllocatedShipQty
        {
            get => _allocatedShipQty;
            set => SetProperty(ref _allocatedShipQty, value);
        }

        [JsonPropertyName("created_date")]
        public DateTime? CreatedDate { get; set; }
    }
}
