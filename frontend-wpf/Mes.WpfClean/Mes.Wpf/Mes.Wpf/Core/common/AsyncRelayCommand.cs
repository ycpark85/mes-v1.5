using System;
using System.Threading.Tasks;
using System.Windows.Input;

namespace Mes.Wpf.Core.Common
{
    public sealed class AsyncRelayCommand : ICommand
    {
        private readonly Func<object?, Task> _executeAsync;
        private readonly Predicate<object?>? _canExecute;
        private readonly Action<Exception>? _onError;
        private bool _isExecuting;

        public AsyncRelayCommand(Func<Task> executeAsync, Func<bool>? canExecute = null, Action<Exception>? onError = null)
            : this(
                _ => executeAsync(),
                canExecute is null ? null : new Predicate<object?>(_ => canExecute()), onError)
        {
        }

        public AsyncRelayCommand(Func<object?, Task> executeAsync, Predicate<object?>? canExecute = null, Action<Exception>? onError = null)
        {
            _executeAsync = executeAsync ?? throw new ArgumentNullException(nameof(executeAsync));
            _canExecute = canExecute;
            _onError = onError;
        }

        public event EventHandler? CanExecuteChanged;

        public bool CanExecute(object? parameter)
        {
            if (_isExecuting)
                return false;

            return _canExecute?.Invoke(parameter) ?? true;
        }

        public async void Execute(object? parameter)
            => await ExecuteAsync(parameter);

        public async Task ExecuteAsync(object? parameter = null)
        {
            if (!CanExecute(parameter))
                return;

            try
            {
                _isExecuting = true;
                RaiseCanExecuteChanged();
                await _executeAsync(parameter);
            }
            catch (Exception error)
            {
                (_onError ?? AsyncCommandErrors.Report)(error);
            }
            finally
            {
                _isExecuting = false;
                RaiseCanExecuteChanged();
            }
        }

        public void RaiseCanExecuteChanged()
        {
            CanExecuteChanged?.Invoke(this, EventArgs.Empty);
        }
    }
}
