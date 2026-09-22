namespace Mes.Wpf.Core.Models;

public sealed class ApiError
{
    public int? StatusCode { get; init; }
    public string? Code { get; init; }
    public string? RequestId { get; init; }
    public string Message { get; init; } = "";
    public IReadOnlyList<ApiFieldError> Fields { get; init; } = Array.Empty<ApiFieldError>();
}

public sealed record ApiFieldError(string Field, string? Code, string Message);
