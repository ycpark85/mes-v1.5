using System;
using System.Text.Json.Serialization;
using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.Inventories.Dtos
{
    public class InventoryDto : ViewModelBase
    {
        private long _currentQty;
        private DateTimeOffset? _updatedAt;
        [JsonPropertyName("product_id")]
        public long ProductId { get; set; }

        [JsonPropertyName("product_code")]
        public string ProductCode { get; set; } = string.Empty;

        [JsonPropertyName("product_name")]
        public string ProductName { get; set; } = string.Empty;

        [JsonPropertyName("uom")]
        public string Uom { get; set; } = string.Empty;

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
}
