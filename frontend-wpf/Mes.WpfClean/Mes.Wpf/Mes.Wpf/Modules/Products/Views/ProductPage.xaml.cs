using Mes.Wpf.Modules.Drawings.Dtos;
using Mes.Wpf.Modules.Products.ViewModels;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Mes.Wpf.Modules.Drawings.ViewModels;
using Mes.Wpf.Modules.Drawings.Views;

namespace Mes.Wpf.Modules.Products.Views
{
    public partial class ProductPage : UserControl
    {
        public ProductPage()
        {
            InitializeComponent();
        }

        private void PartnerMappings_Click(object sender, RoutedEventArgs e)
        {
            if (DataContext is not ProductPageViewModel vm || !vm.CanManagePartnerMappings || vm.SelectedItem == null) return;
            var window = new PartnerProductMappingWindow(new PartnerProductMappingViewModel(vm.ApiClient, vm.MessageService, vm.SelectedItem))
            { Owner = Window.GetWindow(this) };
            window.ShowDialog();
        }

        private void BulkUpload_Click(object sender, RoutedEventArgs e)
        {
            var window = new ProductBulkUploadWindow
            {
                Owner = Window.GetWindow(this),
                DataContext = DataContext
            };

            window.ShowDialog();
        }

        
        private void DrawingSearchResult_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (DataContext is ProductPageViewModel vm
                && sender is ListBox listBox
                && listBox.SelectedItem is DrawingDto drawing)
            {
                vm.SelectDrawing(drawing);
                listBox.SelectedItem = null;
            }
        }

        private void DrawingSearchTextBox_KeyDown(object sender, KeyEventArgs e)
        {
            if (DataContext is ProductPageViewModel current && !current.CanChangeDrawing) return;
            if (e.Key != Key.Enter)
            {
                return;
            }

            if (DataContext is not ProductPageViewModel vm)
            {
                return;
            }

            var keyword = vm.DrawingSearchKeyword?.Trim();

            var lookupVm = new DrawingLookupWindowViewModel(
                vm.ApiClient,
                vm.MessageService,
                keyword);

            var window = new DrawingLookupWindow(lookupVm)
            {
                Owner = Window.GetWindow(this)
            };

            if (window.ShowDialog() == true && window.SelectedDrawing != null)
            {
                vm.SelectDrawing(window.SelectedDrawing);
            }

            e.Handled = true;
        }

    }
}