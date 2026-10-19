using Mes.Wpf.Core.Common;
using System;
using System.Collections.ObjectModel;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OrderLines.Dtos
{
    public class OrderLineBulkImportRowDto : ViewModelBase
    {
        private int _rowNumber;
        private string _erpOrderNo = string.Empty;
        private string _productCode = string.Empty;
        private string _partnerName = string.Empty;
        private string _erpProductDisplayName = string.Empty;
        private string _orderQtyText = string.Empty;
        private string _dueDateText = string.Empty;
        private string? _remark;

        [JsonPropertyName("row_number")]
        public int RowNumber
        {
            get => _rowNumber;
            set => SetProperty(ref _rowNumber, value);
        }

        [JsonPropertyName("erp_order_no")]
        public string ErpOrderNo
        {
            get => _erpOrderNo;
            set => SetProperty(ref _erpOrderNo, value);
        }

        [JsonPropertyName("product_code")]
        public string ProductCode
        {
            get => _productCode;
            set => SetProperty(ref _productCode, value);
        }

        [JsonPropertyName("partner_name")]
        public string PartnerName
        {
            get => _partnerName;
            set => SetProperty(ref _partnerName, value);
        }

        [JsonPropertyName("erp_product_display_name")]
        public string ErpProductDisplayName
        {
            get => _erpProductDisplayName;
            set => SetProperty(ref _erpProductDisplayName, value);
        }

        [JsonPropertyName("order_qty_text")]
        public string OrderQtyText
        {
            get => _orderQtyText;
            set => SetProperty(ref _orderQtyText, value);
        }

        [JsonPropertyName("due_date_text")]
        public string DueDateText
        {
            get => _dueDateText;
            set => SetProperty(ref _dueDateText, value);
        }

        [JsonPropertyName("remark")]
        public string? Remark
        {
            get => _remark;
            set => SetProperty(ref _remark, value);
        }

        public void Clear()
        {
            RowNumber = 0;
            ErpOrderNo = string.Empty;
            ProductCode = string.Empty;
            PartnerName = string.Empty;
            ErpProductDisplayName = string.Empty;
            OrderQtyText = string.Empty;
            DueDateText = string.Empty;
            Remark = null;
        }
    }

    public class OrderLineBulkValidateRequest
    {
        [JsonPropertyName("items")]
        public ObservableCollection<OrderLineBulkImportRowDto> Items { get; set; } = new();
    }

    public class OrderLineBulkValidateMessageDto
    {
        [JsonPropertyName("field")]
        public string Field { get; set; } = string.Empty;

        [JsonPropertyName("level")]
        public string Level { get; set; } = string.Empty;

        [JsonPropertyName("message")]
        public string Message { get; set; } = string.Empty;
    }

    public class OrderLineBulkValidateRowDto : ViewModelBase
    {
        private bool _applyProductNameChange;

        [JsonPropertyName("row_number")]
        public int RowNumber { get; set; }

        [JsonPropertyName("erp_order_no")]
        public string ErpOrderNo { get; set; } = string.Empty;

        [JsonPropertyName("line_no")]
        public int? LineNo { get; set; }

        [JsonPropertyName("order_date")]
        public DateTime? OrderDate { get; set; }

        [JsonPropertyName("due_date")]
        public DateTime? DueDate { get; set; }

        [JsonPropertyName("partner_id")]
        public long? PartnerId { get; set; }

        [JsonPropertyName("partner_name")]
        public string? PartnerName { get; set; }

        [JsonPropertyName("product_id")]
        public long? ProductId { get; set; }

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("erp_product_display_name")]
        public string ErpProductDisplayName { get; set; } = string.Empty;

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }
        [JsonPropertyName("drawing_no")]
        public string? DrawingNo { get; set; }
        [JsonPropertyName("mapping_id")]
        public long? MappingId { get; set; }
        [JsonPropertyName("is_unprinted_managed")]
        public bool IsUnprintedManaged { get; set; }

        [JsonPropertyName("mes_product_display_name")]
        public string? MesProductDisplayName { get; set; }

        [JsonPropertyName("parsed_product_name")]
        public string? ParsedProductName { get; set; }

        [JsonPropertyName("parsed_product_spec")]
        public string? ParsedProductSpec { get; set; }

        [JsonPropertyName("order_qty")]
        public int? OrderQty { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("product_name_mismatch")]
        public bool ProductNameMismatch { get; set; }

        [JsonPropertyName("can_apply_product_name_change")]
        public bool CanApplyProductNameChange { get; set; }

        [JsonPropertyName("apply_product_name_change")]
        public bool ApplyProductNameChange
        {
            get => _applyProductNameChange;
            set => SetProperty(ref _applyProductNameChange, value);
        }

        [JsonPropertyName("messages")]
        public ObservableCollection<OrderLineBulkValidateMessageDto> Messages { get; set; } = new();

        public string MessageSummary => string.Join(Environment.NewLine, Messages.Select(x => $"[{x.Level}] {x.Message}"));
    }

    public class OrderLineBulkValidateGroupDto
    {
        [JsonPropertyName("erp_order_no")]
        public string ErpOrderNo { get; set; } = string.Empty;

        [JsonPropertyName("order_date")]
        public DateTime? OrderDate { get; set; }

        [JsonPropertyName("due_date")]
        public DateTime? DueDate { get; set; }

        [JsonPropertyName("partner_id")]
        public long? PartnerId { get; set; }

        [JsonPropertyName("partner_name")]
        public string? PartnerName { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("can_commit")]
        public bool CanCommit { get; set; }

        [JsonPropertyName("messages")]
        public ObservableCollection<OrderLineBulkValidateMessageDto> Messages { get; set; } = new();

        [JsonPropertyName("rows")]
        public ObservableCollection<OrderLineBulkValidateRowDto> Rows { get; set; } = new();
    }

    public class OrderLineBulkValidateResultDto
    {
        [JsonPropertyName("total_row_count")]
        public int TotalRowCount { get; set; }

        [JsonPropertyName("ready_row_count")]
        public int ReadyRowCount { get; set; }

        [JsonPropertyName("review_row_count")]
        public int ReviewRowCount { get; set; }

        [JsonPropertyName("error_row_count")]
        public int ErrorRowCount { get; set; }

        [JsonPropertyName("duplicate_group_count")]
        public int DuplicateGroupCount { get; set; }

        [JsonPropertyName("groups")]
        public ObservableCollection<OrderLineBulkValidateGroupDto> Groups { get; set; } = new();
    }

    public class OrderLineBulkCommitRowChoiceDto
    {
        [JsonPropertyName("expected_product_id")]
        public long? ExpectedProductId { get; set; }
        [JsonPropertyName("expected_mapping_id")]
        public long? ExpectedMappingId { get; set; }
        [JsonPropertyName("row_number")]
        public int RowNumber { get; set; }

        [JsonPropertyName("apply_product_name_change")]
        public bool ApplyProductNameChange { get; set; }
    }

    public class OrderLineBulkCommitRequest
    {
        [JsonPropertyName("items")]
        public ObservableCollection<OrderLineBulkImportRowDto> Items { get; set; } = new();

        [JsonPropertyName("row_choices")]
        public ObservableCollection<OrderLineBulkCommitRowChoiceDto> RowChoices { get; set; } = new();
    }

    public class OrderLineBulkCommitGroupResultDto
    {
        [JsonPropertyName("erp_order_no")]
        public string ErpOrderNo { get; set; } = string.Empty;

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("message")]
        public string? Message { get; set; }

        [JsonPropertyName("created_order_line_ids")]
        public ObservableCollection<long> CreatedOrderLineIds { get; set; } = new();
    }

    public class OrderLineBulkCommitResultDto
    {
        [JsonPropertyName("total_group_count")]
        public int TotalGroupCount { get; set; }

        [JsonPropertyName("success_group_count")]
        public int SuccessGroupCount { get; set; }

        [JsonPropertyName("failure_group_count")]
        public int FailureGroupCount { get; set; }

        [JsonPropertyName("groups")]
        public ObservableCollection<OrderLineBulkCommitGroupResultDto> Groups { get; set; } = new();
    }
}