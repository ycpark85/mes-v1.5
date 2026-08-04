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
using Mes.Wpf.Modules.InspectionSchedules.Dtos;
using Mes.Wpf.Modules.InspectionSchedules.Views;

namespace Mes.Wpf.Modules.InspectionSchedules.ViewModels
{
    public class InspectionResultManagementPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly bool _canWriteInspection;

        private bool _isLoading;
        private DateTime? _dateFrom = DateTime.Today.AddMonths(-1);
        private DateTime? _dateTo = DateTime.Today;
        private string _searchKeyword = string.Empty;
        private InspectionResultManagementItemDto? _selectedItem;
        private int _currentPage = 1;
        private int _pageSize = 100;
        private int _totalCount;
        private int _totalGoodQty;
        private int _totalUninspectedQty;
        private int _totalReceivedQty;
        private int _totalResultShipQty;
        private int _totalDiscardQty;
        private int _totalStockInQty;
        private int _totalDefectQty;

        public InspectionResultManagementPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            bool canWriteInspection)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _canWriteInspection = canWriteInspection;

            Items = new ObservableCollection<InspectionResultManagementItemDto>();

            RefreshCommand = new AsyncRelayCommand(SearchAsync, () => !IsLoading);
            ResetCommand = new AsyncRelayCommand(ResetAsync, () => !IsLoading);
            PreviousPageCommand = new AsyncRelayCommand(GoPreviousPageAsync, () => !IsLoading && HasPreviousPage);
            NextPageCommand = new AsyncRelayCommand(GoNextPageAsync, () => !IsLoading && HasNextPage);
            OpenDetailCommand = new AsyncRelayCommand(OpenDetailAsync, () => !IsLoading && SelectedItem != null);
        }

        public ObservableCollection<InspectionResultManagementItemDto> Items { get; }

        public ICommand RefreshCommand { get; }
        public ICommand ResetCommand { get; }
        public ICommand PreviousPageCommand { get; }
        public ICommand NextPageCommand { get; }
        public ICommand OpenDetailCommand { get; }

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

        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public InspectionResultManagementItemDto? SelectedItem
        {
            get => _selectedItem;
            set
            {
                if (SetProperty(ref _selectedItem, value))
                {
                    RaiseCommandCanExecuteChanged();
                }
            }
        }

        public int TotalCount
        {
            get => _totalCount;
            set => SetProperty(ref _totalCount, value);
        }

        public int CurrentPage
        {
            get => _currentPage;
            set
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
            set
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
        public string PageDisplayText => $"{CurrentPage} / {TotalPages}";

        public int TotalGoodQty
        {
            get => _totalGoodQty;
            set => SetProperty(ref _totalGoodQty, value);
        }

        public int TotalUninspectedQty
        {
            get => _totalUninspectedQty;
            set => SetProperty(ref _totalUninspectedQty, value);
        }

        public int TotalReceivedQty
        {
            get => _totalReceivedQty;
            set => SetProperty(ref _totalReceivedQty, value);
        }

        public int TotalResultShipQty
        {
            get => _totalResultShipQty;
            set => SetProperty(ref _totalResultShipQty, value);
        }

        public int TotalDiscardQty
        {
            get => _totalDiscardQty;
            set => SetProperty(ref _totalDiscardQty, value);
        }

        public int TotalStockInQty
        {
            get => _totalStockInQty;
            set => SetProperty(ref _totalStockInQty, value);
        }

        public int TotalDefectQty
        {
            get => _totalDefectQty;
            set => SetProperty(ref _totalDefectQty, value);
        }

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        private async Task SearchAsync()
        {
            CurrentPage = 1;
            await LoadAsync();
        }

        public async Task LoadAsync()
        {
            try
            {
                IsLoading = true;

                var result = await _apiClient.GetAsync<InspectionResultManagementListDto>(BuildListUrl());
                if (!result.Success || result.Data == null)
                {
                    Items.Clear();
                    SelectedItem = null;
                    UpdateTotals(null);
                    _messageService.ShowError(result.Message ?? "검수실적 목록 조회에 실패했습니다.");
                    return;
                }

                var selectedId = SelectedItem?.InspectionResultId;

                Items.Clear();
                CurrentPage = result.Data.Page;
                PageSize = result.Data.Size;
                var rowNo = ((CurrentPage - 1) * PageSize) + 1;
                foreach (var item in result.Data.Items)
                {
                    item.RowNo = rowNo++;
                    Items.Add(item);
                }

                SelectedItem = selectedId.HasValue
                    ? Items.FirstOrDefault(x => x.InspectionResultId == selectedId.Value)
                    : null;

                UpdateTotals(result.Data);
            }
            finally
            {
                IsLoading = false;
            }
        }

        public Task ResetAsync()
        {
            DateFrom = DateTime.Today.AddMonths(-1);
            DateTo = DateTime.Today;
            SearchKeyword = string.Empty;
            SelectedItem = null;
            CurrentPage = 1;

            return LoadAsync();
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

        public async Task OpenDetailAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("검수실적을 선택해주세요.");
                return;
            }

            var windowVm = new InspectionResultWindowViewModel(
                _apiClient,
                _messageService,
                canEdit: false,
                canRequestEdit: _canWriteInspection);
            await windowVm.InitializeAsync(
                SelectedItem.InspectionScheduleId,
                SelectedItem.LotNo,
                SelectedItem.ProductName,
                SelectedItem.PartnerName,
                SelectedItem.InspectionDate,
                SelectedItem.LotQty,
                SelectedItem.DueDate,
                SelectedItem.OrderQty);

            var window = new InspectionResultWindow(windowVm)
            {
                Owner = Application.Current?.MainWindow,
                Title = "검수실적 상세보기"
            };

            var dialogResult = window.ShowDialog();
            if (dialogResult == true)
            {
                await LoadAsync();
            }
        }

        private string BuildListUrl()
        {
            var queryParts = new List<string>();

            if (DateFrom.HasValue)
            {
                queryParts.Add($"date_from={DateFrom.Value:yyyy-MM-dd}");
            }

            if (DateTo.HasValue)
            {
                queryParts.Add($"date_to={DateTo.Value:yyyy-MM-dd}");
            }

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(SearchKeyword.Trim())}");
            }

            queryParts.Add($"page={CurrentPage}");
            queryParts.Add($"size={PageSize}");

            return queryParts.Count == 0
                ? ApiRoutes.InspectionResults
                : $"{ApiRoutes.InspectionResults}?{string.Join("&", queryParts)}";
        }

        private void UpdateTotals(InspectionResultManagementListDto? result)
        {
            TotalCount = result?.TotalCount ?? 0;
            TotalGoodQty = result?.TotalGoodQty ?? 0;
            TotalUninspectedQty = result?.TotalUninspectedQty ?? 0;
            TotalReceivedQty = result?.TotalReceivedQty ?? 0;
            TotalResultShipQty = result?.TotalResultShipQty ?? 0;
            TotalDiscardQty = (result?.TotalDiscardQty ?? 0) + TotalUninspectedQty;
            TotalStockInQty = result?.TotalStockInQty ?? 0;
            TotalDefectQty = result?.TotalDefectQty ?? 0;
            RaisePagePropertiesChanged();
        }

        private void RaisePagePropertiesChanged()
        {
            OnPropertyChanged(nameof(TotalPages));
            OnPropertyChanged(nameof(HasPreviousPage));
            OnPropertyChanged(nameof(HasNextPage));
            OnPropertyChanged(nameof(PageDisplayText));
            RaiseCommandCanExecuteChanged();
        }

        private void RaiseCommandCanExecuteChanged()
        {
            if (RefreshCommand is AsyncRelayCommand refreshCommand)
            {
                refreshCommand.RaiseCanExecuteChanged();
            }

            if (ResetCommand is AsyncRelayCommand resetCommand)
            {
                resetCommand.RaiseCanExecuteChanged();
            }

            if (OpenDetailCommand is AsyncRelayCommand openDetailCommand)
            {
                openDetailCommand.RaiseCanExecuteChanged();
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
    }
}
