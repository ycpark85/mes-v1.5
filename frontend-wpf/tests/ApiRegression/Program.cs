using System.Net;
using System.IO;
using System.Net.Http;
using Mes.Wpf.Core.Configuration;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Infrastructure.Api;

var passed = 0;
void Check(bool condition, string description)
{
    if (!condition) throw new Exception(description);
    passed++;
}

const string validation = """{"detail":[{"loc":["body","good_qty"],"type":"greater_than_equal","msg":"Input should be greater than or equal to 0","input":"PRIVATE-VALUE","ctx":{"sensitive":"PRIVATE-CONTEXT"}},{"loc":["body","partial_reason"],"type":"missing","msg":"Field required"}]}""";
var settings = new ApiSettings { BaseUrl = "http://unit-test.invalid/", NormalTimeoutSeconds = 1 };
var handler = new FakeHandler((_, _) => Task.FromResult(Response(422, validation)));
var client = new ApiClient(settings, handler);
handler.Respond = (request, _) =>
{
    Check(request.Headers.GetValues("X-MES-Client-Contract").Single() == "1", "client contract header");
    Check(request.Headers.GetValues("X-MES-Client-Version").Single() == ClientRuntime.Version, "actual assembly version");
    Check(request.Headers.GetValues("X-MES-Client-Build").Single() == ClientRuntime.BuildId, "actual DLL build identity");
    return Task.FromResult(Response(422, validation));
};
var error = await client.PutAsync<object, object>("result", new { });
handler.Respond = (_, _) => Task.FromResult(Response(422, validation));
Check(!error.Success && error.Error?.StatusCode == 422, "422 status preserved");
Check(error.Message!.Contains("양품수량") && error.Message.Contains("최솟값"), "quantity detail preserved");
Check(error.Message.Contains("분할검수 사유: 필수 입력값"), "missing field explained");
Check(error.Error!.Fields.Count == 2 && error.Error.Fields[0].Field == "good_qty", "fields retained");
Check(error.Error.RequestId == "regression-422" && error.Message.Contains("요청 ID: regression-422"), "request correlation");
Check(!error.Message.Contains("PRIVATE"), "raw input/context never printed");

foreach (var invoke in new Func<Task<ApiResult<object>>>[]
{
    () => client.GetAsync<object>("result"),
    () => client.PostAsync<object, object>("result", new { }),
    () => client.PatchAsync<object, object>("result", new { }),
    () => client.PostBulkAsync<object, object>("result", new { }),
    () => client.PostMultipartAsync<object>("result", new MultipartFormDataContent()),
    () => client.PatchMultipartAsync<object>("result", new MultipartFormDataContent())
}) Check((await invoke()).Error?.Fields.Count == 2, "all request methods use common error parser");
Check((await client.DeleteAsync("result")).Error?.Fields.Count == 2, "delete detail");
var destination = Path.Combine(Path.GetTempPath(), "mes-api-regression-" + Guid.NewGuid() + ".pdf");
Check((await client.DownloadFileAsync("result", destination)).Error?.Fields.Count == 2 && !File.Exists(destination), "download failure writes no file");

foreach (var item in new[]
{
    (409, """{"detail":"다른 사용자가 수정했습니다."}""", "다른 사용자가"),
    (409, """{"detail":{"code":"STALE_RESULT","message":"다시 조회하세요."}}""", "다시 조회"),
    (400, """{"message":"입력 확인"}""", "입력 확인"),
    (500, "<html>PRIVATE ERROR PAGE</html>", "요청 실패: 500"),
    (503, "", "요청 실패: 503"),
    (400, """{"detail":{"input":"PRIVATE-VALUE"}}""", "요청 실패: 400")
})
{
    var parsed = ApiErrorParser.Parse(item.Item2, item.Item1, "요청 실패", null);
    Check(parsed.Message.Contains(item.Item3) && !parsed.Message.Contains("PRIVATE"), "string/object/non-JSON response");
}
Check(ApiErrorParser.Parse("""{"detail":{"code":"STALE_RESULT","message":"다시 조회"}}""", 409, "실패", null).Code == "STALE_RESULT", "business error code");
Check(ApiErrorParser.Parse("{}", 500, "실패", "bad\nrequest").RequestId is null, "invalid request id rejected");
handler.Respond = (_, _) =>
{
    var response = Response(409, """{"detail":"프로그램 업데이트 후 다시 열어주세요."}""");
    response.Headers.Add("X-MES-Error-Code", "CLIENT_UPDATE_REQUIRED");
    return Task.FromResult(response);
};
var updateRequired = await client.PutAsync<object, object>("result", new { });
Check(updateRequired.Error?.Code == "CLIENT_UPDATE_REQUIRED" && updateRequired.Message!.Contains("프로그램 업데이트"), "legacy-readable update error with structured code");

handler.Respond = (_, _) => Task.FromResult(Response(200, """{"value":7}"""));
var success = await client.GetAsync<Dictionary<string, int>>("result");
Check(success.Success && success.Data!["value"] == 7 && success.Error is null, "successful JSON unchanged");
handler.Respond = (_, _) => throw new HttpRequestException("private transport error");
Check((await client.GetAsync<object>("result")).Message!.Contains("서버에 연결할 수 없습니다"), "network failure explained");
handler.Respond = async (_, token) => { await Task.Delay(Timeout.Infinite, token); throw new Exception(); };
var beforeTimeout = handler.Count;
var timeout = await client.PutAsync<object, object>("result", new { });
Check(timeout.Message!.Contains("저장 여부") && timeout.Message.Contains("처리 결과"), "write timeout does not imply no save");
Check(handler.Count == beforeTimeout + 1, "no automatic write retry");

Check(ClientRuntime.CompatibilityError(new ApiRuntimeInfo
    { MinWpfContractVersion = 1, MaxWpfContractVersion = 1, InspectionQuantityRuleVersion = 2 }) is null, "compatible runtime");
Check(ClientRuntime.CompatibilityError(new ApiRuntimeInfo
    { MinWpfContractVersion = 2, MaxWpfContractVersion = 2, InspectionQuantityRuleVersion = 2 }) is not null, "older client blocked");
Check(ClientRuntime.CompatibilityError(new ApiRuntimeInfo
    { MinWpfContractVersion = 1, MaxWpfContractVersion = 1, InspectionQuantityRuleVersion = 3 }) is not null, "quantity rule mismatch");
Check(ClientRuntime.CompatibilityError(new ApiRuntimeInfo()) is not null, "missing runtime fields fail closed");
Console.WriteLine($"API regression: {passed} checks passed");

static HttpResponseMessage Response(int status, string body)
{
    var result = new HttpResponseMessage((HttpStatusCode)status) { Content = new StringContent(body) };
    result.Headers.Add("X-Request-ID", $"regression-{status}");
    return result;
}

sealed class FakeHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> respond) : HttpMessageHandler
{
    public Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> Respond { get; set; } = respond;
    public int Count { get; private set; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        Count++;
        return Respond(request, token);
    }
}
