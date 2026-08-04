using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.OutsourceWorkInstructions.Dtos;
using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.OutsourceWorkInstructions.ViewModels
{
    public sealed class OutsourceWorkGroupListPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private bool _isLoading;
        private DateTime? _dateFrom = DateTime.Today.AddMonths(-1);
        private DateTime? _dateTo = DateTime.Today;
        private string _selectedProcessType = "전체";
        private string _selectedStatus = "전체";
        private string _searchKeyword = string.Empty;
        private OutsourceWorkGroupListItemDto? _selectedItem;
        private OutsourceWorkGroupDetailDto? _selectedDetail;
        private string _cancelReason = string.Empty;
        private int _editSheetQty;
        private decimal? _editLengthM;
        private int _editSheetCutCount;
        private string _editFabricLotNo = string.Empty;
        private string _editMemo = string.Empty;
        private string _updateReason = string.Empty;

        public OutsourceWorkGroupListPageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<OutsourceWorkGroupListItemDto>();
            ProcessTypeOptions = new ObservableCollection<string> { "전체", "재단", "인쇄" };
            StatusOptions = new ObservableCollection<string> { "전체", "등록", "업체입고", "작업완료", "출고완료", "취소" };

            SearchCommand = new AsyncRelayCommand(SearchAsync);
            ResetCommand = new RelayCommand(Reset);
            CancelCommand = new AsyncRelayCommand(CancelAsync);
            SaveUpdateCommand = new AsyncRelayCommand(SaveUpdateAsync);
            ReloadEditFormCommand = new RelayCommand(LoadEditFormFromSelectedDetail);
        }

        public ObservableCollection<OutsourceWorkGroupListItemDto> Items { get; }
        public ObservableCollection<string> ProcessTypeOptions { get; }
        public ObservableCollection<string> StatusOptions { get; }

        public AsyncRelayCommand SearchCommand { get; }
        public RelayCommand ResetCommand { get; }
        public AsyncRelayCommand CancelCommand { get; }
        public AsyncRelayCommand SaveUpdateCommand { get; }
        public RelayCommand ReloadEditFormCommand { get; }

        public bool IsLoading
        {
            get => _isLoading;
            set => SetProperty(ref _isLoading, value);
        }

        public DateTime? DateFrom
        {
            get => _dateFrom;
            set => SetProperty(ref _dateFrom, value);
        }

        public DateTime? DateTo
        {
            get => _dateTo;
            set => SetProperty(ref _dateTo, value);
        }

        public string SelectedProcessType
        {
            get => _selectedProcessType;
            set => SetProperty(ref _selectedProcessType, value);
        }

        public string SelectedStatus
        {
            get => _selectedStatus;
            set => SetProperty(ref _selectedStatus, value);
        }

        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public OutsourceWorkGroupListItemDto? SelectedItem
        {
            get => _selectedItem;
            set
            {
                if (SetProperty(ref _selectedItem, value))
                {
                    _ = LoadDetailAsync(value);
                }
            }
        }

        public OutsourceWorkGroupDetailDto? SelectedDetail
        {
            get => _selectedDetail;
            set
            {
                if (SetProperty(ref _selectedDetail, value))
                {
                    LoadEditFormFromSelectedDetail();
                    OnPropertyChanged(nameof(CanUpdateSelectedDetail));
                }
            }
        }

        public string CancelReason
        {
            get => _cancelReason;
            set => SetProperty(ref _cancelReason, value);
        }

        public bool CanUpdateSelectedDetail => SelectedDetail?.CanUpdate == true;

        public int EditSheetQty
        {
            get => _editSheetQty;
            set => SetProperty(ref _editSheetQty, value);
        }

        public decimal? EditLengthM
        {
            get => _editLengthM;
            set => SetProperty(ref _editLengthM, value);
        }

        public int EditSheetCutCount
        {
            get => _editSheetCutCount;
            set => SetProperty(ref _editSheetCutCount, value);
        }

        public string EditFabricLotNo
        {
            get => _editFabricLotNo;
            set => SetProperty(ref _editFabricLotNo, value);
        }

        public string EditMemo
        {
            get => _editMemo;
            set => SetProperty(ref _editMemo, value);
        }

        public string UpdateReason
        {
            get => _updateReason;
            set => SetProperty(ref _updateReason, value);
        }

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        private async Task SearchAsync()
        {
            IsLoading = true;

            try
            {
                var result = await _apiClient.GetAsync<OutsourceWorkGroupListDto>(BuildListUrl());

                if (!result.Success || result.Data == null)
                {
                    Items.Clear();
                    SelectedDetail = null;
                    _messageService.ShowError(result.Message ?? "외주 작업지시 목록 조회 중 오류가 발생했습니다.");
                    return;
                }

                Items.Clear();
                foreach (var item in result.Data.Items)
                {
                    Items.Add(item);
                }

                SelectedItem = Items.Count > 0 ? Items[0] : null;
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task LoadDetailAsync(OutsourceWorkGroupListItemDto? item)
        {
            if (item == null)
            {
                SelectedDetail = null;
                return;
            }

            var result = await _apiClient.GetAsync<OutsourceWorkGroupDetailDto>(
                $"{ApiRoutes.OutsourceWorkInstructionGroups}/{item.OutsourceWorkGroupId}");

            if (!result.Success || result.Data == null)
            {
                SelectedDetail = null;
                _messageService.ShowError(result.Message ?? "외주 작업지시 상세 조회 중 오류가 발생했습니다.");
                return;
            }

            SelectedDetail = result.Data;
            CancelReason = string.Empty;
        }

        private async Task CancelAsync()
        {
            if (SelectedDetail == null)
            {
                _messageService.ShowWarning("취소할 외주 작업지시를 선택하세요.");
                return;
            }

            if (!SelectedDetail.CanCancel)
            {
                _messageService.ShowWarning(SelectedDetail.CancelBlockReason ?? "취소할 수 없는 상태입니다.");
                return;
            }

            if (string.IsNullOrWhiteSpace(CancelReason))
            {
                _messageService.ShowWarning("취소 사유를 입력하세요.");
                return;
            }

            var confirmMessage =
                "선택한 외주 작업지시를 취소합니다.\n" +
                $"작업지시: {SelectedDetail.InstructionNo}\n" +
                $"LOT: {SelectedDetail.LotNosText}";

            if (!_messageService.Confirm(confirmMessage, "외주 작업지시 취소"))
            {
                return;
            }

            IsLoading = true;

            try
            {
                var request = new OutsourceWorkGroupCancelRequest
                {
                    Reason = CancelReason.Trim()
                };
                var result = await _apiClient.PostAsync<OutsourceWorkGroupCancelRequest, OutsourceWorkGroupDetailDto>(
                    $"{ApiRoutes.OutsourceWorkInstructionGroups}/{SelectedDetail.OutsourceWorkGroupId}/cancel",
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "외주 작업지시 취소 중 오류가 발생했습니다.");
                    return;
                }

                _messageService.ShowInfo("외주 작업지시가 취소되었습니다.");
                await SearchAsync();
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void LoadEditFormFromSelectedDetail()
        {
            if (SelectedDetail == null)
            {
                EditSheetQty = 0;
                EditLengthM = null;
                EditSheetCutCount = 0;
                EditFabricLotNo = string.Empty;
                EditMemo = string.Empty;
                UpdateReason = string.Empty;
                return;
            }

            EditSheetQty = SelectedDetail.SheetQty;
            EditLengthM = SelectedDetail.LengthM;
            EditSheetCutCount = SelectedDetail.SheetCutCount;
            EditFabricLotNo = SelectedDetail.FabricLotNo ?? string.Empty;
            EditMemo = SelectedDetail.Memo ?? string.Empty;
            UpdateReason = string.Empty;

        }

        private async Task SaveUpdateAsync()
        {
            if (SelectedDetail == null)
            {
                _messageService.ShowWarning("수정할 외주작업지시를 선택하세요.");
                return;
            }

            if (!CanUpdateSelectedDetail)
            {
                _messageService.ShowWarning("등록 상태의 외주작업지시만 수정할 수 있습니다.");
                return;
            }

            if (EditSheetQty <= 0 || EditSheetCutCount <= 0)
            {
                _messageService.ShowWarning("매수와 컷수는 0보다 커야 합니다.");
                return;
            }

            if (string.IsNullOrWhiteSpace(UpdateReason))
            {
                _messageService.ShowWarning("수정 사유를 입력하세요.");
                return;
            }

            if (!_messageService.Confirm(
                "외주작업지시를 수정하시겠습니까?",
                "외주작업지시 수정"))
            {
                return;
            }

            IsLoading = true;

            try
            {
                var request = new OutsourceWorkGroupUpdateRequest
                {
                    SheetQty = EditSheetQty,
                    LengthM = EditLengthM,
                    SheetCutCount = EditSheetCutCount,
                    FabricLotNo = string.IsNullOrWhiteSpace(EditFabricLotNo) ? null : EditFabricLotNo.Trim(),
                    Remark = string.IsNullOrWhiteSpace(EditMemo) ? null : EditMemo.Trim(),
                    Reason = UpdateReason.Trim()
                };

                var result = await _apiClient.PutAsync<OutsourceWorkGroupUpdateRequest, OutsourceWorkGroupDetailDto>(
                    $"{ApiRoutes.OutsourceWorkInstructionGroups}/{SelectedDetail.OutsourceWorkGroupId}",
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "외주작업지시 수정 중 오류가 발생했습니다.");
                    return;
                }

                _messageService.ShowInfo("외주작업지시가 수정되었습니다.");
                await SearchAsync();
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void Reset()
        {
            DateFrom = DateTime.Today.AddMonths(-1);
            DateTo = DateTime.Today;
            SelectedProcessType = "전체";
            SelectedStatus = "전체";
            SearchKeyword = string.Empty;
            SelectedItem = null;
            SelectedDetail = null;
            _ = SearchAsync();
        }

        private string BuildListUrl()
        {
            var query = new System.Collections.Generic.List<string>();

            if (DateFrom.HasValue)
            {
                query.Add($"date_from={DateFrom.Value:yyyy-MM-dd}");
            }

            if (DateTo.HasValue)
            {
                query.Add($"date_to={DateTo.Value:yyyy-MM-dd}");
            }

            var processType = ToProcessTypeCode(SelectedProcessType);
            if (!string.IsNullOrWhiteSpace(processType))
            {
                query.Add($"process_type={Uri.EscapeDataString(processType)}");
            }

            var status = ToStatusCode(SelectedStatus);
            if (!string.IsNullOrWhiteSpace(status))
            {
                query.Add($"status={Uri.EscapeDataString(status)}");
            }

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                query.Add($"q={Uri.EscapeDataString(SearchKeyword.Trim())}");
            }

            return query.Count > 0
                ? $"{ApiRoutes.OutsourceWorkInstructionGroups}?{string.Join("&", query)}"
                : ApiRoutes.OutsourceWorkInstructionGroups;
        }

        private static string? ToProcessTypeCode(string? displayName)
        {
            return displayName switch
            {
                "재단" => "CUT",
                "인쇄" => "PRINT",
                _ => null
            };
        }

        private static string? ToStatusCode(string? displayName)
        {
            return displayName switch
            {
                "등록" => "REGISTERED",
                "업체입고" => "VENDOR_RECEIVED",
                "작업완료" => "WORK_DONE",
                "출고완료" => "SHIPPED",
                "취소" => "CANCELED",
                _ => null
            };
        }
    }
}
