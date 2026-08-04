using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;
using Mes.Wpf.Modules.InspectionSchedules.ViewModels;

namespace Mes.Wpf.Modules.InspectionSchedules.Views
{
    public partial class InspectionResultWindow : Window
    {
        private bool _wasChanged;

        public InspectionResultWindow()
        {
            InitializeComponent();
        }

        public InspectionResultWindow(InspectionResultWindowViewModel viewModel)
        {
            InitializeComponent();

            DataContext = viewModel;
            viewModel.CloseRequested += OnCloseRequested;
            viewModel.EditRequested += OnEditRequested;
        }

        private void OnCloseRequested(bool dialogResult)
        {
            DialogResult = dialogResult || _wasChanged;
            Close();
        }

        private async void OnEditRequested()
        {
            if (DataContext is not InspectionResultWindowViewModel detailVm)
            {
                return;
            }

            var editVm = new InspectionResultWindowViewModel(
                detailVm.ApiClient,
                detailVm.MessageService,
                canEdit: true);

            await editVm.InitializeAsync(
                detailVm.InspectionScheduleId,
                detailVm.LotNo,
                detailVm.ProductName,
                detailVm.PartnerName,
                detailVm.InspectionDate,
                detailVm.PlanQty,
                detailVm.DueDate,
                detailVm.OrderQty);

            var editWindow = new InspectionResultWindow(editVm)
            {
                Owner = this,
                Title = "검수실적 수정"
            };

            if (editWindow.ShowDialog() == true)
            {
                _wasChanged = true;
                await detailVm.RefreshAsync();
            }
        }

        private void DefectTypeIdTextBox_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key != Key.Enter)
            {
                return;
            }

            if (DataContext is not InspectionResultWindowViewModel vm)
            {
                return;
            }

            if (sender is not TextBox textBox || textBox.Tag is not InspectionResultDefectEditModel defect)
            {
                return;
            }

            OpenDefectTypeLookup(vm, defect, textBox.Text?.Trim());

            e.Handled = true;
        }

        private void OpenDefectTypeLookup(
            InspectionResultWindowViewModel vm,
            InspectionResultDefectEditModel defect,
            string? typedKeyword)
        {
            var initialKeyword = typedKeyword;

            if (string.IsNullOrWhiteSpace(initialKeyword))
            {
                initialKeyword = defect.Category2Name;
            }

            if (string.IsNullOrWhiteSpace(initialKeyword))
            {
                initialKeyword = defect.Category1Name;
            }

            if (string.IsNullOrWhiteSpace(initialKeyword))
            {
                initialKeyword = defect.DefectCode;
            }

            if (string.IsNullOrWhiteSpace(initialKeyword) && defect.DefectTypeId.HasValue)
            {
                initialKeyword = defect.DefectTypeId.Value.ToString();
            }

            var lookupVm = new DefectTypeLookupWindowViewModel(
                vm.ApiClient,
                vm.MessageService,
                initialKeyword);

            var lookupWindow = new DefectTypeLookupWindow(lookupVm)
            {
                Owner = this
            };

            if (lookupWindow.ShowDialog() == true && lookupWindow.SelectedDefectType != null)
            {
                vm.ApplySelectedDefectType(defect, lookupWindow.SelectedDefectType);
            }
        }
    }
}
