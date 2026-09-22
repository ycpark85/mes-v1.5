using System.Diagnostics;

namespace Mes.Wpf.Core.Common;

public static class AsyncCommandErrors
{
    // The application installs the user-facing reporter at startup. Explicit handlers support isolated tests.
    public static Action<Exception> Handler { get; set; } = error =>
        Trace.TraceError($"Unhandled asynchronous command: {error.GetType().FullName}");
    public static void Report(Exception error) => Handler(error);
}
