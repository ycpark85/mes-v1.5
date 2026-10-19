using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.ProductionDaily.Dtos
{
    public class ProductionDailyListDto
    {
        [JsonPropertyName("items")]
        public List<ProductionDailyRowDto> Items { get; set; } = new();

        [JsonPropertyName("total")]
        public int Total { get; set; }

        [JsonPropertyName("page")]
        public int Page { get; set; }

        [JsonPropertyName("size")]
        public int Size { get; set; }
    }

    public class ProductionDailyRowDto
    {
        [JsonPropertyName("order_line_id")]
        public long OrderLineId { get; set; }

        [JsonPropertyName("order_no")]
        public string OrderNo { get; set; } = string.Empty;

        [JsonPropertyName("line_no")]
        public int LineNo { get; set; }

        [JsonPropertyName("due_date")]
        public DateTime DueDate { get; set; }

        [JsonPropertyName("due_slack_text")]
        public string DueSlackText { get; set; } = string.Empty;

        [JsonPropertyName("due_slack_level")]
        public string DueSlackLevel { get; set; } = string.Empty;

        [JsonPropertyName("due_days")]
        public int DueDays { get; set; }

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

        [JsonPropertyName("available_inventory_qty")]
        public int AvailableInventoryQty { get; set; }

        [JsonPropertyName("production_qty")]
        public int ProductionQty { get; set; }

        [JsonPropertyName("work_type")]
        public string WorkType { get; set; } = string.Empty;

        [JsonPropertyName("work_type_display")]
        public string WorkTypeDisplay { get; set; } = string.Empty;

        [JsonPropertyName("current_process")]
        public string CurrentProcess { get; set; } = string.Empty;

        [JsonPropertyName("current_process_display")]
        public string CurrentProcessDisplay { get; set; } = string.Empty;

        [JsonPropertyName("progress_rate")]
        public int ProgressRate { get; set; }

        [JsonPropertyName("lot_count")]
        public int LotCount { get; set; }

        [JsonPropertyName("target_lot_count")]
        public int TargetLotCount { get; set; }

        [JsonPropertyName("completed_lot_count")]
        public int CompletedLotCount { get; set; }

        [JsonPropertyName("lot_nos")]
        public List<string> LotNos { get; set; } = new();

        public string ProductDisplay => string.IsNullOrWhiteSpace(ProductCode)
            ? ProductName
            : $"{ProductCode} / {ProductName}";

        public string ProgressText => $"{ProgressRate}%";

        public string LotNosText => string.Join(", ", LotNos);
    }

    public class ProductionDailyStatusOption
    {
        public ProductionDailyStatusOption(string code, string name)
        {
            Code = code;
            Name = name;
        }

        public string Code { get; }
        public string Name { get; }
    }
}
