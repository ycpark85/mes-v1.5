using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.BohyunOutsourceManagement.Dtos;
using Mes.Wpf.Modules.BohyunOutsourceManagement.Views;

namespace Mes.Wpf.Modules.BohyunOutsourceManagement.ViewModels
{
    public class BohyunOutsourceManagementViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private bool _isLoading;
        private DateTime? _dateFrom;
        private DateTime? _dateTo;
        private string _selectedProcessType = "전체";
        private string _selectedStatus = "전체";
        private string _searchKeyword = string.Empty;
        private BohyunOutsourceRowModel? _selectedItem;
        private int _totalCount;
        private int _currentPage = 1;
        private int _pageSize = 100;

        public BohyunOutsourceManagementViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<BohyunOutsourceRowModel>();

            ProcessTypeOptions = new ObservableCollection<string>
            {
                "전체",
                "CUT",
                "PRINT"
            };

            StatusOptions = new ObservableCollection<string>
            {
                "전체",
                "WAITING_INBOUND",
                "INBOUNDED",
                "WORK_DONE"
            };

            SearchCommand = new AsyncRelayCommand(SearchAsync, () => !IsLoading);
            ResetCommand = new AsyncRelayCommand(ResetAsync, () => !IsLoading);
            PreviousPageCommand = new AsyncRelayCommand(GoPreviousPageAsync, () => !IsLoading && HasPreviousPage);
            NextPageCommand = new AsyncRelayCommand(GoNextPageAsync, () => !IsLoading && HasNextPage);
            InboundCompleteCommand = new AsyncRelayCommand<BohyunOutsourceRowModel>(InboundCompleteAsync, item => !IsLoading && item != null);
            WorkDoneCommand = new AsyncRelayCommand<BohyunOutsourceRowModel>(OpenWorkDoneWindowAsync, item => !IsLoading && item != null);
            ShipSelectedCommand = new AsyncRelayCommand(ShipSelectedAsync, () => !IsLoading);
        }

        public ObservableCollection<BohyunOutsourceRowModel> Items { get; }

        public ObservableCollection<string> ProcessTypeOptions { get; }

        public ObservableCollection<string> StatusOptions { get; }

        public ICommand SearchCommand { get; }

        public ICommand ResetCommand { get; }
        public ICommand PreviousPageCommand { get; }
        public ICommand NextPageCommand { get; }

        public ICommand InboundCompleteCommand { get; }

        public ICommand WorkDoneCommand { get; }

        public ICommand ShipSelectedCommand { get; }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    RaiseCommandCanExecuteChanged();
                }
            }
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

        public BohyunOutsourceRowModel? SelectedItem
        {
            get => _selectedItem;
            set => SetProperty(ref _selectedItem, value);
        }

        public int TotalCount
        {
            get => _totalCount;
            set
            {
                if (SetProperty(ref _totalCount, value))
                {
                    RaisePagePropertiesChanged();
                }
            }
        }

        public int CurrentPage
        {
            get => _currentPage;
            private set
            {
                if (SetProperty(ref _currentPage, value))
                {
                    RaisePagePropertiesChanged();
                }
            }
        }

        public int PageSize
        {
            get => _pageSize;
            private set
            {
                if (SetProperty(ref _pageSize, value))
                {
                    RaisePagePropertiesChanged();
                }
            }
        }

        public int TotalPages => Math.Max(1, (int)Math.Ceiling(TotalCount / (double)Math.Max(PageSize, 1)));
        public bool HasPreviousPage => CurrentPage > 1;
        public bool HasNextPage => CurrentPage < TotalPages;
        public string PageDisplayText => $"{CurrentPage} / {TotalPages} (총 {TotalCount:N0}건)";

        public async Task InitializeAsync()
        {
            DateFrom = DateTime.Today.AddMonths(-1);
            DateTo = DateTime.Today;

            await SearchAsync();
        }

        public async Task SearchAsync()
        {
            CurrentPage = 1;
            await LoadAsync();
        }

        private async Task LoadAsync()
        {
            try
            {
                IsLoading = true;

                var result = await _apiClient.GetAsync<BohyunOutsourceListDto>(BuildListUrl());

                if (!result.Success || result.Data == null)
                {
                    Items.Clear();
                    SelectedItem = null;
                    TotalCount = 0;

                    _messageService.ShowError(result.Message ?? "보현문화 외주 대상 조회에 실패했습니다.");
                    return;
                }

                Items.Clear();

                foreach (var item in result.Data.Items)
                {
                    Items.Add(BohyunOutsourceRowModel.FromDto(item));
                }

                SelectedItem = null;
                TotalCount = result.Data.TotalCount;
                CurrentPage = result.Data.Page;
                PageSize = result.Data.Size;
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task GoPreviousPageAsync()
        {
            if (!HasPreviousPage)
            {
                return;
            }

            CurrentPage--;
            await LoadAsync();
        }

        private async Task GoNextPageAsync()
        {
            if (!HasNextPage)
            {
                return;
            }

            CurrentPage++;
            await LoadAsync();
        }

        private async Task ResetAsync()
        {
            DateFrom = DateTime.Today.AddMonths(-1);
            DateTo = DateTime.Today;
            SelectedProcessType = "전체";
            SelectedStatus = "전체";
            SearchKeyword = string.Empty;
            SelectedItem = null;

            await SearchAsync();
        }

        private async Task InboundCompleteAsync(BohyunOutsourceRowModel? item)
        {
            if (item == null)
            {
                return;
            }

            if (!item.CanInbound)
            {
                _messageService.ShowWarning("입고대기 상태만 입고완료 처리할 수 있습니다.");
                return;
            }

            var confirm = _messageService.Confirm(
                $"작업지시 [{item.InstructionNo}] {item.WorkTypeName} 작업을 입고완료 처리하시겠습니까?");

            if (!confirm)
            {
                return;
            }

            try
            {
                IsLoading = true;

                var url = $"{ApiRoutes.BohyunOutsourceGroups}/{item.OutsourceWorkGroupId}/inbound";
                var result = await _apiClient.PostAsync<object, object>(url, new { });

                if (!result.Success)
                {
                    _messageService.ShowError(result.Message ?? "입고완료 처리에 실패했습니다.");
                    return;
                }

                _messageService.ShowInfo("입고완료 처리되었습니다.");
                SelectedStatus = "전체";
                await SearchAsync();
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task OpenWorkDoneWindowAsync(BohyunOutsourceRowModel? item)
        {
            if (item == null)
            {
                return;
            }

            if (!item.CanWorkDone)
            {
                _messageService.ShowWarning("입고완료 상태만 작업완료 처리할 수 있습니다.");
                return;
            }

            var viewModel = new BohyunOutsourceWorkDoneWindowViewModel(
                _apiClient,
                _messageService,
                item);

            var window = new BohyunOutsourceWorkDoneWindow(viewModel)
            {
                Owner = Application.Current.MainWindow
            };

            var result = window.ShowDialog();

            if (result == true)
            {
                SelectedStatus = "전체";
                await SearchAsync();
            }
        }

        private async Task ShipSelectedAsync()
        {
            var checkedItems = Items
                .Where(x => x.IsChecked)
                .ToList();

            if (checkedItems.Count == 0)
            {
                _messageService.ShowWarning("출고 처리할 항목을 선택해주세요.");
                return;
            }

            var invalidItems = checkedItems
                .Where(x => !x.CanShip)
                .ToList();

            if (invalidItems.Count > 0)
            {
                _messageService.ShowWarning("작업완료 상태만 출고 처리할 수 있습니다.");
                return;
            }

            var confirm = _messageService.Confirm(
                $"선택한 {checkedItems.Count}건을 출고 처리하시겠습니까?");

            if (!confirm)
            {
                return;
            }

            try
            {
                IsLoading = true;

                var request = new BohyunOutsourceShipRequest
                {
                    GroupIds = checkedItems
                        .Select(x => x.OutsourceWorkGroupId)
                        .ToList()
                };

                var url = $"{ApiRoutes.BohyunOutsourceGroups}/ship-batch";
                var result = await _apiClient.PostAsync<BohyunOutsourceShipRequest, object>(url, request);

                if (!result.Success)
                {
                    _messageService.ShowError(result.Message ?? "출고 처리에 실패했습니다.");
                    return;
                }

                _messageService.ShowInfo("출고 처리되었습니다.");

                await SearchAsync();
            }
            finally
            {
                IsLoading = false;
            }
        }

        private string BuildListUrl()
        {
            NormalizeSearchConditions();

            var queryParts = new List<string>();

            if (DateFrom.HasValue)
            {
                queryParts.Add($"date_from={DateFrom.Value:yyyy-MM-dd}");
            }

            if (DateTo.HasValue)
            {
                queryParts.Add($"date_to={DateTo.Value:yyyy-MM-dd}");
            }

            if (!string.IsNullOrWhiteSpace(SelectedProcessType) && SelectedProcessType != "전체")
            {
                queryParts.Add($"process_type={Uri.EscapeDataString(SelectedProcessType)}");
            }

            if (!string.IsNullOrWhiteSpace(SelectedStatus) && SelectedStatus != "전체")
            {
                queryParts.Add($"status={Uri.EscapeDataString(SelectedStatus)}");
            }

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(SearchKeyword)}");
            }

            queryParts.Add($"page={CurrentPage}");
            queryParts.Add($"size={PageSize}");

            if (queryParts.Count == 0)
            {
                return ApiRoutes.BohyunOutsourceGroups;
            }

            return $"{ApiRoutes.BohyunOutsourceGroups}?{string.Join("&", queryParts)}";
        }

        private void NormalizeSearchConditions()
        {
            SearchKeyword = SearchKeyword?.Trim() ?? string.Empty;
            SelectedProcessType = SelectedProcessType?.Trim().ToUpperInvariant() ?? "전체";
            SelectedStatus = SelectedStatus?.Trim().ToUpperInvariant() ?? "전체";
        }

        private void RaiseCommandCanExecuteChanged()
        {
            if (SearchCommand is AsyncRelayCommand searchCommand)
            {
                searchCommand.RaiseCanExecuteChanged();
            }

            if (ResetCommand is AsyncRelayCommand resetCommand)
            {
                resetCommand.RaiseCanExecuteChanged();
            }

            if (InboundCompleteCommand is AsyncRelayCommand<BohyunOutsourceRowModel> inboundCommand)
            {
                inboundCommand.RaiseCanExecuteChanged();
            }

            if (WorkDoneCommand is AsyncRelayCommand<BohyunOutsourceRowModel> workDoneCommand)
            {
                workDoneCommand.RaiseCanExecuteChanged();
            }

            if (ShipSelectedCommand is AsyncRelayCommand shipCommand)
            {
                shipCommand.RaiseCanExecuteChanged();
            }

            if (PreviousPageCommand is AsyncRelayCommand previousPageCommand)
            {
                previousPageCommand.RaiseCanExecuteChanged();
            }

            if (NextPageCommand is AsyncRelayCommand nextPageCommand)
            {
                nextPageCommand.RaiseCanExecuteChanged();
            }
        }

        private void RaisePagePropertiesChanged()
        {
            OnPropertyChanged(nameof(TotalPages));
            OnPropertyChanged(nameof(HasPreviousPage));
            OnPropertyChanged(nameof(HasNextPage));
            OnPropertyChanged(nameof(PageDisplayText));
            RaiseCommandCanExecuteChanged();
        }
    }

}
