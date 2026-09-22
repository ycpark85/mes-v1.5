using Mes.Wpf.Modules.Inventories.ViewModels;
using System.Windows;
using System.Windows.Controls;

namespace Mes.Wpf.Modules.Inventories.Views
{
    public partial class InventoryPage : UserControl
    {
        private InventoryPageViewModel? _viewModel;

        public InventoryPage()
        {
            InitializeComponent();
            DataContextChanged += InventoryPage_DataContextChanged;
        }

        private void InventoryPage_DataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
        {
            if (_viewModel != null)
            {
                _viewModel.RequestOpenInitialInventoryBulkUpload -= OpenInitialInventoryBulkUploadWindow;
                _viewModel.RequestOpenAdjustment -= OpenAdjustmentWindow;
            }

            _viewModel = e.NewValue as InventoryPageViewModel;

            if (_viewModel != null)
            {
                _viewModel.RequestOpenInitialInventoryBulkUpload += OpenInitialInventoryBulkUploadWindow;
                _viewModel.RequestOpenAdjustment += OpenAdjustmentWindow;
            }
        }

        private void OpenAdjustmentWindow(InventoryAdjustmentWindowViewModel viewModel)
        {
            new InventoryAdjustmentWindow(viewModel) { Owner = Window.GetWindow(this) }.ShowDialog();
        }

        private void OpenInitialInventoryBulkUploadWindow(InitialInventoryBulkUploadWindowViewModel viewModel)
        {
            var window = new InitialInventoryBulkUploadWindow
            {
                Owner = Window.GetWindow(this),
                DataContext = viewModel
            };

            window.ShowDialog();
        }
    }
}
