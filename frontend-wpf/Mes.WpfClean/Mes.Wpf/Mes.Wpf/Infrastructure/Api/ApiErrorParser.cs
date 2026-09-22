using System.Text.Json;
using Mes.Wpf.Core.Models;

namespace Mes.Wpf.Infrastructure.Api;

internal static class ApiErrorParser
{
    private static readonly IReadOnlyDictionary<string, string> FieldLabels = new Dictionary<string, string>
    {
        ["good_qty"] = "양품수량", ["defect_qty"] = "불량수량",
        ["defect_ship_qty"] = "불량출고수량", ["uninspected_qty"] = "미검수수량",
        ["stock_ship_qty"] = "재고 출고수량", ["result_ship_qty"] = "생산 출고수량",
        ["stock_in_qty"] = "재고편입수량", ["discard_qty"] = "폐기수량",
        ["shortage_reason"] = "미달 종료 사유", ["partial_reason"] = "분할검수 사유",
        ["next_inspection_date"] = "다음 검수일", ["order_qty"] = "발주수량",
        ["due_date"] = "납기일", ["quantity_rule_version"] = "검수 규칙 버전"
    };

    public static ApiError Parse(string raw, int statusCode, string prefix, string? requestId, string? errorCode = null)
    {
        var fields = new List<ApiFieldError>();
        var messages = new List<string>();
        string? code = errorCode;
        try
        {
            using var document = JsonDocument.Parse(raw);
            var root = document.RootElement;
            if (root.ValueKind == JsonValueKind.Object)
            {
                code = Text(root, "code") ?? code;
                requestId ??= Text(root, "request_id");
                if (root.TryGetProperty("detail", out var detail))
                {
                    ReadDetail(detail, fields, messages, 0);
                    if (code is null && detail.ValueKind == JsonValueKind.Object)
                        code = Text(detail, "code");
                }
                if (messages.Count == 0 && Text(root, "message") is { } message)
                    messages.Add(message);
                if (messages.Count == 0 && root.TryGetProperty("errors", out var errors))
                    ReadDetail(errors, fields, messages, 0);
            }
        }
        catch (JsonException) { }

        requestId = SafeIdentifier(requestId);
        var description = messages.Count > 0
            ? string.Join("\n", messages.Distinct())
            : $"{prefix}: {statusCode}";
        return new ApiError
        {
            StatusCode = statusCode, Code = SafeIdentifier(code), RequestId = requestId,
            Fields = fields,
            Message = requestId is null ? description : $"{description}\n요청 ID: {requestId}"
        };
    }

    private static void ReadDetail(JsonElement element, List<ApiFieldError> fields,
        List<string> messages, int depth)
    {
        if (depth > 4 || messages.Count >= 20) return;
        if (element.ValueKind == JsonValueKind.String)
        {
            if (Clean(element.GetString()) is { } text) messages.Add(text);
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                ReadDetail(item, fields, messages, depth + 1);
                if (messages.Count >= 20) break;
            }
        }
        else if (element.ValueKind == JsonValueKind.Object)
        {
            var code = Text(element, "type") ?? Text(element, "code");
            var message = Text(element, "msg") ?? Text(element, "message");
            if (message is not null)
            {
                message = code switch
                {
                    "missing" => "필수 입력값입니다.",
                    "int_parsing" or "int_type" or "int_from_float" => "정수로 입력하세요.",
                    "greater_than_equal" => "허용된 최솟값 이상으로 입력하세요.",
                    "greater_than" => "허용된 최솟값보다 크게 입력하세요.",
                    "less_than_equal" => "허용된 최댓값 이하로 입력하세요.",
                    _ => message
                };
                var field = Text(element, "field") ?? "";
                if (element.TryGetProperty("loc", out var loc) && loc.ValueKind == JsonValueKind.Array)
                    field = string.Join(".", loc.EnumerateArray()
                        .Where(part => part.ValueKind is JsonValueKind.String or JsonValueKind.Number)
                        .Select(part => Clean(part.ToString()))
                        .Where(part => part is not null && part is not ("body" or "query" or "path")));
                fields.Add(new ApiFieldError(field, SafeIdentifier(code), message));
                var label = FieldLabels.GetValueOrDefault(field, field);
                messages.Add(string.IsNullOrEmpty(label) ? message : $"{label}: {message}");
            }
            if (element.TryGetProperty("errors", out var nested))
                ReadDetail(nested, fields, messages, depth + 1);
        }
    }

    private static string? Text(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? Clean(value.GetString()) : null;

    private static string? Clean(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        return new string(value.Trim().Take(512).Where(c => !char.IsControl(c)).ToArray());
    }

    private static string? SafeIdentifier(string? value) =>
        value is { Length: > 0 and <= 64 } && value.All(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or '-')
            ? value : null;
}
