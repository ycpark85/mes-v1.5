using System;
using System.Threading.Tasks;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Configuration;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.Auth.Dtos;

namespace Mes.Wpf.Modules.Auth.ViewModels
{
    public class LoginViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly UserPreferences _userPreferences;

        private string _loginId = string.Empty;
        private string _password = string.Empty;
        private string _errorMessage = string.Empty;
        private bool _rememberLoginId;
        private bool _isLoading;

        public LoginViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _userPreferences = UserPreferences.Load();
            _loginId = _userPreferences.SavedLoginId?.Trim() ?? string.Empty;
            _rememberLoginId = !string.IsNullOrWhiteSpace(_loginId);

            LoginCommand = new AsyncRelayCommand(LoginAsync, CanLogin);
        }

        public event EventHandler? LoginSucceeded;

        public AsyncRelayCommand LoginCommand { get; }

        public AuthLoginResponse? LoginResponse { get; private set; }
        public string RuntimeDescription => ClientRuntime.Description;
        private string _runtimeDetails = $"WPF 빌드: {ClientRuntime.BuildId}";
        public string RuntimeDetails
        {
            get => _runtimeDetails;
            private set => SetProperty(ref _runtimeDetails, value);
        }

        public string LoginId
        {
            get => _loginId;
            set
            {
                if (SetProperty(ref _loginId, value))
                {
                    LoginCommand.RaiseCanExecuteChanged();
                }
            }
        }

        public string Password
        {
            get => _password;
            set
            {
                if (SetProperty(ref _password, value))
                {
                    LoginCommand.RaiseCanExecuteChanged();
                }
            }
        }

        public string ErrorMessage
        {
            get => _errorMessage;
            set => SetProperty(ref _errorMessage, value);
        }

        public bool RememberLoginId
        {
            get => _rememberLoginId;
            set => SetProperty(ref _rememberLoginId, value);
        }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    LoginCommand.RaiseCanExecuteChanged();
                }
            }
        }

        private bool CanLogin()
        {
            if (IsLoading)
            {
                return false;
            }

            return !string.IsNullOrWhiteSpace(LoginId)
                && !string.IsNullOrWhiteSpace(Password);
        }

        private async Task LoginAsync()
        {
            Normalize();

            if (!Validate())
            {
                return;
            }

            IsLoading = true;
            ErrorMessage = string.Empty;

            try
            {
                _apiClient.ClearAccessToken();

                var runtime = await _apiClient.GetAsync<ApiRuntimeInfo>(ApiRoutes.RuntimeInfo);
                if (!runtime.Success || runtime.Data is null)
                {
                    ErrorMessage = runtime.Error?.StatusCode == 404
                        ? "서버의 버전 확인 기능이 없습니다. 서버 업데이트 상태를 확인하세요."
                        : runtime.Message ?? "서버 버전을 확인할 수 없습니다.";
                    return;
                }
                RuntimeDetails = $"WPF 빌드: {ClientRuntime.BuildId}\n서버: {runtime.Data.Environment} / {runtime.Data.ServerBuild}";
                var compatibilityError = ClientRuntime.CompatibilityError(runtime.Data);
                if (compatibilityError is not null)
                {
                    ErrorMessage = compatibilityError;
                    return;
                }

                var request = new AuthLoginRequest
                {
                    LoginId = LoginId,
                    Password = Password
                };

                var result = await _apiClient.PostAsync<AuthLoginRequest, AuthLoginResponse>(
                    ApiRoutes.AuthLogin,
                    request);

                if (!result.Success || result.Data == null)
                {
                    ErrorMessage = result.Message ?? "로그인에 실패했습니다.";
                    return;
                }

                if (string.IsNullOrWhiteSpace(result.Data.AccessToken))
                {
                    ErrorMessage = "로그인 응답에 토큰 정보가 없습니다.";
                    return;
                }

                _apiClient.SetAccessToken(result.Data.AccessToken);

                LoginResponse = result.Data;
                SaveLoginIdPreference();
                LoginSucceeded?.Invoke(this, EventArgs.Empty);
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void Normalize()
        {
            LoginId = LoginId.Trim();
        }

        private void SaveLoginIdPreference()
        {
            try
            {
                _userPreferences.SavedLoginId = RememberLoginId ? LoginId : null;
                _userPreferences.Save();
            }
            catch (System.IO.IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }

        private bool Validate()
        {
            if (string.IsNullOrWhiteSpace(LoginId))
            {
                ErrorMessage = "아이디를 입력하세요.";
                return false;
            }

            if (string.IsNullOrWhiteSpace(Password))
            {
                ErrorMessage = "비밀번호를 입력하세요.";
                return false;
            }

            if (Password.Length < 6)
            {
                ErrorMessage = "비밀번호는 최소 6자리 이상입니다.";
                return false;
            }

            return true;
        }
    }
}
