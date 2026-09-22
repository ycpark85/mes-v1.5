using Mes.Wpf.Core.Models;

namespace Mes.Wpf.Core.Configuration;

public static class ClientRuntime
{
    public const int ContractVersion = 1;
    public const int InspectionQuantityRuleVersion = 2;
    public static string Version => typeof(ClientRuntime).Assembly.GetName().Version?.ToString() ?? "unknown";
    public static string BuildId => typeof(ClientRuntime).Module.ModuleVersionId.ToString("N");
#if DEBUG
    public const string Environment = "Development";
#else
    public const string Environment = "Production";
#endif
    public static string Description => $"실행 버전 {Version} · {Environment}";

    public static string? CompatibilityError(ApiRuntimeInfo info)
    {
        if (info.MinWpfContractVersion <= 0 || info.MaxWpfContractVersion < info.MinWpfContractVersion)
            return "서버의 버전 정보를 확인할 수 없습니다. 서버 업데이트 상태를 확인하세요.";
        if (ContractVersion < info.MinWpfContractVersion || ContractVersion > info.MaxWpfContractVersion
            || info.InspectionQuantityRuleVersion != InspectionQuantityRuleVersion)
            return "실행 프로그램과 서버 버전이 호환되지 않습니다. 프로그램과 서버의 업데이트 상태를 확인하세요.";
        return null;
    }
}
