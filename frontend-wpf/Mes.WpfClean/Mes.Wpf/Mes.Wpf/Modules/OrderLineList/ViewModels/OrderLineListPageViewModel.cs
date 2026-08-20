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

        private string _selectedFulfillmentMode = "INVENTORY_FIRST";
        private string _selectedProductionPolicy = "ORDER_ONLY";
        private string _extraProductionQtyText = "0";

        private bool _canCreateBaseLot;
        private bool _canShortClose;

        private string _selectedPartialStockPlanType = "PARTIAL_STOCK_PLUS_PRODUCTION";
        private string _partialStockPlanMemo = string.Empty;
        private bool _canConfirmPartialStockPlan;

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

            SearchOrderLinesCommand = new AsyncRelayCommand(async () =>
            {
                Page = 1;
                await SearchAsync();
            });

            ResetOrderLineSearchCommand = new AsyncRelayCommand(async () =>
            {
                Reset();
                await SearchAsync();
            });

            ShowInProgressCommand = new AsyncRelayCommand(async () =>
            {
                await ChangeProductionTabAsync(ProductionTabInProgress);
            });

            ShowCompletedCommand = new AsyncRelayCommand(async () =>
            {
                await ChangeProductionTabAsync(ProductionTabCompleted);
            });

            SaveFulfillmentPlanCommand = new AsyncRelayCommand(SaveFulfillmentPlanAsync);
            CreateBaseLotCommand = new AsyncRelayCommand(CreateBaseLotAsync);
            ShortCloseCommand = new AsyncRelayCommand(ShortCloseAsync);
            ConfirmPartialStockPlanCommand = new AsyncRelayCommand(ConfirmPartialStockPlanAsync);
            OpenOrderDetailCommand = new AsyncRelayCommand(OpenOrderDetailAsync);
            OpenLotActionCommand = new AsyncRelayCommand(OpenLotActionAsync);
            DeleteOrderGroupCommand = new AsyncRelayCommand(DeleteOrderGroupAsync);
            PreviousPageCommand = new AsyncRelayCommand(
                GoPreviousPageAsync,
                () => CanGoPreviousPage);

            NextPageCommand = new AsyncRelayCommand(
                GoNextPageAsync,
                () => CanGoNextPage);


        }

        public ObservableCollection<OrderLineListItemDto> Items { get; }

        public AsyncRelayCommand SearchOrderLinesCommand { get; }
        public AsyncRelayCommand ResetOrderLineSearchCommand { get; }

        public AsyncRelayCommand ShowInProgressCommand { get; }
        public AsyncRelayCommand ShowCompletedCommand { get; }

        public AsyncRelayCommand SaveFulfillmentPlanCommand { get; }
        public AsyncRelayCommand CreateBaseLotCommand { get; }
        public AsyncRelayCommand ShortCloseCommand { get; }

        public AsyncRelayCommand OpenOrderDetailCommand { get; }
        public AsyncRelayCommand OpenLotActionCommand { get; }
        public AsyncRelayCommand DeleteOrderGroupCommand { get; }
        public AsyncRelayCommand PreviousPageCommand { get; }
        public AsyncRelayCommand NextPageCommand { get; }

        public AsyncRelayCommand ConfirmPartialStockPlanCommand { get; }


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
                    OnPropertyChanged(nameof(CanEditFulfillmentPlan));
                    OnPropertyChanged(nameof(CanEditFulfillmentMode));
                    OnPropertyChanged(nameof(CanEditExtraProductionQty));
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

        public string SelectedFulfillmentMode
        {
            get => _selectedFulfillmentMode;
            set => SetProperty(ref _selectedFulfillmentMode, value);
        }

        public string SelectedProductionPolicy
        {
            get => _selectedProductionPolicy;
            set
            {
                if (SetProperty(ref _selectedProductionPolicy, value))
                {
                    if (_selectedProductionPolicy == "INVENTORY_ONLY_CLOSE")
                    {
                        SelectedFulfillmentMode = "INVENTORY_FIRST";
                        ExtraProductionQtyText = "0";
                    }
                    else if (_selectedProductionPolicy != "ALLOW_STOCK_BUILD")
                    {
                        ExtraProductionQtyText = "0";
                    }

                    OnPropertyChanged(nameof(CanEditFulfillmentPlan));
                    OnPropertyChanged(nameof(CanEditFulfillmentMode));
                    OnPropertyChanged(nameof(CanEditExtraProductionQty));
                }
            }
        }

        public string SelectedPartialStockPlanType
        {
            get => _selectedPartialStockPlanType;
            set => SetProperty(ref _selectedPartialStockPlanType, value);
        }

        public string PartialStockPlanMemo
        {
            get => _partialStockPlanMemo;
            set => SetProperty(ref _partialStockPlanMemo, value);
        }

        public bool CanConfirmPartialStockPlan
        {
            get => _canConfirmPartialStockPlan;
            set => SetProperty(ref _canConfirmPartialStockPlan, value);
        }

        public bool IsPartialStockDecisionVisible =>
            IsInProgressTab
            && SelectedItem != null
            && !SelectedItem.DecisionMade
            && SelectedItem.Status == "OPEN"
            && !SelectedItem.HasLot
            && SelectedItem.AvailableInventoryQty > 0
            && SelectedItem.AvailableInventoryQty < SelectedItem.ShipTargetQty;

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
                    return "현재고가 출고목표수량 이상이므로 재고 출고 대상으로 처리됩니다.";
                }

                return "현재고가 출고목표수량보다 부족합니다. 처리방식을 선택하세요.";
            }
        }


        public string ExtraProductionQtyText
        {
            get => _extraProductionQtyText;
            set => SetProperty(ref _extraProductionQtyText, value);
        }

        public bool CanEditFulfillmentPlan =>
            IsInProgressTab &&
            SelectedItem != null &&
            !SelectedItem.DecisionMade &&
            SelectedItem.Status == "OPEN" &&
            !SelectedItem.HasLot;

        public bool CanEditFulfillmentMode =>
            CanEditFulfillmentPlan &&
            SelectedProductionPolicy != "INVENTORY_ONLY_CLOSE";

        public bool CanEditExtraProductionQty =>
            CanEditFulfillmentPlan &&
            SelectedProductionPolicy == "ALLOW_STOCK_BUILD";

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
        public string PlannedProductionQtyText => $"{SelectedItem?.PlannedProductionQty ?? 0:N0}";
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
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();

            var result = await _apiClient.GetAsync<OrderLineListResponse>(route);

            if (!result.Success || result.Data == null)
            {
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

            Items.Clear();

            foreach (var item in result.Data.Items)
            {
                Items.Add(item);
            }

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

        protected override void Reset()
        {
            SearchKeyword = string.Empty;
            OrderDateFrom = null;
            OrderDateTo = null;

            Page = 1;
            Size = 20;
            Total = 0;

            CanGoPreviousPage = false;
            CanGoNextPage = false;

            SelectedItem = null;

            SelectedFulfillmentMode = "INVENTORY_FIRST";
            SelectedProductionPolicy = "ORDER_ONLY";
            ExtraProductionQtyText = "0";
            SelectedPartialStockPlanType = "PARTIAL_STOCK_PLUS_PRODUCTION";
            PartialStockPlanMemo = string.Empty;
            CanConfirmPartialStockPlan = false;

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
                SelectedPartialStockPlanType = "PARTIAL_STOCK_PLUS_PRODUCTION";
                PartialStockPlanMemo = string.Empty;
            }

            RefreshActionStates(item);
            RaisePlanningPropertiesChanged();
        }

        private void SyncPlanningEditorFromSelectedItem(OrderLineListItemDto? item)
        {
            if (item == null)
            {
                SelectedFulfillmentMode = "INVENTORY_FIRST";
                SelectedProductionPolicy = "ORDER_ONLY";
                ExtraProductionQtyText = "0";
                return;
            }

            SelectedFulfillmentMode = string.IsNullOrWhiteSpace(item.FulfillmentMode)
                ? (string.IsNullOrWhiteSpace(item.RecommendedFulfillmentMode) ? "INVENTORY_FIRST" : item.RecommendedFulfillmentMode!)
                : item.FulfillmentMode!;

            SelectedProductionPolicy = string.IsNullOrWhiteSpace(item.ProductionPolicy)
                ? "ORDER_ONLY"
                : item.ProductionPolicy!;

            ExtraProductionQtyText = (item.ExtraProductionQty < 0 ? 0 : item.ExtraProductionQty).ToString();

            if (SelectedProductionPolicy == "INVENTORY_ONLY_CLOSE")
            {
                SelectedFulfillmentMode = "INVENTORY_FIRST";
                ExtraProductionQtyText = "0";
            }
        }

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

            CanShortClose = false;

            CanConfirmPartialStockPlan = IsPartialStockDecisionVisible;

            OnPropertyChanged(nameof(CanCreateBaseLot));
            OnPropertyChanged(nameof(CanShortClose));
            OnPropertyChanged(nameof(CanConfirmPartialStockPlan));
            OnPropertyChanged(nameof(CanEditFulfillmentPlan));
            OnPropertyChanged(nameof(CanEditFulfillmentMode));
            OnPropertyChanged(nameof(CanEditExtraProductionQty));
            OnPropertyChanged(nameof(CanDeleteOrderGroup));
            OnPropertyChanged(nameof(IsPartialStockDecisionVisible));
        }

        private void RaisePlanningPropertiesChanged()
        {
            OnPropertyChanged(nameof(IsPlanningSectionVisible));

            OnPropertyChanged(nameof(CanEditFulfillmentPlan));
            OnPropertyChanged(nameof(CanEditFulfillmentMode));
            OnPropertyChanged(nameof(CanEditExtraProductionQty));

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

            OnPropertyChanged(nameof(IsPartialStockDecisionVisible));
            OnPropertyChanged(nameof(CanConfirmPartialStockPlan));
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

        private async Task SaveFulfillmentPlanAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("처리계획을 저장할 발주를 먼저 선택하세요.");
                return;
            }

            if (!CanEditFulfillmentPlan)
            {
                _messageService.ShowWarning("이미 결정완료된 발주이거나 처리계획을 수정할 수 없는 상태입니다.");
                return;
            }

            if (!IsInProgressTab)
            {
                _messageService.ShowWarning("처리계획 저장은 생산중 탭에서만 가능합니다.");
                return;
            }

            if (!TryParseExtraProductionQty(out var extraProductionQty))
            {
                _messageService.ShowWarning("추가생산수량은 0 이상의 숫자만 입력하세요.");
                return;
            }

            var request = new OrderLineFulfillmentPlanUpdateRequest
            {
                FulfillmentMode = SelectedProductionPolicy == "INVENTORY_ONLY_CLOSE"
                    ? "INVENTORY_FIRST"
                    : SelectedFulfillmentMode,
                ProductionPolicy = SelectedProductionPolicy,
                ExtraProductionQty = SelectedProductionPolicy == "ALLOW_STOCK_BUILD" ? extraProductionQty : 0
            };

            var route = $"{ApiRoutes.OrderLines}/{SelectedItem.OrderLineId}/fulfillment-plan";
            var result = await _apiClient.PatchAsync<OrderLineFulfillmentPlanUpdateRequest, OrderLineListItemDto>(route, request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "처리계획 저장 중 오류가 발생했습니다.");
                return;
            }

            var targetId = SelectedItem.OrderLineId;

            await SearchAsync();

            var refreshed = Items.FirstOrDefault(x => x.OrderLineId == targetId);
            if (refreshed != null)
            {
                SelectedItem = refreshed;
            }

            _messageService.ShowInfo("처리계획이 저장되었습니다.");
        }

        private async Task ConfirmPartialStockPlanAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("처리계획을 확정할 발주를 먼저 선택하세요.");
                return;
            }

            if (!IsPartialStockDecisionVisible)
            {
                _messageService.ShowWarning("현재 선택된 발주는 부분재고 처리 대상이 아닙니다.");
                return;
            }

            if (SelectedPartialStockPlanType != "PARTIAL_STOCK_ONLY_CLOSE"
                && SelectedPartialStockPlanType != "PARTIAL_STOCK_PLUS_PRODUCTION")
            {
                _messageService.ShowWarning("부분재고 처리방식을 선택하세요.");
                return;
            }

            var confirmMessage = SelectedPartialStockPlanType == "PARTIAL_STOCK_ONLY_CLOSE"
                ? "현재고만 출하대기로 생성하고 부족분 생산 없이 종료하시겠습니까?"
                : "현재고는 검수실적등록에서 함께 출하대기로 처리하고, 부족분 생산으로 진행하시겠습니까?";

            if (!_messageService.Confirm(confirmMessage))
            {
                return;
            }

            var request = new OrderLinePlanConfirmRequest
            {
                PlanType = SelectedPartialStockPlanType,
                Memo = string.IsNullOrWhiteSpace(PartialStockPlanMemo)
                    ? null
                    : PartialStockPlanMemo.Trim()
            };

            var route = $"{ApiRoutes.OrderLines}/{SelectedItem.OrderLineId}/plan/confirm";

            var result = await _apiClient.PostAsync<OrderLinePlanConfirmRequest, OrderLineListItemDto>(
                route,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "처리계획 확정 중 오류가 발생했습니다.");
                return;
            }

            var targetId = SelectedItem.OrderLineId;

            await SearchAsync();

            var refreshed = Items.FirstOrDefault(x => x.OrderLineId == targetId);
            if (refreshed != null)
            {
                SelectedItem = refreshed;
            }
            else
            {
                SelectedItem = null;
            }

            PartialStockPlanMemo = string.Empty;

            _messageService.ShowInfo("처리계획이 확정되었습니다.");
        }


        private bool TryParseExtraProductionQty(out int extraProductionQty)
        {
            extraProductionQty = 0;

            var text = (ExtraProductionQtyText ?? string.Empty).Trim();

            if (string.IsNullOrWhiteSpace(text))
            {
                return true;
            }

            if (!int.TryParse(text, out extraProductionQty))
            {
                return false;
            }

            return extraProductionQty >= 0;
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

            var route = $"{ApiRoutes.OrderLines}/{SelectedItem.OrderLineId}/base-lot";

            var result = await _apiClient.PostAsync<OrderLineBaseLotCreateRequest, object>(
                route,
                new OrderLineBaseLotCreateRequest());

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "기본 LOT 생성 중 오류가 발생했습니다.");
                return;
            }

            var targetId = SelectedItem.OrderLineId;

            await SearchAsync();

            var refreshed = Items.FirstOrDefault(x => x.OrderLineId == targetId);
            if (refreshed != null)
            {
                SelectedItem = refreshed;
            }

            _messageService.ShowInfo("기본 LOT가 생성되었습니다.");
        }

        private async Task ShortCloseAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("부족종료할 발주를 먼저 선택하세요.");
                return;
            }

            if (!CanShortClose)
            {
                _messageService.ShowWarning("현재 선택된 발주는 부족종료 대상이 아닙니다.");
                return;
            }

            var route = $"{ApiRoutes.OrderLines}/{SelectedItem.OrderLineId}/short-close";

            var result = await _apiClient.PatchAsync<OrderLineShortCloseRequest, OrderLineListItemDto>(
                route,
                new OrderLineShortCloseRequest());

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "부족종료 처리 중 오류가 발생했습니다.");
                return;
            }

            var targetId = SelectedItem.OrderLineId;

            await SearchAsync();

            var refreshed = Items.FirstOrDefault(x => x.OrderLineId == targetId);
            if (refreshed != null)
            {
                SelectedItem = refreshed;
            }

            _messageService.ShowInfo("부족종료 처리되었습니다.");
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
