using Mes.Wpf.Modules.Partners.ViewModels;
using Mes.Wpf.Modules.Partners.Views;
using Mes.Wpf.Modules.Products.ViewModels;
using System.Windows;

namespace Mes.Wpf.Modules.Products.Views;

public partial class PartnerProductMappingWindow : Window
{
    public PartnerProductMappingWindow(PartnerProductMappingViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
        Loaded += async (_, _) => await viewModel.RefreshCommand.ExecuteAsync();
        Closing += (_, e) => e.Cancel = viewModel.IsBusy;
    }

    private void FindPartner_Click(object sender, RoutedEventArgs e)
    {
        if (DataContext is not PartnerProductMappingViewModel vm || vm.IsBusy) return;
        var lookup = new PartnerLookupWindow(new PartnerLookupWindowViewModel(vm.ApiClient, vm.MessageService)) { Owner = this };
        if (lookup.ShowDialog() == true && lookup.SelectedPartner != null) vm.SelectPartner(lookup.SelectedPartner);
    }
}
