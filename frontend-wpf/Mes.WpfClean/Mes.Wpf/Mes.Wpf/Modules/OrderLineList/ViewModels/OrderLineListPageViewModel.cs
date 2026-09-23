using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.OrderLineList.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.OrderLineList.ViewModels
{
    public class OrderLineListPageViewModel : CrudPageViewModelBase<OrderLineListItemDto>
    {
        private const string ProductionTabInProgress = "IN_PROGRESS";
        private const string ProductionTabCompleted = "COMPLETED";

        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly Func<long, Task>? _openDetailAsync;
        private readonly Func<OrderLineListItemDto, Task>? _openLotCreateAsync;

        private string _searchKeyword = string.Empty;
        private string _selectedProductionTab = ProductionTabInProgress;

        private int _page = 1;
        private int _size = 20;
        private int _total;

        private DateTime? _orderDateFrom;
        private DateTime? _orderDateTo;

        private bool _canGoPreviousPage;
        private bool _canGoNextPage;

        private bool _canCreateBaseLot;
        private bool _canShortClose;

        private string _selectedPlanType = string.Empty;
        private string _planMemo = string.Empty;
        private bool _canConfirmPlan;
        private string? _selectedWorkQueue;
        private int? _lotCreationCount;
        private int? _closeDecisionCount;
        private bool _isWorking;
        private bool _preserveRows;

        public event Action? ItemsRefreshing;
        public event Action? ItemsRefreshed;
        public bool IsInteractionEnabled => !_isWorking;
        public bool IsLotCreationQueue => _selectedWorkQueue == "LOT_CREATION";
        public bool IsCloseDecisionQueue => _selectedWorkQueue == "CLOSE_DECISION";
        public string LotCreationButtonText => $"LOT 생성 대기 ({(_lotCreationCount is int count ? count.ToString("N0") : "미조회")})";
        public string CloseDecisionButtonText => $"종료판단대기 ({(_closeDecisionCount is int count ? count.ToString("N0") : "미조회")})";
        public bool CanReopen => IsCompletedTab && SelectedItem?.ManualClosed == true;

        private readonly List<AsyncRelayCommand> _commands = new();
        private AsyncRelayCommand BusyCommand(Func<Task> action, Func<bool>? canExecute = null)
        {
            var command = new AsyncRelayCommand(() => RunBusyAsync(action), () => !_isWorking && (canExecute?.Invoke() ?? true));
            _commands.Add(command);
            return command;
        }

        private async Task RunBusyAsync(Func<Task> action)
        {
            if (_isWorking) return;
            _isWorking = true;
            OnPropertyChanged(nameof(IsInteractionEnabled));
            try { await action(); }
            finally
            {
                _isWorking = false;
                OnPropertyChanged(nameof(IsInteractionEnabled));
                foreach (var command in _commands) command.RaiseCanExecuteChanged();
            }
        }

        private void SetWorkQueue(string? value)
        {
            _selectedWorkQueue = value;
            OnPropertyChanged(nameof(IsLotCreationQueue));
            OnPropertyChanged(nameof(IsCloseDecisionQueue));
        }

        private async Task ToggleWorkQueueAsync(string queue)
        {
            SetWorkQueue(_selectedWorkQueue == queue ? null : queue);
            Page = 1;
            SelectedItem = null;
            await SearchAsync();
        }

        public OrderLineListPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            Func<long, Task>? openDetailAsync = null,
            Func<OrderLineListItemDto, Task>? openLotCreateAsync = null)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _openDetailAsync = openDetailAsync;
            _openLotCreateAsync = openLotCreateAsync;

            Items = new ObservableCollection<OrderLineListItemDto>();
            PlanOptions = new ObservableCollection<KeyValuePair<string, string>>();

            SearchOrderLinesCommand = BusyCommand(async () =>
            {
                Page = 1;
                await SearchAsync();
            });

            ResetOrderLineSearchCommand = BusyCommand(async () =>
            {
                Reset();
                await SearchAsync();
            });

            ShowInProgressCommand = BusyCommand(async () =>
            {
                await ChangeProductionTabAsync(ProductionTabInProgress);
            });

            ShowCompletedCommand = BusyCommand(async () =>
            {
                await ChangeProductionTabAsync(ProductionTabCompleted);
            });

            CreateBaseLotCommand = BusyCommand(CreateBaseLotAsync);
            ShortCloseCommand = BusyCommand(ShortCloseAsync);
            ReopenCommand = BusyCommand(ReopenAsync);
            ShowLotCreationQueueCommand = BusyCommand(() => ToggleWorkQueueAsync("LOT_CREATION"));
            ShowCloseDecisionQueueCommand = BusyCommand(() => ToggleWorkQueueAsync("CLOSE_DECISION"));
            ConfirmPlanCommand = BusyCommand(ConfirmPlanAsync);
            OpenOrderDetailCommand = BusyCommand(OpenOrderDetailAsync);
            OpenLotActionCommand = BusyCommand(OpenLotActionAsync);
            DeleteOrderGroupCommand = BusyCommand(DeleteOrderGroupAsync);
            PreviousPageCommand = BusyCommand(
                GoPreviousPageAsync,
                () => CanGoPreviousPage);

            NextPageCommand = BusyCommand(
                GoNextPageAsync,
                () => CanGoNextPage);


        }

        public ObservableCollection<OrderLineListItemDto> Items { get; }
        public ObservableCollection<KeyValuePair<string, string>> PlanOptions { get; }

        public AsyncRelayCommand SearchOrderLinesCommand { get; }
        public AsyncRelayCommand ResetOrderLineSearchCommand { get; }

        public AsyncRelayCommand ShowInProgressCommand { get; }
        public AsyncRelayCommand ShowCompletedCommand { get; }

        public AsyncRelayCommand CreateBaseLotCommand { get; }
        public AsyncRelayCommand ShortCloseCommand { get; }
        public AsyncRelayCommand ReopenCommand { get; }
        public AsyncRelayCommand ShowLotCreationQueueCommand { get; }
        public AsyncRelayCommand ShowCloseDecisionQueueCommand { get; }

        public AsyncRelayCommand OpenOrderDetailCommand { get; }
        public AsyncRelayCommand OpenLotActionCommand { get; }
        public AsyncRelayCommand DeleteOrderGroupCommand { get; }
        public AsyncRelayCommand PreviousPageCommand { get; }
        public AsyncRelayCommand NextPageCommand { get; }

        public AsyncRelayCommand ConfirmPlanCommand { get; }


        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public string SelectedProductionTab
        {
            get => _selectedProductionTab;
            set
            {
                if (SetProperty(ref _selectedProductionTab, value))
                {
                    OnPropertyChanged(nameof(IsInProgressTab));
                    OnPropertyChanged(nameof(IsCompletedTab));
                    OnPropertyChanged(nameof(IsDateFilterVisible));
                    OnPropertyChanged(nameof(CurrentTabTitle));
                    OnPropertyChanged(nameof(IsPlanningSectionVisible));
                    OnPropertyChanged(nameof(IsPlanDecisionVisible));
                }
            }
        }

        public bool IsInProgressTab => SelectedProductionTab == ProductionTabInProgress;
        public bool IsCompletedTab => SelectedProductionTab == ProductionTabCompleted;
        public bool IsDateFilterVisible => IsCompletedTab;

        public bool IsPlanningSectionVisible => IsInProgressTab && SelectedItem != null;

        public string CurrentTabTitle => IsCompletedTab ? "발주리스트 - 생산완료" : "발주리스트 - 생산중";

        public bool CanDeleteOrderGroup => SelectedItem != null;

        public DateTime? OrderDateFrom
        {
            get => _orderDateFrom;
            set => SetProperty(ref _orderDateFrom, value);
        }

        public DateTime? OrderDateTo
        {
            get => _orderDateTo;
            set => SetProperty(ref _orderDateTo, value);
        }

        public int Page
        {
            get => _page;
            set
            {
                if (SetProperty(ref _page, value))
                {
                    OnPropertyChanged(nameof(PageInfoText));
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
                }
            }
        }

        public bool CanGoPreviousPage
        {
            get => _canGoPreviousPage;
            set
            {
                if (SetProperty(ref _canGoPreviousPage, value))
                {
                    PreviousPageCommand?.RaiseCanExecuteChanged();
                }
            }
        }

        public bool CanGoNextPage
        {
            get => _canGoNextPage;
            set
            {
                if (SetProperty(ref _canGoNextPage, value))
                {
                    NextPageCommand?.RaiseCanExecuteChanged();
                }
            }
        }

        public string PagingDebugText =>
             $"Page={Page}, Size={Size}, Total={Total}, Next={CanGoNextPage}";

        public string PageInfoText =>
            $"{Page} / {Math.Max(1, (int)Math.Ceiling((double)Math.Max(Total, 1) / Math.Max(Size, 1)))} 페이지";

        public string TotalCountText => $"총 {Total:N0}건";

        public string LotActionButtonText => "재작업 LOT";

        public string SelectedPlanType
        {
            get => _selectedPlanType;
            set
            {
                if (SetProperty(ref _selectedPlanType, value))
                {
                    OnPropertyChanged(nameof(StockUsePlanQtyText));
                    OnPropertyChanged(nameof(PlannedProductionQtyText));
                }
            }
        }

        public string PlanMemo
        {
            get => _planMemo;
            set => SetProperty(ref _planMemo, value);
        }

        public bool CanConfirmPlan
        {
            get => _canConfirmPlan;
            set => SetProperty(ref _canConfirmPlan, value);
        }

        public bool IsPlanDecisionVisible =>
            IsInProgressTab
            && SelectedItem != null
            && SelectedItem.DecisionRequired
            && SelectedItem.Status == "OPEN"
            && !SelectedItem.HasLot
            && SelectedItem.AllowedPlanTypes.Count > 0;

        public string PlanTypeDisplayText =>
            string.IsNullOrWhiteSpace(SelectedItem?.PlanTypeDisplay)
                ? "-"
                : SelectedItem.PlanTypeDisplay!;

        public string StockUsePlanQtyText
        {
            get
            {
                if (SelectedItem == null)
                {
                    return "0";
                }

                if (SelectedPlanType == "STOCK_REPLENISHMENT")
                {
                    return "0";
                }

                if (SelectedItem.DecisionMade)
                    return $"{SelectedItem.PlannedStockShipQty:N0}";

                var qty = Math.Min(
                    Math.Max(SelectedItem.AvailableInventoryQty, 0),
                    Math.Max(SelectedItem.ShipTargetQty, 0));

                return $"{qty:N0}";
            }
        }

        public string AutoPlanGuideText
        {
            get
            {
                if (SelectedItem == null)
                {
                    return "-";
                }

                if (SelectedItem.DecisionMade)
                {
                    return "처리계획이 확정되었습니다.";
                }

                if (SelectedItem.AvailableInventoryQty <= 0)
                {
                    return "현재고가 없어 출고목표수량 기준으로 생산이 진행됩니다.";
                }

                if (SelectedItem.AvailableInventoryQty >= SelectedItem.ShipTargetQty)
                {
                    return "현재고가 충분합니다. 재고 출고완료 또는 발주수량 전체 재고생산을 선택하세요.";
                }

                return "현재고가 부족합니다. 기존 부분재고 처리 또는 발주수량 전체 재고생산을 선택하세요.";
            }
        }

        public bool CanCreateBaseLot
        {
            get => _canCreateBaseLot;
            set => SetProperty(ref _canCreateBaseLot, value);
        }

        public bool CanShortClose
        {
            get => _canShortClose;
            set => SetProperty(ref _canShortClose, value);
        }

        public string AvailableInventoryQtyText => $"{SelectedItem?.AvailableInventoryQty ?? 0:N0}";
        public string TargetShipQtyText => $"{SelectedItem?.TargetShipQty ?? 0:N0}";
        public string RecommendedFulfillmentModeText => SelectedItem?.RecommendedFulfillmentModeDisplay ?? "-";
        public string RecommendedProductionQtyText => $"{SelectedItem?.RecommendedProductionQty ?? 0:N0}";
        public string PlannedProductionQtyText => SelectedPlanType switch
        {
            "STOCK_REPLENISHMENT" => $"{SelectedItem?.OrderQty ?? 0:N0}",
            "STOCK_SHIP_COMPLETE" or "PARTIAL_STOCK_ONLY_CLOSE" => "0",
            _ => $"{SelectedItem?.PlannedProductionQty ?? 0:N0}"
        };
        public string DecisionStatusText => SelectedItem == null ? "-" : (SelectedItem.DecisionMade ? "결정완료" : "결정필요");

        public string ExpectedShipQtyText => $"{SelectedItem?.ExpectedShipQty ?? 0:N0}";
        public string ExpectedShortQtyText => $"{SelectedItem?.ExpectedShortQty ?? 0:N0}";

        public string ShipTargetQtyText => $"{SelectedItem?.ShipTargetQty ?? 0:N0}";
        public string AlreadyShippedQtyText => $"{SelectedItem?.AlreadyShippedQty ?? 0:N0}";
        public string RemainingShipQtyText => $"{SelectedItem?.RemainingShipQty ?? 0:N0}";
        public string ShortageStatusText => SelectedItem?.ShortageStatusDisplay ?? "-";

        public bool IsShortageSectionVisible =>
            IsInProgressTab &&
            SelectedItem != null &&
            (SelectedItem.NeedsShortageAction || SelectedItem.ShortageClosed);

        public async Task InitializeAsync()
        {
            await RunBusyAsync(SearchAsync);
        }

        protected override async Task<bool> LoadListAsync()
        {
            SetQueueCounts(null);
            var route = BuildListUrl();

            var result = await _apiClient.GetAsync<OrderLineListResponse>(route);

            if (!result.Success || result.Data == null)
            {
                if (_preserveRows)
                {
                    _messageService.ShowError(result.Message ?? "처리는 완료되었지만 목록 갱신에 실패했습니다. 다시 조회하세요.");
                    return false;
                }
                Items.Clear();
                Total = 0;
                CanGoPreviousPage = false;
                CanGoNextPage = false;

                OnPropertyChanged(nameof(PageInfoText));
                OnPropertyChanged(nameof(TotalCountText));
                OnPropertyChanged(nameof(CanGoPreviousPage));
                OnPropertyChanged(nameof(CanGoNextPage));
                OnPropertyChanged(nameof(PagingDebugText));

                _messageService.ShowError(result.Message ?? "수주 리스트 조회 중 오류가 발생했습니다.");
                return false;
            }

            if (_preserveRows && result.Data.Items.Count == 0 && Page > 1)
            {
                Page = Math.Max(1, Math.Min(Page - 1, (int)Math.Ceiling(result.Data.Meta.Total / (double)Math.Max(Size, 1))));
                return await LoadListAsync();
            }

            ApplyItems(result.Data.Items);
            SetQueueCounts(result.Data.QueueCounts);

            Page = result.Data.Meta.Page <= 0 ? Page : result.Data.Meta.Page;
            Size = result.Data.Meta.Size <= 0 ? Size : result.Data.Meta.Size;
            Total = result.Data.Meta.Total;

            CanGoPreviousPage = Page > 1;
            CanGoNextPage = Page * Size < Total;

            OnPropertyChanged(nameof(PageInfoText));
            OnPropertyChanged(nameof(TotalCountText));
            OnPropertyChanged(nameof(CanGoPreviousPage));
            OnPropertyChanged(nameof(CanGoNextPage));
            OnPropertyChanged(nameof(PageInfoText));
            OnPropertyChanged(nameof(TotalCountText));
            OnPropertyChanged(nameof(PagingDebugText));
            return true;
        }

        private void SetQueueCounts(Dictionary<string, int>? counts)
        {
            _lotCreationCount = counts != null && counts.TryGetValue("lot_creation", out var lotCount) ? lotCount : null;
            _closeDecisionCount = counts != null && counts.TryGetValue("close_decision", out var closeCount) ? closeCount : null;
            OnPropertyChanged(nameof(LotCreationButtonText));
            OnPropertyChanged(nameof(CloseDecisionButtonText));
        }

        private void ApplyItems(List<OrderLineListItemDto> incoming)
        {
            var selectedId = SelectedItem?.OrderLineId;
            var selectedIndex = SelectedItem == null ? -1 : Items.IndexOf(SelectedItem);
            if (!_preserveRows)
            {
                Items.Clear();
                foreach (var item in incoming) Items.Add(item);
                SelectedItem = Items.FirstOrDefault(x => x.OrderLineId == selectedId);
                return;
            }

            ItemsRefreshing?.Invoke();
            try
            {
                var ids = incoming.Select(x => x.OrderLineId).ToHashSet();
                for (var i = Items.Count - 1; i >= 0; i--)
                    if (!ids.Contains(Items[i].OrderLineId)) Items.RemoveAt(i);
                for (var i = 0; i < incoming.Count; i++)
                {
                    var item = incoming[i];
                    var existing = Items.FirstOrDefault(x => x.OrderLineId == item.OrderLineId);
                    if (existing == null) Items.Insert(i, item);
                    else
                    {
                        var index = Items.IndexOf(existing);
                        if (index != i) Items.Move(index, i);
                        if (System.Text.Json.JsonSerializer.Serialize(existing) != System.Text.Json.JsonSerializer.Serialize(item))
                            Items[i] = item;
                    }
                }
                SelectedItem = Items.FirstOrDefault(x => x.OrderLineId == selectedId)
                    ?? (selectedIndex >= 0 && Items.Count > 0 ? Items[Math.Min(selectedIndex, Items.Count - 1)] : null);
            }
            finally { ItemsRefreshed?.Invoke(); }
        }

        private async Task RefreshAfterActionAsync()
        {
            var previousPage = Page;
            _preserveRows = true;
            try
            {
                if (!await LoadListAsync()) Page = previousPage;
            }
            finally { _preserveRows = false; }
        }

        protected override void Reset()
        {
            SetWorkQueue(null);
            SearchKeyword = string.Empty;
            OrderDateFrom = null;
            OrderDateTo = null;

            Page = 1;
            Size = 20;
            Total = 0;

            CanGoPreviousPage = false;
            CanGoNextPage = false;

            SelectedItem = null;

            PlanOptions.Clear();
            SelectedPlanType = string.Empty;
            PlanMemo = string.Empty;
            CanConfirmPlan = false;

            CanCreateBaseLot = false;
            CanShortClose = false;

            OnPropertyChanged(nameof(PageInfoText));
            OnPropertyChanged(nameof(TotalCountText));

            RaisePlanningPropertiesChanged();
        }

        protected override void New()
        {
        }

        protected override void OnSelectedItemChanged(OrderLineListItemDto? item)
        {
            OnPropertyChanged(nameof(LotActionButtonText));
            OnPropertyChanged(nameof(IsPlanningSectionVisible));

            SyncPlanningEditorFromSelectedItem(item);

            if (item == null)
            {
                PlanMemo = string.Empty;
            }

            RefreshActionStates(item);
            RaisePlanningPropertiesChanged();
        }

        private void SyncPlanningEditorFromSelectedItem(OrderLineListItemDto? item)
        {
            PlanOptions.Clear();

            if (item == null || item.AllowedPlanTypes.Count == 0)
            {
                SelectedPlanType = string.Empty;
                return;
            }

            foreach (var planType in item.AllowedPlanTypes)
            {
                PlanOptions.Add(new KeyValuePair<string, string>(planType, GetPlanTypeDisplay(planType)));
            }

            SelectedPlanType = PlanOptions[0].Key;
        }

        private static string GetPlanTypeDisplay(string planType) => planType switch
        {
            "AUTO_PRODUCTION" => "전량 생산",
            "STOCK_SHIP_COMPLETE" => "재고로 출고완료",
            "PARTIAL_STOCK_PLUS_PRODUCTION" => "기존재고 예약 + 부족분 생산",
            "PARTIAL_STOCK_ONLY_CLOSE" => "재고만 출고 후 종료",
            "STOCK_REPLENISHMENT" => "발주수량 전체 재고생산",
            _ => planType
        };

        private void RefreshActionStates(OrderLineListItemDto? item)
        {
            CanCreateBaseLot =
                IsInProgressTab
                && item != null
                && item.DecisionMade
                && item.PlannedProductionQty > 0
                && item.ProductionPolicy != "INVENTORY_ONLY_CLOSE"
                && !item.HasLot
                && item.Status == "OPEN";

            CanShortClose = IsInProgressTab && item?.WorkQueue == "CLOSE_DECISION";

            CanConfirmPlan = IsPlanDecisionVisible;

            OnPropertyChanged(nameof(CanCreateBaseLot));
            OnPropertyChanged(nameof(CanShortClose));
            OnPropertyChanged(nameof(CanConfirmPlan));
            OnPropertyChanged(nameof(CanDeleteOrderGroup));
            OnPropertyChanged(nameof(CanReopen));
            OnPropertyChanged(nameof(IsPlanDecisionVisible));
        }

        private void RaisePlanningPropertiesChanged()
        {
            OnPropertyChanged(nameof(IsPlanningSectionVisible));

            OnPropertyChanged(nameof(AvailableInventoryQtyText));
            OnPropertyChanged(nameof(TargetShipQtyText));
            OnPropertyChanged(nameof(RecommendedFulfillmentModeText));
            OnPropertyChanged(nameof(RecommendedProductionQtyText));
            OnPropertyChanged(nameof(PlannedProductionQtyText));
            OnPropertyChanged(nameof(DecisionStatusText));

            OnPropertyChanged(nameof(ExpectedShipQtyText));
            OnPropertyChanged(nameof(ExpectedShortQtyText));

            OnPropertyChanged(nameof(ShipTargetQtyText));
            OnPropertyChanged(nameof(AlreadyShippedQtyText));
            OnPropertyChanged(nameof(RemainingShipQtyText));
            OnPropertyChanged(nameof(ShortageStatusText));
            OnPropertyChanged(nameof(IsShortageSectionVisible));

            OnPropertyChanged(nameof(IsPlanDecisionVisible));
            OnPropertyChanged(nameof(CanConfirmPlan));
            OnPropertyChanged(nameof(PlanTypeDisplayText));
            OnPropertyChanged(nameof(StockUsePlanQtyText));
            OnPropertyChanged(nameof(AutoPlanGuideText));
        }

        private async Task ChangeProductionTabAsync(string targetTab)
        {
            if (SelectedProductionTab == targetTab)
            {
                return;
            }

            SelectedProductionTab = targetTab;
            SetWorkQueue(null);
            SearchKeyword = string.Empty;
            Page = 1;

            if (Size <= 0)
            {
                Size = 20;
            }

            if (IsInProgressTab)
            {
                OrderDateFrom = null;
                OrderDateTo = null;
            }

            SelectedItem = null;
            CanCreateBaseLot = false;
            CanShortClose = false;

            RaisePlanningPropertiesChanged();

            await SearchAsync();
        }

        private async Task ConfirmPlanAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("처리계획을 확정할 발주를 먼저 선택하세요.");
                return;
            }

            if (!IsPlanDecisionVisible)
            {
                _messageService.ShowWarning("현재 선택된 발주는 처리계획 선택 대상이 아닙니다.");
                return;
            }

            if (string.IsNullOrWhiteSpace(SelectedPlanType)
                || !SelectedItem.AllowedPlanTypes.Contains(SelectedPlanType))
            {
                _messageService.ShowWarning("허용된 처리방식을 선택하세요.");
                return;
            }

            var confirmMessage = SelectedPlanType switch
            {
                "STOCK_SHIP_COMPLETE" => "현재고를 즉시 차감하고 재고 출고완료로 처리하시겠습니까?",
                "PARTIAL_STOCK_ONLY_CLOSE" => "현재고만 출고하고 부족분 생산 없이 종료하시겠습니까?",
                "PARTIAL_STOCK_PLUS_PRODUCTION" => "현재고를 예약하고 부족분 생산으로 진행하시겠습니까?",
                "STOCK_REPLENISHMENT" => "기존 재고를 사용하지 않고 발주수량 전체로 재고생산 LOT를 생성하시겠습니까?",
                _ => "선택한 처리계획을 확정하시겠습니까?"
            };

            if (!_messageService.Confirm(confirmMessage))
            {
                return;
            }

            var request = new OrderLinePlanConfirmRequest
            {
                PlanType = SelectedPlanType,
                Memo = string.IsNullOrWhiteSpace(PlanMemo)
                    ? null
                    : PlanMemo.Trim()
            };

            var targetId = SelectedItem.OrderLineId;
            var route = $"{ApiRoutes.OrderLines}/{targetId}/plan/confirm";

            var result = await _apiClient.PostAsync<OrderLinePlanConfirmRequest, OrderLineListItemDto>(
                route,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "처리계획 확정 중 오류가 발생했습니다.");
                return;
            }

            await RefreshAfterActionAsync();

            PlanMemo = string.Empty;

            _messageService.ShowInfo("처리계획이 확정되었습니다.");
        }

        private async Task CreateBaseLotAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("기본 LOT를 생성할 발주를 먼저 선택하세요.");
                return;
            }

            if (!CanCreateBaseLot)
            {
                _messageService.ShowWarning("현재 선택된 발주는 기본 LOT 생성 조건을 만족하지 않습니다.");
                return;
            }

            var targetId = SelectedItem.OrderLineId;
            var route = $"{ApiRoutes.OrderLines}/{targetId}/base-lot";

            var result = await _apiClient.PostAsync<OrderLineBaseLotCreateRequest, object>(
                route,
                new OrderLineBaseLotCreateRequest());

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "기본 LOT 생성 중 오류가 발생했습니다.");
                return;
            }

            await RefreshAfterActionAsync();

            _messageService.ShowInfo("기본 LOT가 생성되었습니다.");
        }

        private async Task ShortCloseAsync()
        {
            var item = SelectedItem;
            if (item == null || !CanShortClose)
            {
                _messageService.ShowWarning("종료판단대기 발주를 선택하세요.");
                return;
            }
            if (!_messageService.Confirm(
                $"발주 [{item.OrderNo}] / {item.LineNo}번 항목\n출고목표 {item.ShipTargetQty:N0} / 실제 출고 {item.AlreadyShippedQty:N0} / 미출고 {item.RemainingShipQty:N0}\n\n현재 실적으로 완료하시겠습니까?",
                "현재 실적으로 완료"))
                return;
            await ChangeCompletionAsync(item, "manual-close", "현재 실적으로 완료했습니다.");
        }

        private async Task ReopenAsync()
        {
            var item = SelectedItem;
            if (item == null || !CanReopen) return;
            if (!_messageService.Confirm($"발주 [{item.OrderNo}] / {item.LineNo}번 항목의 수동완료를 취소하시겠습니까?\n기존 출고와 재고 수량은 유지됩니다.", "완료 취소")) return;
            await ChangeCompletionAsync(item, "manual-reopen", "수동완료를 취소했습니다.");
        }

        private async Task ChangeCompletionAsync(OrderLineListItemDto item, string action, string successMessage)
        {
            var result = await _apiClient.PatchAsync<OrderLineShortCloseRequest, OrderLineListItemDto>(
                $"{ApiRoutes.OrderLines}/{item.OrderLineId}/{action}",
                new OrderLineShortCloseRequest
                {
                    ExpectedUpdatedAt = item.UpdatedAt,
                    ExpectedShipTargetQty = item.ShipTargetQty,
                    ExpectedShippedQty = item.AlreadyShippedQty
                });
            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "완료 상태 변경에 실패했습니다.");
                return;
            }
            await RefreshAfterActionAsync();
            _messageService.ShowInfo(successMessage);
        }

        private async Task OpenOrderDetailAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("발주상세를 볼 항목을 먼저 선택하세요.");
                return;
            }

            if (_openDetailAsync == null)
            {
                _messageService.ShowWarning("상세 화면 연결이 아직 설정되지 않았습니다.");
                return;
            }

            await _openDetailAsync(SelectedItem.OrderLineId);
            await RefreshAfterActionAsync();
        }

        private async Task OpenLotActionAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("항목을 먼저 선택하세요.");
                return;
            }

            if (!SelectedItem.HasLot)
            {
                _messageService.ShowWarning("Primary LOT이 없는 수주라인은 재작업 LOT를 생성할 수 없습니다.");
                return;
            }

            if (_openLotCreateAsync == null)
            {
                _messageService.ShowWarning("재작업 LOT 생성 창 연결이 아직 설정되지 않았습니다.");
                return;
            }

            await _openLotCreateAsync(SelectedItem);
            await RefreshAfterActionAsync();
        }

        private async Task DeleteOrderGroupAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("삭제할 수주를 먼저 선택하세요.");
                return;
            }

            var orderNo = SelectedItem.OrderNo;
            var confirmed = _messageService.Confirm(
                $"수주번호 [{orderNo}]에 포함된 모든 라인과 관련 LOT/검수/출하대기 데이터가 삭제됩니다.\n\n다시 등록하기 위한 관리자 삭제 작업입니다. 계속하시겠습니까?",
                "수주번호 전체 삭제 확인");

            if (!confirmed)
            {
                return;
            }

            var result = await _apiClient.DeleteAsync($"{ApiRoutes.OrderLines}/{SelectedItem.OrderLineId}");

            if (!result.Success || !result.Data)
            {
                _messageService.ShowError(result.Message ?? "수주번호 전체 삭제 중 오류가 발생했습니다.");
                return;
            }

            SelectedItem = null;
            await SearchAsync();

            _messageService.ShowInfo($"수주번호 [{orderNo}] 전체 삭제가 완료되었습니다.");
        }

        private string BuildListUrl()
        {
            var page = Page <= 0 ? 1 : Page;
            var size = Size <= 0 ? 20 : Size;

            var queryParts = new List<string>
            {
                $"page={page}",
                $"size={size}"
            };

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(SearchKeyword.Trim())}");
            }

            var statusGroup = IsCompletedTab ? ProductionTabCompleted : ProductionTabInProgress;
            queryParts.Add($"status_group={Uri.EscapeDataString(statusGroup)}");

            if (IsInProgressTab && _selectedWorkQueue != null)
                queryParts.Add($"work_queue={_selectedWorkQueue}");

            if (IsCompletedTab)
            {
                if (OrderDateFrom.HasValue)
                {
                    queryParts.Add($"order_date_from={OrderDateFrom.Value:yyyy-MM-dd}");
                }

                if (OrderDateTo.HasValue)
                {
                    queryParts.Add($"order_date_to={OrderDateTo.Value:yyyy-MM-dd}");
                }
            }

            return $"{ApiRoutes.OrderLines}?{string.Join("&", queryParts)}";
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
