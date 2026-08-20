using System;
using System.Threading.Tasks;
using System.Windows.Input;

namespace Mes.Wpf.Core.Common
{
    public sealed class AsyncRelayCommand<T> : ICommand
    {
        private readonly Func<T?, Task> _executeAsync;
        private readonly Predicate<T?>? _canExecute;
        private bool _isExecuting;

        public AsyncRelayCommand(Func<T?, Task> executeAsync, Predicate<T?>? canExecute = null)
        {
            _executeAsync = executeAsync ?? throw new ArgumentNullException(nameof(executeAsync));
            _canExecute = canExecute;
        }

        public event EventHandler? CanExecuteChanged;

        public bool CanExecute(object? parameter)
        {
            if (_isExecuting)
            {
                return false;
            }

            if (parameter == null)
            {
                return _canExecute == null || _canExecute(default);
            }

            return parameter is T typedParameter && (_canExecute?.Invoke(typedParameter) ?? true);
        }

        public async void Execute(object? parameter)
        {
            if (!CanExecute(parameter))
            {
                return;
            }

            try
            {
                _isExecuting = true;
                RaiseCanExecuteChanged();
                await _executeAsync(parameter is T typedParameter ? typedParameter : default);
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
