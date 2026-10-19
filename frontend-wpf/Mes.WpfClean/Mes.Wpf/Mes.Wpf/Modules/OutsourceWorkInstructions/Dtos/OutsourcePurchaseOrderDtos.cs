using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OutsourceWorkInstructions.Dtos
{
    public sealed class OutsourcePurchaseOrderCreateRequest
    {
        [JsonPropertyName("purchase_order_date")]
        public string PurchaseOrderDate { get; set; } = string.Empty;

        [JsonPropertyName("due_date")]
        public string? DueDate { get; set; }

        [JsonPropertyName("process_type")]
        public string ProcessType { get; set; } = string.Empty;

        [JsonPropertyName("outsource_partner_id")]
        public long OutsourcePartnerId { get; set; }

        [JsonPropertyName("inbound_partner_id")]
        public long? InboundPartnerId { get; set; }

        [JsonPropertyName("work_description")]
        public string? WorkDescription { get; set; }

        [JsonPropertyName("remark")]
        public string? Remark { get; set; }

        [JsonPropertyName("qty")]
        public int Qty { get; set; }

        [JsonPropertyName("unit_price")]
        public decimal? UnitPrice { get; set; }

        [JsonPropertyName("supply_amount")]
        public decimal? SupplyAmount { get; set; }

        [JsonPropertyName("vat_amount")]
        public decimal? VatAmount { get; set; }

        [JsonPropertyName("total_amount")]
        public decimal? TotalAmount { get; set; }

        [JsonPropertyName("items")]
        public List<OutsourcePurchaseOrderCreateItemRequest> Items { get; set; } = new();

        [JsonPropertyName("form_snapshot")]
        public object? FormSnapshot { get; set; }
    }

    public sealed class OutsourcePurchaseOrderCreateItemRequest
    {
        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("outsource_work_instruction_id")]
        public long? OutsourceWorkInstructionId { get; set; }

        [JsonPropertyName("item_seq")]
        public int ItemSeq { get; set; }

        [JsonPropertyName("qty")]
        public int Qty { get; set; }
    }

    public sealed class OutsourcePurchaseOrderResponse
    {
        [JsonPropertyName("outsource_purchase_order_id")]
        public long OutsourcePurchaseOrderId { get; set; }

        [JsonPropertyName("purchase_order_no")]
        public string PurchaseOrderNo { get; set; } = string.Empty;

        [JsonPropertyName("purchase_order_date")]
        public string PurchaseOrderDate { get; set; } = string.Empty;

        [JsonPropertyName("due_date")]
        public string? DueDate { get; set; }

        [JsonPropertyName("process_type")]
        public string ProcessType { get; set; } = string.Empty;

        [JsonPropertyName("outsource_partner_id")]
        public long OutsourcePartnerId { get; set; }

        [JsonPropertyName("inbound_partner_id")]
        public long? InboundPartnerId { get; set; }

        [JsonPropertyName("work_description")]
        public string? WorkDescription { get; set; }

        [JsonPropertyName("remark")]
        public string? Remark { get; set; }

        [JsonPropertyName("qty")]
        public int Qty { get; set; }

        [JsonPropertyName("unit_price")]
        public decimal? UnitPrice { get; set; }

        [JsonPropertyName("supply_amount")]
        public decimal? SupplyAmount { get; set; }

        [JsonPropertyName("vat_amount")]
        public decimal? VatAmount { get; set; }

        [JsonPropertyName("total_amount")]
        public decimal? TotalAmount { get; set; }

        [JsonPropertyName("outsource_partner_name")]
        public string? OutsourcePartnerName { get; set; }

        [JsonPropertyName("inbound_partner_name")]
        public string? InboundPartnerName { get; set; }

        [JsonPropertyName("items")]
        public List<OutsourcePurchaseOrderItemResponse> Items { get; set; } = new();
    }

    public sealed class OutsourcePurchaseOrderItemResponse
    {
        [JsonPropertyName("outsource_purchase_order_item_id")]
        public long OutsourcePurchaseOrderItemId { get; set; }

        [JsonPropertyName("outsource_purchase_order_id")]
        public long OutsourcePurchaseOrderId { get; set; }

        [JsonPropertyName("lot_id")]
        public long LotId { get; set; }

        [JsonPropertyName("outsource_work_instruction_id")]
        public long? OutsourceWorkInstructionId { get; set; }

        [JsonPropertyName("item_seq")]
        public int ItemSeq { get; set; }

        [JsonPropertyName("qty")]
        public int Qty { get; set; }

        [JsonPropertyName("status")]
        public string? Status { get; set; }

        [JsonPropertyName("vendor_received_at")]
        public string? VendorReceivedAt { get; set; }

        [JsonPropertyName("work_done_at")]
        public string? WorkDoneAt { get; set; }

        [JsonPropertyName("shipped_at")]
        public string? ShippedAt { get; set; }

        [JsonPropertyName("work_done_qty")]
        public int? WorkDoneQty { get; set; }

        [JsonPropertyName("bad_qty")]
        public int? BadQty { get; set; }

        [JsonPropertyName("work_done_remark")]
        public string? WorkDoneRemark { get; set; }

        [JsonPropertyName("lot_no")]
        public string? LotNo { get; set; }

        [JsonPropertyName("order_no")]
        public string? OrderNo { get; set; }

        [JsonPropertyName("line_no")]
        public int? LineNo { get; set; }

        [JsonPropertyName("product_code")]
        public string? ProductCode { get; set; }

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("lot_qty")]
        public int? LotQty { get; set; }
    }

    public sealed class OutsourcePurchaseOrderCutSnapshotRequest
    {
        [JsonPropertyName("request_company_name")]
        public string? RequestCompanyName { get; set; }

        [JsonPropertyName("requester_name")]
        public string? RequesterName { get; set; }

        [JsonPropertyName("purchase_order_date")]
        public string? PurchaseOrderDate { get; set; }

        [JsonPropertyName("raw_material_inbound_text")]
        public string? RawMaterialInboundText { get; set; }

        [JsonPropertyName("stock_500_width_text")]
        public string? Stock500WidthText { get; set; }

        [JsonPropertyName("stock_600_width_text")]
        public string? Stock600WidthText { get; set; }

        [JsonPropertyName("stock_600_tpt0268_text")]
        public string? Stock600Tpt0268Text { get; set; }

        [JsonPropertyName("remark")]
        public string? Remark { get; set; }

        [JsonPropertyName("rows")]
        public List<OutsourcePurchaseOrderCutSnapshotRowRequest> Rows { get; set; } = new();
    }

    public sealed class OutsourcePurchaseOrderCutSnapshotRowRequest
    {
        [JsonPropertyName("no")]
        public int No { get; set; }

        [JsonPropertyName("raw_material_text")]
        public string? RawMaterialText { get; set; }

        [JsonPropertyName("length_m_text")]
        public string? LengthMText { get; set; }

        [JsonPropertyName("inbound_place_text")]
        public string? InboundPlaceText { get; set; }

        [JsonPropertyName("cut_spec_text")]
        public string? CutSpecText { get; set; }

        [JsonPropertyName("sheet_qty_text")]
        public string? SheetQtyText { get; set; }
    }

    public sealed class OutsourcePurchaseOrderPrintSnapshotRequest
    {
        [JsonPropertyName("vendor_name")]
        public string? VendorName { get; set; }

        [JsonPropertyName("request_company_name")]
        public string? RequestCompanyName { get; set; }

        [JsonPropertyName("requester_name")]
        public string? RequesterName { get; set; }

        [JsonPropertyName("purchase_order_date")]
        public string? PurchaseOrderDate { get; set; }

        [JsonPropertyName("footer_remark")]
        public string? FooterRemark { get; set; }

        [JsonPropertyName("rows")]
        public List<OutsourcePurchaseOrderPrintSnapshotRowRequest> Rows { get; set; } = new();
    }

    public sealed class OutsourcePurchaseOrderPrintSnapshotRowRequest
    {
        [JsonPropertyName("no")]
        public int No { get; set; }

        [JsonPropertyName("customer_name")]
        public string? CustomerName { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("material_spec")]
        public string? MaterialSpec { get; set; }

        [JsonPropertyName("print_sheet_qty")]
        public string? PrintSheetQty { get; set; }

        [JsonPropertyName("sample")]
        public string? Sample { get; set; }

        [JsonPropertyName("plate_count")]
        public string? PlateCount { get; set; }

        [JsonPropertyName("color_name")]
        public string? ColorName { get; set; }

        [JsonPropertyName("material_type")]
        public string? MaterialType { get; set; }

        [JsonPropertyName("remark")]
        public string? Remark { get; set; }
    }

    public sealed class OutsourcePurchaseOrderListDto
    {
        [JsonPropertyName("items")]
        public List<OutsourcePurchaseOrderListItemDto> Items { get; set; } = new();

        [JsonPropertyName("total_count")]
        public int TotalCount { get; set; }

        [JsonPropertyName("page")]
        public int Page { get; set; } = 1;

        [JsonPropertyName("size")]
        public int Size { get; set; } = 100;
    }

    public sealed class OutsourcePurchaseOrderListItemDto
    {
        [JsonPropertyName("outsource_purchase_order_id")]
        public long OutsourcePurchaseOrderId { get; set; }

        [JsonPropertyName("purchase_order_no")]
        public string PurchaseOrderNo { get; set; } = string.Empty;

        [JsonPropertyName("purchase_order_date")]
        public string PurchaseOrderDate { get; set; } = string.Empty;

        [JsonPropertyName("process_type")]
        public string ProcessType { get; set; } = string.Empty;

        [JsonPropertyName("outsource_partner_id")]
        public long OutsourcePartnerId { get; set; }

        [JsonPropertyName("outsource_partner_name")]
        public string? OutsourcePartnerName { get; set; }

        [JsonPropertyName("qty")]
        public int Qty { get; set; }

        [JsonPropertyName("remark")]
        public string? Remark { get; set; }
    }
}
