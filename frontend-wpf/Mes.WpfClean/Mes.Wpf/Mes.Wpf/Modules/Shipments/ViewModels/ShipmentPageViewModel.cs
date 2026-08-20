using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Shipments.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Shipments.ViewModels
{
    public class ShipmentPageViewModel : CrudPageViewModelBase<ShipmentDisplayItemDto>
    {
        private const string ShipmentStatusWaiting = "WAITING";
        private const string ShipmentStatusDone = "DONE";

        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private readonly Func<long, Task>? _openOrderDetailWindowAsync;
        private readonly Func<long, Task>? _openLotCertificateWindowAsync;
        private readonly Func<ShipmentDisplayItemDto, Task>? _openCoaAsync;

        private string _selectedShipmentStatus = ShipmentStatusWaiting;
        private string _searchKeyword = string.Empty;
        private int _page = 1;
        private int _size = 50;
        private int _total;
        private bool _canGoPreviousPage;
        private bool _canGoNextPage;
        private DateTime? _shippedDateFrom;
        private DateTime? _shippedDateTo;

        public ShipmentPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            Func<long, Task>? openOrderDetailWindowAsync = null,
            Func<long, Task>? openLotCertificateWindowAsync = null,
            Func<ShipmentDisplayItemDto, Task>? openCoaAsync = null)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _openOrderDetailWindowAsync = openOrderDetailWindowAsync;
            _openLotCertificateWindowAsync = openLotCertificateWindowAsync;
            _openCoaAsync = openCoaAsync;

            Items = new ObservableCollection<ShipmentDisplayItemDto>();

            ShippedDateTo = DateTime.Today;
            ShippedDateFrom = DateTime.Today.AddMonths(-2);

            ShowWaitingCommand = new AsyncRelayCommand(async () =>
            {
                await ChangeShipmentStatusAsync(ShipmentStatusWaiting);
            });

            ShowDoneCommand = new AsyncRelayCommand(async () =>
            {
                await ChangeShipmentStatusAsync(ShipmentStatusDone);
            });

            ConfirmSelectedCommand = new AsyncRelayCommand(ConfirmSelectedAsync);

            SelectAllCommand = new RelayCommand(_ => SelectAll());
            ClearSelectionCommand = new RelayCommand(_ => ClearSelection());

            OpenOrderDetailCommand = new AsyncRelayCommand(OpenOrderDetailAsync);
            OpenStockLotCertificateCommand = new AsyncRelayCommand(OpenStockLotCertificateAsync);
            OpenProductionLotCertificateCommand = new AsyncRelayCommand(OpenProductionLotCertificateAsync);
            OpenCoaCommand = new AsyncRelayCommand(OpenCoaAsync);

            PreviousPageCommand = new AsyncRelayCommand(GoPreviousPageAsync);
            NextPageCommand = new AsyncRelayCommand(GoNextPageAsync);
        }

        public ObservableCollection<ShipmentDisplayItemDto> Items { get; }

        public AsyncRelayCommand ShowWaitingCommand { get; }

        public AsyncRelayCommand ShowDoneCommand { get; }

        public AsyncRelayCommand ConfirmSelectedCommand { get; }

        public RelayCommand SelectAllCommand { get; }

        public RelayCommand ClearSelectionCommand { get; }

        public AsyncRelayCommand OpenOrderDetailCommand { get; }

        public AsyncRelayCommand OpenStockLotCertificateCommand { get; }

        public AsyncRelayCommand OpenProductionLotCertificateCommand { get; }

        public AsyncRelayCommand OpenCoaCommand { get; }

        public AsyncRelayCommand PreviousPageCommand { get; }

        public AsyncRelayCommand NextPageCommand { get; }

        public string SelectedShipmentStatus
        {
            get => _selectedShipmentStatus;
            set
            {
                if (SetProperty(ref _selectedShipmentStatus, value))
                {
                    OnPropertyChanged(nameof(IsWaitingTab));
                    OnPropertyChanged(nameof(IsDoneTab));
                    OnPropertyChanged(nameof(IsConfirmEnabled));
                    OnPropertyChanged(nameof(CurrentTabTitle));
                    OnPropertyChanged(nameof(IsWaitingActionVisible));
                    OnPropertyChanged(nameof(IsDoneActionVisible));
                    OnPropertyChanged(nameof(IsDoneDateFilterVisible));
                }
            }
        }

        public bool IsWaitingTab => SelectedShipmentStatus == ShipmentStatusWaiting;

        public bool IsDoneTab => SelectedShipmentStatus == ShipmentStatusDone;

        public bool IsWaitingActionVisible => IsWaitingTab;

        public bool IsDoneActionVisible => IsDoneTab;

        public bool IsDoneDateFilterVisible => IsDoneTab;

        public bool IsConfirmEnabled => IsWaitingTab && Items.Any(x => x.IsSelected);

        public string CurrentTabTitle => IsDoneTab
            ? "출하관리 - 출하완료"
            : "출하관리 - 출하대기";

        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public DateTime? ShippedDateFrom
        {
            get => _shippedDateFrom;
            set => SetProperty(ref _shippedDateFrom, value);
        }

        public DateTime? ShippedDateTo
        {
            get => _shippedDateTo;
            set => SetProperty(ref _shippedDateTo, value);
        }

        public int DisplayedCount => Items.Count;

        public string ListSummaryText =>
            $"표시 {DisplayedCount:N0}건 / 원본 {Total:N0}건    {PageInfoText}";

        public int Page
        {
            get => _page;
            set
            {
                if (SetProperty(ref _page, value))
                {
                    OnPropertyChanged(nameof(PageInfoText));
                    OnPropertyChanged(nameof(ListSummaryText));
                }
            }
        }

        public int Size
        {
            get => _size;
            set
            {
                if (SetProperty(ref _size, value))
                {
                    OnPropertyChanged(nameof(PageInfoText));
                    OnPropertyChanged(nameof(ListSummaryText));
                }
            }
        }

        public int Total
        {
            get => _total;
            set
            {
                if (SetProperty(ref _total, value))
                {
                    OnPropertyChanged(nameof(PageInfoText));
                    OnPropertyChanged(nameof(TotalCountText));
                    OnPropertyChanged(nameof(ListSummaryText));
                }
            }
        }

        public bool CanGoPreviousPage
        {
            get => _canGoPreviousPage;
            set => SetProperty(ref _canGoPreviousPage, value);
        }

        public bool CanGoNextPage
        {
            get => _canGoNextPage;
            set => SetProperty(ref _canGoNextPage, value);
        }

        public int SelectedCount => Items.Count(x => x.IsSelected);

        public string SelectedCountText => $"선택 {SelectedCount:N0}건";

        public string PageInfoText =>
            $"{Page} / {Math.Max(1, (int)Math.Ceiling((double)Math.Max(Total, 1) / Math.Max(Size, 1)))} 페이지";

        public string TotalCountText => $"총 {Total:N0}건";

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();

            var result = await _apiClient.GetAsync<ShipmentLineListResponse>(route);

            if (!result.Success || result.Data == null)
            {
                Items.Clear();
                Total = 0;
                CanGoPreviousPage = false;
                CanGoNextPage = false;

                _messageService.ShowError(result.Message ?? "출하 목록 조회 중 오류가 발생했습니다.");
                return false;
            }

            Items.Clear();

            var groupedItems = result.Data.Items
                .GroupBy(x => x.OrderLineId)
                .Select(group =>
                {
                    var first = group.First();

                    var stockLines = group
                        .Where(x => x.SourceType == "STOCK")
                        .ToList();

                    var productionLines = group
                        .Where(x => x.SourceType == "INSPECTION_RESULT")
                        .ToList();

                    var display = new ShipmentDisplayItemDto
                    {
                        OrderLineId = first.OrderLineId,
                        OrderNo = first.OrderNo,
                        PartnerName = first.PartnerName,
                        ProductCode = first.ProductCode,
                        ProductName = first.ProductName,
                        Status = first.Status,

                        ShippedDate = group
                            .Where(x => x.ShippedAt.HasValue)
                            .OrderByDescending(x => x.ShippedAt)
                            .Select(x => x.ShippedAt)
                            .FirstOrDefault(),

                        StockShipQty = stockLines.Sum(x => x.Status == ShipmentStatusDone ? x.ShippedQty : x.ShipQty),
                        ProductionShipQty = productionLines.Sum(x => x.Status == ShipmentStatusDone ? x.ShippedQty : x.ShipQty),

                        StockLotNos = string.Join(", ",
                            stockLines
                                .Select(x => x.LotNo)
                                .Where(x => !string.IsNullOrWhiteSpace(x))
                                .Distinct()),

                        ProductionLotNos = string.Join(", ",
                            productionLines
                                .Select(x => x.LotNo)
                                .Where(x => !string.IsNullOrWhiteSpace(x))
                                .Distinct()),

                        Lines = new ObservableCollection<ShipmentLineDto>(group)
                    };

                    return display;
                })
                .ToList();

            foreach (var item in groupedItems)
            {
                item.PropertyChanged += (_, e) =>
                {
                    if (e.PropertyName == nameof(ShipmentDisplayItemDto.IsSelected))
                    {
                        RaiseSelectionPropertiesChanged();
                    }
                };

                Items.Add(item);
            }

            Page = result.Data.Page;
            Size = result.Data.Size;
            Total = result.Data.Total;

            CanGoPreviousPage = Page > 1;
            CanGoNextPage = Page * Size < Total;

            RaiseSelectionPropertiesChanged();
            OnPropertyChanged(nameof(PageInfoText));
            OnPropertyChanged(nameof(TotalCountText));
            OnPropertyChanged(nameof(DisplayedCount));
            OnPropertyChanged(nameof(ListSummaryText));
            return true;
        }

        protected override void Reset()
        {
            SearchKeyword = string.Empty;
            Page = 1;
            Size = 50;
            Total = 0;
            SelectedItem = null;
            ClearSelection();

            if (IsDoneTab)
            {
                ShippedDateTo = DateTime.Today;
                ShippedDateFrom = DateTime.Today.AddMonths(-2);
            }
            else
            {
                ShippedDateFrom = null;
                ShippedDateTo = null;
            }

            OnPropertyChanged(nameof(PageInfoText));
            OnPropertyChanged(nameof(TotalCountText));
        }

        protected override void New()
        {
        }

        protected override void OnSelectedItemChanged(ShipmentDisplayItemDto? item)
        {
        }

        private async Task ChangeShipmentStatusAsync(string targetStatus)
        {
            if (SelectedShipmentStatus == targetStatus)
            {
                return;
            }

            SelectedShipmentStatus = targetStatus;
            SearchKeyword = string.Empty;
            Page = 1;
            SelectedItem = null;
            ClearSelection();

            if (targetStatus == ShipmentStatusDone)
            {
                ShippedDateTo = DateTime.Today;
                ShippedDateFrom = DateTime.Today.AddMonths(-2);
            }
            else
            {
                ShippedDateFrom = null;
                ShippedDateTo = null;
            }

            await SearchAsync();
        }

        private async Task ConfirmSelectedAsync()
        {
            if (!IsWaitingTab)
            {
                _messageService.ShowWarning("출하확정은 출하대기 탭에서만 가능합니다.");
                return;
            }

            var selectedIds = Items
                .Where(x => x.IsSelected)
                .SelectMany(x => x.Lines)
                .Select(x => x.ShipmentLineId)
                .Distinct()
                .ToList();

            if (selectedIds.Count == 0)
            {
                _messageService.ShowWarning("출하확정할 항목을 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"선택한 {selectedIds.Count:N0}건을 출하확정 처리하시겠습니까?\n출하확정 시 실제 재고가 차감됩니다.",
                "출하확정 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;

            try
            {
                var request = new ShipmentConfirmRequest
                {
                    ShipmentLineIds = new ObservableCollection<int>(selectedIds)
                };

                var route = $"{ApiRoutes.Shipments}/confirm";

                var result = await _apiClient.PostAsync<ShipmentConfirmRequest, ShipmentConfirmResponse>(
                    route,
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "출하확정 처리 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();

                _messageService.ShowInfo($"{result.Data.ConfirmedCount:N0}건 출하확정 처리되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void SelectAll()
        {
            if (!IsWaitingTab)
            {
                return;
            }

            foreach (var item in Items)
            {
                item.IsSelected = true;
            }

            RaiseSelectionPropertiesChanged();
        }

        private void ClearSelection()
        {
            foreach (var item in Items)
            {
                item.IsSelected = false;
            }

            RaiseSelectionPropertiesChanged();
        }

        private ShipmentDisplayItemDto? GetSingleSelectedDoneItem()
        {
            if (!IsDoneTab)
            {
                _messageService.ShowWarning("출하완료 탭에서만 사용할 수 있습니다.");
                return null;
            }

            if (SelectedItem == null)
            {
                _messageService.ShowWarning("항목을 선택하세요.");
                return null;
            }

            return SelectedItem;
        }

        private async Task OpenOrderDetailAsync()
        {
            var item = GetSingleSelectedDoneItem();

            if (item == null)
            {
                return;
            }

            if (_openOrderDetailWindowAsync == null)
            {
                _messageService.ShowWarning("수주상세 화면 연결이 설정되지 않았습니다.");
                return;
            }

            await _openOrderDetailWindowAsync(item.OrderLineId);
        }

        private async Task OpenStockLotCertificateAsync()
        {
            var item = SelectedItem;

            if (item == null)
            {
                _messageService.ShowWarning("항목을 선택하세요.");
                return;
            }

            var stockLot = item.Lines
                .FirstOrDefault(x => x.SourceType == "STOCK" && x.LotId.HasValue);

            if (stockLot == null || !stockLot.LotId.HasValue)
            {
                _messageService.ShowWarning("성적서를 출력할 재고 LOT가 없습니다.");
                return;
            }

            if (_openLotCertificateWindowAsync == null)
            {
                _messageService.ShowWarning("성적서 화면 연결이 설정되지 않았습니다.");
                return;
            }

            await _openLotCertificateWindowAsync(stockLot.LotId.Value);
        }

        private async Task OpenProductionLotCertificateAsync()
        {
            var item = SelectedItem;

            if (item == null)
            {
                _messageService.ShowWarning("항목을 선택하세요.");
                return;
            }

            var productionLot = item.Lines
                .FirstOrDefault(x => x.SourceType == "INSPECTION_RESULT" && x.LotId.HasValue);

            if (productionLot == null || !productionLot.LotId.HasValue)
            {
                _messageService.ShowWarning("성적서를 출력할 생산 LOT가 없습니다.");
                return;
            }

            if (_openLotCertificateWindowAsync == null)
            {
                _messageService.ShowWarning("성적서 화면 연결이 설정되지 않았습니다.");
                return;
            }

            await _openLotCertificateWindowAsync(productionLot.LotId.Value);
        }

        private async Task OpenCoaAsync()
        {
            var item = GetSingleSelectedDoneItem();

            if (item == null)
            {
                return;
            }

            if (_openCoaAsync == null)
            {
                _messageService.ShowInfo("COA 기능은 아직 미구현입니다.");
                return;
            }

            await _openCoaAsync(item);
        }

        private void RaiseSelectionPropertiesChanged()
        {
            OnPropertyChanged(nameof(SelectedCount));
            OnPropertyChanged(nameof(SelectedCountText));
            OnPropertyChanged(nameof(IsConfirmEnabled));
            OnPropertyChanged(nameof(DisplayedCount));
            OnPropertyChanged(nameof(ListSummaryText));
        }

        private string BuildListUrl()
        {
            var page = Page <= 0 ? 1 : Page;
            var size = Size <= 0 ? 50 : Size;

            var queryParts = new List<string>
            {
                $"status={Uri.EscapeDataString(SelectedShipmentStatus)}",
                $"page={page}",
                $"size={size}"
            };

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(SearchKeyword.Trim())}");
            }

            if (IsDoneTab)
            {
                if (ShippedDateFrom.HasValue)
                {
                    queryParts.Add($"shipped_from={Uri.EscapeDataString(ShippedDateFrom.Value.ToString("yyyy-MM-dd"))}");
                }

                if (ShippedDateTo.HasValue)
                {
                    queryParts.Add($"shipped_to={Uri.EscapeDataString(ShippedDateTo.Value.ToString("yyyy-MM-dd"))}");
                }
            }

            return $"{ApiRoutes.Shipments}?{string.Join("&", queryParts)}";
        }

        private async Task GoPreviousPageAsync()
        {
            if (!CanGoPreviousPage)
            {
                return;
            }

            Page--;
            await SearchAsync();
        }

        private async Task GoNextPageAsync()
        {
            if (!CanGoNextPage)
            {
                return;
            }

            Page++;
            await SearchAsync();
        }
    }
}
