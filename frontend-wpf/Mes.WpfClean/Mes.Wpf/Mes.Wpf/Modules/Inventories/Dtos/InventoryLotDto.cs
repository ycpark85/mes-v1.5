using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.Inventories.Dtos
{
    public class InventoryLotDto : ViewModelBase
    {
        private long _currentQty;
        private DateTimeOffset? _updatedAt;
        [JsonPropertyName("product_inventory_lot_id")]
        public long ProductInventoryLotId { get; set; }
        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }
        [JsonPropertyName("lot_no")]
        public string LotNo { get; set; } = string.Empty;
        [JsonPropertyName("current_qty")]
        public long CurrentQty { get => _currentQty; set => SetProperty(ref _currentQty, value); }
        [JsonPropertyName("updated_at")]
        public DateTimeOffset? UpdatedAt
        {
            get => _updatedAt;
            set
            {
                if (SetProperty(ref _updatedAt, value)) OnPropertyChanged(nameof(LocalUpdatedAt));
            }
        }
        public DateTime? LocalUpdatedAt => UpdatedAt?.ToOffset(TimeSpan.FromHours(9)).DateTime;
    }

    public class InventoryLotListDto
    {
        [JsonPropertyName("items")]
        public List<InventoryLotDto> Items { get; set; } = new();
        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }
        [JsonPropertyName("product_current_qty")]
        public long ProductCurrentQty { get; set; }
        [JsonPropertyName("product_updated_at")]
        public DateTimeOffset? ProductUpdatedAt { get; set; }
        [JsonPropertyName("total_qty")]
        public long TotalQty { get; set; }
        [JsonPropertyName("total")]
        public int Total { get; set; }
        [JsonPropertyName("page")]
        public int Page { get; set; }
        [JsonPropertyName("size")]
        public int Size { get; set; }
        [JsonPropertyName("stock_warning")]
        public string? StockWarning { get; set; }
    }
}
