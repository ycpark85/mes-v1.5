using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.OrderLineList.Dtos
{
    public class OrderLineListResponse
    {
        [JsonPropertyName("items")]
        public List<OrderLineListItemDto> Items { get; set; } = new();

        [JsonPropertyName("meta")]
        public OrderLineListMetaDto Meta { get; set; } = new();

        [JsonPropertyName("queue_counts")]
        public Dictionary<string, int>? QueueCounts { get; set; }
    }

    public class OrderLineListMetaDto
    {
        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }

        [JsonPropertyName("total")]
        public int Total { get; set; }
    }
}
