using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Mes.Wpf.Core.Configuration;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;

namespace Mes.Wpf.Infrastructure.Api
{
    public class ApiClient : IApiClient
    {
        private const string NetworkErrorMessage =
            "서버에 연결할 수 없습니다. 네트워크와 서버 상태를 확인하세요.";
        private const string NormalTimeoutMessage =
            "요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.";
        private const string WriteTimeoutMessage =
            "요청 시간이 초과되어 저장 여부를 확인할 수 없습니다. 목록을 새로 조회하여 처리 결과를 확인한 후 다시 시도하세요.";
        private const string BulkTimeoutMessage =
            "대량 처리 요청 시간이 초과되었습니다. 처리 결과를 확인한 후 다시 시도하세요.";
        private const string FileTimeoutMessage =
            "파일 전송 시간이 초과되었습니다. 처리 결과와 네트워크 상태를 확인한 후 다시 시도하세요.";

        private static readonly JsonSerializerOptions JsonOptions = CreateJsonOptions();
        private readonly HttpClient _httpClient;
        private readonly TimeSpan _normalTimeout;
        private readonly TimeSpan _bulkTimeout;
        private readonly TimeSpan _fileTransferTimeout;

        public ApiClient(ApiSettings settings) : this(settings, null) { }

        internal ApiClient(ApiSettings settings, HttpMessageHandler? handler)
        {
            ArgumentNullException.ThrowIfNull(settings);

            if (string.IsNullOrWhiteSpace(settings.BaseUrl))
            {
                throw new ArgumentException("API BaseUrl이 비어 있습니다.", nameof(settings));
            }

            if (settings.NormalTimeoutSeconds <= 0
                || settings.BulkTimeoutSeconds <= 0
                || settings.FileTransferTimeoutSeconds <= 0)
            {
                throw new ArgumentException("API 제한시간은 1초 이상이어야 합니다.", nameof(settings));
            }

            _normalTimeout = TimeSpan.FromSeconds(settings.NormalTimeoutSeconds);
            _bulkTimeout = TimeSpan.FromSeconds(settings.BulkTimeoutSeconds);
            _fileTransferTimeout = TimeSpan.FromSeconds(settings.FileTransferTimeoutSeconds);
            _httpClient = handler is null ? new HttpClient() : new HttpClient(handler);
            _httpClient.BaseAddress = new Uri(settings.BaseUrl);
            _httpClient.Timeout = Timeout.InfiniteTimeSpan;
            _httpClient.DefaultRequestHeaders.Add("X-MES-Client-Contract", ClientRuntime.ContractVersion.ToString());
            _httpClient.DefaultRequestHeaders.Add("X-MES-Client-Version", ClientRuntime.Version);
            _httpClient.DefaultRequestHeaders.Add("X-MES-Client-Build", ClientRuntime.BuildId);
        }

        private static JsonSerializerOptions CreateJsonOptions()
        {
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
            options.Converters.Add(new KoreaDateTimeJsonConverter());
            return options;
        }

        public void SetAccessToken(string? accessToken)
        {
            if (string.IsNullOrWhiteSpace(accessToken))
            {
                ClearAccessToken();
                return;
            }

            _httpClient.DefaultRequestHeaders.Authorization =
                new AuthenticationHeaderValue("Bearer", accessToken);
        }

        public void ClearAccessToken()
        {
            _httpClient.DefaultRequestHeaders.Authorization = null;
        }

        public Task<ApiResult<T>> GetAsync<T>(string relativeUrl)
        {
            return SendAndReadAsync<T>(
                cancellationToken => _httpClient.GetAsync(relativeUrl, cancellationToken),
                "GET 요청 실패",
                _normalTimeout,
                NormalTimeoutMessage);
        }

        public Task<ApiResult<TResponse>> PostAsync<TRequest, TResponse>(
            string relativeUrl,
            TRequest request)
        {
            return SendAndReadAsync<TResponse>(
                cancellationToken => _httpClient.PostAsJsonAsync(relativeUrl, request, cancellationToken),
                "POST 요청 실패",
                _normalTimeout,
                WriteTimeoutMessage);
        }

        public Task<ApiResult<TResponse>> PostBulkAsync<TRequest, TResponse>(
            string relativeUrl,
            TRequest request)
        {
            return SendAndReadAsync<TResponse>(
                cancellationToken => _httpClient.PostAsJsonAsync(relativeUrl, request, cancellationToken),
                "대량 처리 요청 실패",
                _bulkTimeout,
                BulkTimeoutMessage);
        }

        public Task<ApiResult<TResponse>> PutAsync<TRequest, TResponse>(
            string relativeUrl,
            TRequest request)
        {
            return SendAndReadAsync<TResponse>(
                cancellationToken => _httpClient.PutAsJsonAsync(relativeUrl, request, cancellationToken),
                "PUT 요청 실패",
                _normalTimeout,
                WriteTimeoutMessage);
        }

        public async Task<ApiResult<TResponse>> PatchAsync<TRequest, TResponse>(
            string relativeUrl,
            TRequest request)
        {
            using var requestMessage = new HttpRequestMessage(HttpMethod.Patch, relativeUrl)
            {
                Content = JsonContent.Create(request)
            };

            return await SendAndReadAsync<TResponse>(
                cancellationToken => _httpClient.SendAsync(requestMessage, cancellationToken),
                "PATCH 요청 실패",
                _normalTimeout,
                WriteTimeoutMessage);
        }

        public async Task<ApiResult<bool>> DeleteAsync(string relativeUrl)
        {
            using var timeoutCts = new CancellationTokenSource(_normalTimeout);

            try
            {
                using var response = await _httpClient.DeleteAsync(relativeUrl, timeoutCts.Token);

                if (!response.IsSuccessStatusCode)
                {
                    return await ReadFailureAsync<bool>(response, "DELETE 요청 실패", timeoutCts.Token);
                }

                return new ApiResult<bool>
                {
                    Success = true,
                    Data = true
                };
            }
            catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested)
            {
                return Failure<bool>(WriteTimeoutMessage);
            }
            catch (HttpRequestException)
            {
                return Failure<bool>(NetworkErrorMessage);
            }
            catch (Exception ex)
            {
                return Failure<bool>($"요청 처리 중 오류가 발생했습니다: {ex.Message}");
            }
        }

        public Task<ApiResult<TResponse>> PostMultipartAsync<TResponse>(
            string relativeUrl,
            MultipartFormDataContent content)
        {
            return SendAndReadAsync<TResponse>(
                cancellationToken => _httpClient.PostAsync(relativeUrl, content, cancellationToken),
                "파일 업로드 실패",
                _fileTransferTimeout,
                FileTimeoutMessage);
        }

        public async Task<ApiResult<TResponse>> PatchMultipartAsync<TResponse>(
            string relativeUrl,
            MultipartFormDataContent content)
        {
            using var requestMessage = new HttpRequestMessage(HttpMethod.Patch, relativeUrl)
            {
                Content = content
            };

            return await SendAndReadAsync<TResponse>(
                cancellationToken => _httpClient.SendAsync(requestMessage, cancellationToken),
                "파일 업로드 실패",
                _fileTransferTimeout,
                FileTimeoutMessage);
        }

        public async Task<ApiResult<bool>> DownloadFileAsync(
            string relativeUrl,
            string destinationPath)
        {
            var tempPath = $"{destinationPath}.{Guid.NewGuid():N}.download";
            using var timeoutCts = new CancellationTokenSource(_fileTransferTimeout);

            try
            {
                using var response = await _httpClient.GetAsync(
                    relativeUrl,
                    HttpCompletionOption.ResponseHeadersRead,
                    timeoutCts.Token);

                if (!response.IsSuccessStatusCode)
                {
                    return await ReadFailureAsync<bool>(
                        response,
                        "파일 다운로드 실패",
                        timeoutCts.Token);
                }

                await using (var source = await response.Content.ReadAsStreamAsync(timeoutCts.Token))
                await using (var destination = new FileStream(
                    tempPath,
                    FileMode.CreateNew,
                    FileAccess.Write,
                    FileShare.None,
                    81920,
                    FileOptions.Asynchronous | FileOptions.SequentialScan))
                {
                    await source.CopyToAsync(destination, timeoutCts.Token);
                }

                File.Move(tempPath, destinationPath, true);
                return new ApiResult<bool>
                {
                    Success = true,
                    Data = true
                };
            }
            catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested)
            {
                return Failure<bool>(FileTimeoutMessage);
            }
            catch (HttpRequestException)
            {
                return Failure<bool>(NetworkErrorMessage);
            }
            catch (Exception ex)
            {
                return Failure<bool>($"파일 다운로드 중 오류가 발생했습니다: {ex.Message}");
            }
            finally
            {
                TryDeleteFile(tempPath);
            }
        }

        public string BuildAbsoluteUrl(string relativeUrl)
        {
            return new Uri(_httpClient.BaseAddress!, relativeUrl).ToString();
        }

        private async Task<ApiResult<T>> SendAndReadAsync<T>(
            Func<CancellationToken, Task<HttpResponseMessage>> sendAsync,
            string errorPrefix,
            TimeSpan timeout,
            string timeoutMessage)
        {
            using var timeoutCts = new CancellationTokenSource(timeout);

            try
            {
                using var response = await sendAsync(timeoutCts.Token);

                if (!response.IsSuccessStatusCode)
                {
                    return await ReadFailureAsync<T>(
                        response,
                        errorPrefix,
                        timeoutCts.Token);
                }

                var data = await response.Content.ReadFromJsonAsync<T>(
                    JsonOptions,
                    timeoutCts.Token);

                return new ApiResult<T>
                {
                    Success = true,
                    Data = data
                };
            }
            catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested)
            {
                return Failure<T>(timeoutMessage);
            }
            catch (HttpRequestException)
            {
                return Failure<T>(NetworkErrorMessage);
            }
            catch (Exception ex)
            {
                return Failure<T>($"요청 처리 중 오류가 발생했습니다: {ex.Message}");
            }
        }

        private static async Task<ApiResult<T>> ReadFailureAsync<T>(
            HttpResponseMessage response,
            string defaultPrefix,
            CancellationToken cancellationToken)
        {
            var raw = await response.Content.ReadAsStringAsync(cancellationToken);
            var requestId = response.Headers.TryGetValues("X-Request-ID", out var values)
                ? values.FirstOrDefault() : null;
            var errorCode = response.Headers.TryGetValues("X-MES-Error-Code", out var codes)
                ? codes.FirstOrDefault() : null;
            var error = ApiErrorParser.Parse(raw, (int)response.StatusCode, defaultPrefix, requestId, errorCode);
            return new ApiResult<T> { Success = false, Message = error.Message, Error = error };
        }

        private static ApiResult<T> Failure<T>(string message)
        {
            return new ApiResult<T>
            {
                Success = false,
                Message = message
            };
        }

        private static void TryDeleteFile(string path)
        {
            try
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
            catch
            {
            }
        }
    }
}
