namespace Mes.Wpf.Core.Models
{
    public class ApiResult<T>
    {
        public bool Success { get; set; }

        public string? Message { get; set; }

        public ApiError? Error { get; set; }

        public T? Data { get; set; }
    }
}
