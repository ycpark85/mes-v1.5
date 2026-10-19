using Mes.Wpf.Core.Common;
using System;
using System.Collections.ObjectModel;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.Shipments.Dtos
{
    public class ShipmentLineListResponse
    {
        [JsonPropertyName("items")]
        public ObservableCollection<ShipmentLineDto> Items { get; set; } = new();

        [JsonPropertyName("total")]
        public int Total { get; set; }

        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }
    }

    public class ShipmentLineDto : ViewModelBase
    {
        private bool _isSelected;

        [JsonIgnore]
        public bool IsSelected
        {
            get => _isSelected;
            set => SetProperty(ref _isSelected, value);
        }

        [JsonPropertyName("shipment_line_id")]
        public int ShipmentLineId { get; set; }

        [JsonPropertyName("order_line_id")]
        public int OrderLineId { get; set; }

        [JsonPropertyName("order_no")]
        public string OrderNo { get; set; } = string.Empty;

        [JsonPropertyName("partner_name")]
        public string? PartnerName { get; set; }

        [JsonPropertyName("product_id")]
        public int ProductId { get; set; }

        [JsonPropertyName("product_code")]
        public string? ProductCode { get; set; }

        [JsonPropertyName("mes_product_code")]
        public string? MesProductCode { get; set; }

        [JsonPropertyName("product_name")]
        public string? ProductName { get; set; }

        [JsonPropertyName("product_inventory_lot_id")]
        public int? ProductInventoryLotId { get; set; }

        [JsonPropertyName("stock_lot_no")]
        public string? StockLotNoRaw { get; set; }

        [JsonPropertyName("lot_id")]
        public int? LotId { get; set; }

        [JsonPropertyName("lot_no")]
        public string? LotNo { get; set; }

        [JsonPropertyName("inspection_result_id")]
        public int? InspectionResultId { get; set; }

        [JsonPropertyName("source_type")]
        public string SourceType { get; set; } = string.Empty;

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("ship_qty")]
        public int ShipQty { get; set; }

        [JsonPropertyName("shipped_qty")]
        public int ShippedQty { get; set; }

        [JsonPropertyName("ship_target_qty")]
        public int ShipTargetQty { get; set; }

        [JsonPropertyName("already_shipped_qty")]
        public int AlreadyShippedQty { get; set; }

        [JsonPropertyName("remaining_ship_qty")]
        public int RemainingShipQty { get; set; }

        [JsonPropertyName("current_stock_qty")]
        public int CurrentStockQty { get; set; }

        [JsonPropertyName("stock_after_ship_qty")]
        public int StockAfterShipQty { get; set; }

        [JsonIgnore]
        public int ShipmentQtyDisplay => Status == "DONE" ? ShippedQty : ShipQty;

        [JsonPropertyName("memo")]
        public string? Memo { get; set; }

        [JsonPropertyName("created_at")]
        public DateTime CreatedAt { get; set; }

        [JsonPropertyName("shipped_at")]
        public DateTime? ShippedAt { get; set; }

        [JsonIgnore]
        public string SourceTypeDisplay => SourceType switch
        {
            "STOCK" => "기존재고",
            "INSPECTION_RESULT" => "검수분",
            _ => SourceType
        };

        [JsonIgnore]
        public string StockLotNo => SourceType == "STOCK"
            ? StockLotNoRaw ?? LotNo ?? string.Empty
            : string.Empty;

        [JsonIgnore]
        public string ProductionLotNo => SourceType == "INSPECTION_RESULT"
            ? LotNo ?? string.Empty
            : string.Empty;

        [JsonIgnore]
        public string StatusDisplay => Status switch
        {
            "WAITING" => "출하대기",
            "DONE" => "출하완료",
            "CANCELED" => "취소",
            _ => Status
        };

        

    }

    public class ShipmentDisplayItemDto : ViewModelBase
    {
        private bool _isSelected;

        [JsonIgnore]
        public bool IsSelected
        {
            get => _isSelected;
            set => SetProperty(ref _isSelected, value);
        }

        [JsonIgnore]
        public ObservableCollection<ShipmentLineDto> Lines { get; set; } = new();

        public int OrderLineId { get; set; }

        public string OrderNo { get; set; } = string.Empty;

        public string? PartnerName { get; set; }

        public string? ProductCode { get; set; }

        public string? MesProductCode { get; set; }

        public string? ProductName { get; set; }

        public string Status { get; set; } = string.Empty;

        public int StockShipQty { get; set; }

        public int ProductionShipQty { get; set; }

        public int ShipQty => StockShipQty + ProductionShipQty;

        public string StockLotNos { get; set; } = string.Empty;

        public string ProductionLotNos { get; set; } = string.Empty;

        public DateTime? ShippedDate { get; set; }

        public string StatusDisplay => Status switch
        {
            "WAITING" => "출하대기",
            "DONE" => "출하완료",
            "CANCELED" => "취소",
            _ => Status
        };

        [JsonIgnore]
        public long? FirstStockLotId => Lines
            .FirstOrDefault(x => x.SourceType == "STOCK" && x.LotId.HasValue)
            ?.LotId;

        [JsonIgnore]
        public long? FirstProductionLotId => Lines
            .FirstOrDefault(x => x.SourceType == "INSPECTION_RESULT" && x.LotId.HasValue)
            ?.LotId;
    }


    public class ShipmentConfirmRequest
    {
        [JsonPropertyName("shipment_line_ids")]
        public ObservableCollection<int> ShipmentLineIds { get; set; } = new();
    }

    public class ShipmentConfirmResponse
    {
        [JsonPropertyName("confirmed_count")]
        public int ConfirmedCount { get; set; }

        [JsonPropertyName("confirmed_shipment_line_ids")]
        public ObservableCollection<int> ConfirmedShipmentLineIds { get; set; } = new();
    }
}
