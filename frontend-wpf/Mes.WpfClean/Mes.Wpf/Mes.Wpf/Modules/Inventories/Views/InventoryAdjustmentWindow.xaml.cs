using System.ComponentModel;
using System.Windows;
using Mes.Wpf.Modules.Inventories.ViewModels;

namespace Mes.Wpf.Modules.Inventories.Views
{
    public partial class InventoryAdjustmentWindow : Window
    {
        private readonly InventoryAdjustmentWindowViewModel _viewModel;
        public InventoryAdjustmentWindow(InventoryAdjustmentWindowViewModel viewModel)
        {
            InitializeComponent();
            _viewModel = viewModel;
            DataContext = viewModel;
            viewModel.CloseRequested += OnCloseRequested;
        }
        private void OnCloseRequested(bool saved) => DialogResult = saved;
        protected override void OnClosing(CancelEventArgs e)
        {
            if (_viewModel.IsLoading) e.Cancel = true;
            base.OnClosing(e);
        }
        protected override void OnClosed(System.EventArgs e)
        {
            _viewModel.CloseRequested -= OnCloseRequested;
            base.OnClosed(e);
        }
    }
}
