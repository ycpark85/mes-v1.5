using System.Text.Json.Serialization;

namespace Mes.Wpf.Core.Models;

public sealed class ApiRuntimeInfo
{
    [JsonPropertyName("environment")] public string Environment { get; set; } = "";
    [JsonPropertyName("server_build")] public string ServerBuild { get; set; } = "unknown";
    [JsonPropertyName("min_wpf_contract_version")] public int MinWpfContractVersion { get; set; }
    [JsonPropertyName("max_wpf_contract_version")] public int MaxWpfContractVersion { get; set; }
    [JsonPropertyName("inspection_quantity_rule_version")] public int InspectionQuantityRuleVersion { get; set; }
}
