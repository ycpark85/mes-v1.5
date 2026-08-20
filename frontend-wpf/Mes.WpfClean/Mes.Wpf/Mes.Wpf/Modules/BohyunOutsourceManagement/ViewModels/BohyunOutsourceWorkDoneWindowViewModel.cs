using System;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.BohyunOutsourceManagement.Dtos;

namespace Mes.Wpf.Modules.BohyunOutsourceManagement.ViewModels
{
    public class BohyunOutsourceWorkDoneWindowViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private bool _isLoading;

        public BohyunOutsourceWorkDoneWindowViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            BohyunOutsourceRowModel row)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            EditModel = new BohyunOutsourceWorkDoneEditModel();
            EditModel.LoadFromDto(row);

            SaveCommand = new AsyncRelayCommand(SaveAsync, () => !IsLoading);
            CancelCommand = new RelayCommand(Cancel);
        }

        public BohyunOutsourceWorkDoneEditModel EditModel { get; }

        public ICommand SaveCommand { get; }

        public ICommand CancelCommand { get; }

        public Window? OwnerWindow { get; set; }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    if (SaveCommand is AsyncRelayCommand saveCommand)
                    {
                        saveCommand.RaiseCanExecuteChanged();
                    }
                }
            }
        }

        private async Task SaveAsync()
        {
            Normalize();

            if (!ValidateForSave())
            {
                return;
            }

            var confirm = _messageService.Confirm("보현문화 작업완료 처리하시겠습니까?");

            if (!confirm)
            {
                return;
            }

            try
            {
                IsLoading = true;

                var request = new BohyunOutsourceWorkDoneRequest
                {
                    WorkDoneSheetQty = EditModel.WorkDoneSheetQty!.Value,
                    OutsourceProcessingFee = EditModel.OutsourceProcessingFee,
                    Remark = string.IsNullOrWhiteSpace(EditModel.Remark) ? null : EditModel.Remark
                };

                var url = $"{ApiRoutes.BohyunOutsourceGroups}/{EditModel.OutsourceWorkGroupId!.Value}/work-done";
                var result = await _apiClient.PostAsync<BohyunOutsourceWorkDoneRequest, object>(url, request);

                if (!result.Success)
                {
                    _messageService.ShowError(result.Message ?? "작업완료 처리에 실패했습니다.");
                    return;
                }

                _messageService.ShowInfo("작업완료 처리되었습니다.");

                if (OwnerWindow != null)
                {
                    OwnerWindow.DialogResult = true;
                    OwnerWindow.Close();
                }
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void Cancel()
        {
            OwnerWindow?.Close();
        }

        private void Normalize()
        {
            EditModel.PartnerName = EditModel.PartnerName?.Trim() ?? string.Empty;
            EditModel.WorkTypeName = EditModel.WorkTypeName?.Trim() ?? string.Empty;
            EditModel.LotNosText = EditModel.LotNosText?.Trim() ?? string.Empty;
            EditModel.ProductNamesText = EditModel.ProductNamesText?.Trim() ?? string.Empty;
            EditModel.Remark = EditModel.Remark?.Trim() ?? string.Empty;
        }

        private bool ValidateForSave()
        {
            if (!EditModel.OutsourceWorkGroupId.HasValue)
            {
                _messageService.ShowWarning("작업완료 처리 대상이 없습니다.");
                return false;
            }

            if (!EditModel.WorkDoneSheetQty.HasValue || EditModel.WorkDoneSheetQty.Value <= 0)
            {
                _messageService.ShowWarning("완료 시트수를 입력해주세요.");
                return false;
            }

            if (EditModel.OutsourceProcessingFee.HasValue && EditModel.OutsourceProcessingFee.Value < 0)
            {
                _messageService.ShowWarning("외주가공비는 0보다 작을 수 없습니다.");
                return false;
            }

            return true;
        }
    }

}
