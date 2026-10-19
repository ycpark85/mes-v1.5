using System.Text.Json.Serialization;

namespace Mes.Wpf.Modules.Products.Dtos;

public class PartnerProductMappingCreateRequest
{
    [JsonPropertyName("partner_id")]
    public long PartnerId { get; set; }
    [JsonPropertyName("erp_product_code")]
    public string ErpProductCode { get; set; } = string.Empty;
    [JsonPropertyName("customer_product_name")]
    public string CustomerProductName { get; set; } = string.Empty;
    [JsonPropertyName("customer_product_spec")]
    public string? CustomerProductSpec { get; set; }
}

public class PartnerProductMappingDto : PartnerProductMappingCreateRequest
{
    [JsonPropertyName("mapping_id")]
    public long MappingId { get; set; }
    [JsonPropertyName("product_id")]
    public long ProductId { get; set; }
    [JsonPropertyName("partner_name")]
    public string? PartnerName { get; set; }
    [JsonPropertyName("is_active")]
    public bool IsActive { get; set; }
    public string StatusDisplay => IsActive ? "연결 중" : "해제됨";
}
