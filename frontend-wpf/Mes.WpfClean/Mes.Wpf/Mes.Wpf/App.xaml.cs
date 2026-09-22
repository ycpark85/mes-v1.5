using System;
using System.Windows;
using Mes.Wpf.Core.Configuration;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Infrastructure.Diagnostics;
using Mes.Wpf.Infrastructure.Api;
using Mes.Wpf.Infrastructure.Dialogs;
using Mes.Wpf.Modules.Auth.ViewModels;
using Mes.Wpf.Modules.Auth.Views;
using Mes.Wpf.Views.Shell;

namespace Mes.Wpf
{
    public partial class App : Application
    {
        protected override void OnStartup(StartupEventArgs e)
        {
            // App.xaml에 StartupUri가 남아 있어도 MainWindow가 자동으로 뜨지 않도록 차단
            base.OnStartup(e);

            var messageService = new MessageService();
            AsyncCommandErrors.Handler = error => UiErrorReporter.Report(error, messageService);

            try
            {
                // LoginWindow가 닫힐 때 앱이 바로 종료되지 않도록 임시로 명시 종료 모드 사용
                ShutdownMode = ShutdownMode.OnExplicitShutdown;

                var appSettings = AppSettings.Load();
                var apiClient = new ApiClient(appSettings.Api);

                var loginViewModel = new LoginViewModel(apiClient, messageService);
                var loginWindow = new LoginWindow(loginViewModel);

                var loginResult = loginWindow.ShowDialog();

                if (loginResult != true || loginViewModel.LoginResponse == null)
                {
                    Shutdown();
                    return;
                }

                var mainWindow = new MainWindow(
                    apiClient,
                    messageService,
                    loginViewModel.LoginResponse);

                MainWindow = mainWindow;

                // MainWindow가 닫히면 앱 종료
                ShutdownMode = ShutdownMode.OnMainWindowClose;

                mainWindow.Show();
            }
            catch (Exception ex)
            {
                messageService.ShowError(
                    $"프로그램 시작 중 오류가 발생했습니다.\n\n{ex.Message}",
                    "시작 오류");

                Shutdown();
            }
        }
    }
}
