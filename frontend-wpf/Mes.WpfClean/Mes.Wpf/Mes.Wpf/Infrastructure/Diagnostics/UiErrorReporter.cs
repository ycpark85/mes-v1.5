using System.Diagnostics;
using System.IO;
using System.Text.Json;
using Mes.Wpf.Core.Configuration;
using Mes.Wpf.Core.Interfaces;

namespace Mes.Wpf.Infrastructure.Diagnostics;

public static class UiErrorReporter
{
    private static readonly object LogLock = new();

    public static void Report(Exception error, IMessageService messages)
    {
        var id = Guid.NewGuid().ToString("N");
        var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Mes.Wpf", "Logs");
        var entry = Describe(error, id);
        try
        {
            lock (LogLock)
            {
                Directory.CreateDirectory(directory);
                var path = Path.Combine(directory, "ui-errors.jsonl");
                if (File.Exists(path) && new FileInfo(path).Length > 1024 * 1024)
                    File.Move(path, Path.Combine(directory, "ui-errors.previous.jsonl"), overwrite: true);
                File.AppendAllText(path, entry + Environment.NewLine);
            }
        }
        catch (Exception loggingError) when (loggingError is IOException or UnauthorizedAccessException)
        {
            Trace.TraceError($"UI error logging failed: {loggingError.GetType().Name}; error_id={id}");
        }
        messages.ShowError($"처리 중 오류가 발생했습니다. 처리 결과를 확인한 뒤 다시 시도하세요.\n오류 ID: {id}");
    }

    internal static string Describe(Exception error, string id) => JsonSerializer.Serialize(new
    {
        time_utc = DateTimeOffset.UtcNow, error_id = id, type = error.GetType().FullName,
        client_version = ClientRuntime.Version, client_build = ClientRuntime.BuildId,
        methods = new StackTrace(error, false).GetFrames().Take(8)
            .Select(frame => frame.GetMethod()).Select(method => $"{method?.DeclaringType?.FullName}.{method?.Name}")
        // Never log exception.Message, input values, file paths, credentials, or arguments.
    });
}
