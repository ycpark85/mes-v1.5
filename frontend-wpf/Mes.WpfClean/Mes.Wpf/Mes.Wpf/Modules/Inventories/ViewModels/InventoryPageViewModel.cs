using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Inventories.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Inventories.ViewModels
{
    public class InventoryPageViewModel : CrudPageViewModelBase<InventoryDto>
    {
        private const int DetailPageSize = 50;
        private const int ProductSelectionDelayMs = 250;
        private readonly IApiClient _api;
        private readonly IMessageService _messages;
        private string _searchKeyword = string.Empty, _lotKeyword = string.Empty;
        private string _loadedLotKeyword = string.Empty;
        private bool _loadedIncludeZero;
        private string _selectedMovementType = "전체";
        private string _lotStatus = "품목을 선택하세요.", _historyStatus = "LOT를 선택하세요.";
        private bool _includeZeroStock, _lotsLoading, _historyLoading, _updatingProducts, _updatingLots;
        private bool _isHistoryOpen;
        private int _lotPage = 1, _lotTotal, _historyPage = 1, _historyTotal;
        private int _listVersion, _lotVersion, _historyVersion;
        private long? _activeProductId;
        private long _lotTotalQty;
        private InventoryLotDto? _selectedLot;
        private DateTime? _dateFrom, _dateTo;

        public InventoryPageViewModel(IApiClient apiClient, IMessageService messageService)
        {
            _api = apiClient;
            _messages = messageService;
            LoadLotsCommand = new AsyncRelayCommand(() => LoadLotsAsync(1), () => SelectedItem != null && !LotsLoading);
            LotPreviousCommand = new AsyncRelayCommand(() => LoadLotsAsync(_lotPage - 1), () => !LotsLoading && _lotPage > 1);
            LotNextCommand = new AsyncRelayCommand(() => LoadLotsAsync(_lotPage + 1), () => !LotsLoading && _lotPage * (long)DetailPageSize < _lotTotal);
            OpenHistoryCommand = new RelayCommand(OpenHistory, () => HasSelectedLot && !LotsLoading && !HistoryLoading);
            SearchHistoryCommand = new AsyncRelayCommand(() => LoadHistoryAsync(1), () => IsHistoryOpen && HasSelectedLot && !LotsLoading && !HistoryLoading);
            HistoryPreviousCommand = new AsyncRelayCommand(() => LoadHistoryAsync(_historyPage - 1), () => IsHistoryOpen && HasSelectedLot && !LotsLoading && !HistoryLoading && _historyPage > 1);
            HistoryNextCommand = new AsyncRelayCommand(() => LoadHistoryAsync(_historyPage + 1), () => IsHistoryOpen && HasSelectedLot && !LotsLoading && !HistoryLoading && _historyPage * (long)DetailPageSize < _historyTotal);
            ClearHistoryPeriodCommand = new AsyncRelayCommand(async () => { DateFrom = null; DateTo = null; await LoadHistoryAsync(1); }, () => IsHistoryOpen && HasSelectedLot && !LotsLoading && !HistoryLoading);
            OpenAdjustmentCommand = new RelayCommand(OpenAdjustment, () => HasSelectedLot && !LotsLoading && !HistoryLoading);
            CheckConsistencyCommand = new AsyncRelayCommand(CheckConsistencyAsync);
            OpenInitialInventoryBulkUploadCommand = new RelayCommand(OpenInitialInventoryBulkUpload);
        }

        public event Action<InitialInventoryBulkUploadWindowViewModel>? RequestOpenInitialInventoryBulkUpload;
        public event Action<InventoryAdjustmentWindowViewModel>? RequestOpenAdjustment;
        public ObservableCollection<InventoryDto> Items { get; } = new();
        public ObservableCollection<InventoryLotDto> Lots { get; } = new();
        public ObservableCollection<InventoryMovementDto> Movements { get; } = new();
        public string[] MovementTypeOptions { get; } = new[] { "전체", "기초재고", "검수입고", "출고", "재고증가", "재고감소" };
        public AsyncRelayCommand LoadLotsCommand { get; }
        public AsyncRelayCommand LotPreviousCommand { get; }
        public AsyncRelayCommand LotNextCommand { get; }
        public RelayCommand OpenHistoryCommand { get; }
        public AsyncRelayCommand SearchHistoryCommand { get; }
        public AsyncRelayCommand HistoryPreviousCommand { get; }
        public AsyncRelayCommand HistoryNextCommand { get; }
        public AsyncRelayCommand ClearHistoryPeriodCommand { get; }
        public RelayCommand OpenAdjustmentCommand { get; }
        public AsyncRelayCommand CheckConsistencyCommand { get; }
        public RelayCommand OpenInitialInventoryBulkUploadCommand { get; }

        public string SearchKeyword { get => _searchKeyword; set => SetProperty(ref _searchKeyword, value); }
        public string LotKeyword { get => _lotKeyword; set => SetProperty(ref _lotKeyword, value); }
        public bool IncludeZeroStock { get => _includeZeroStock; set => SetProperty(ref _includeZeroStock, value); }
        public string SelectedMovementType { get => _selectedMovementType; set => SetProperty(ref _selectedMovementType, value); }
        public DateTime? DateFrom { get => _dateFrom; set => SetProperty(ref _dateFrom, value); }
        public DateTime? DateTo { get => _dateTo; set => SetProperty(ref _dateTo, value); }
        public string LotStatus { get => _lotStatus; private set => SetProperty(ref _lotStatus, value); }
        public string HistoryStatus { get => _historyStatus; private set => SetProperty(ref _historyStatus, value); }
        public bool LotsLoading { get => _lotsLoading; private set { SetProperty(ref _lotsLoading, value); RefreshCommands(); } }
        public bool HistoryLoading { get => _historyLoading; private set { SetProperty(ref _historyLoading, value); RefreshCommands(); } }
        public bool HasSelectedLot => SelectedItem != null && SelectedLot != null;
        public string SelectedProductText => SelectedItem == null ? "품목을 선택하면 LOT별 재고를 확인할 수 있습니다." : $"{SelectedItem.ProductName} · 전체 재고 {SelectedItem.CurrentQty:N0} {SelectedItem.Uom}";
        public string SelectedLotText => !IsHistoryOpen || !HasSelectedLot ? "왼쪽에서 LOT를 선택한 뒤 상세보기를 누르세요." : $"{SelectedLot!.LotNo} · 현재 재고 {SelectedLot.CurrentQty:N0} {SelectedItem!.Uom}";
        public string LotPageText => $"{_lotPage:N0} / {Pages(_lotTotal):N0} 페이지 (LOT {_lotTotal:N0}건)";
        public string LotSummaryText => $"조회 합계 {_lotTotalQty:N0} {SelectedItem?.Uom}";
        public string HistoryPageText => $"{_historyPage:N0} / {Pages(_historyTotal):N0} 페이지 (총 {_historyTotal:N0}건)";
        private static int Pages(int total) => Math.Max(1, (int)Math.Ceiling(total / (double)DetailPageSize));

        public bool IsHistoryOpen
        {
            get => _isHistoryOpen;
            private set
            {
                if (SetProperty(ref _isHistoryOpen, value)) NotifySelection();
            }
        }

        public InventoryLotDto? SelectedLot
        {
            get => _selectedLot;
            set
            {
                if (!SetProperty(ref _selectedLot, value) || _updatingLots) return;
                ResetHistory();
                NotifySelection();
            }
        }

        public Task InitializeAsync() => SearchAsync();

        protected override async Task<bool> LoadListAsync()
        {
            var version = ++_listVersion;
            var route = $"{ApiRoutes.Inventories}?page={ListPage}&size={ListPageSize}&include_zero={IncludeZeroStock.ToString().ToLowerInvariant()}";
            if (!string.IsNullOrWhiteSpace(SearchKeyword)) route += $"&q={Uri.EscapeDataString(SearchKeyword.Trim())}";
            var result = await _api.GetAsync<InventoryListDto>(route);
            if (version != _listVersion) return false;
            if (!result.Success || result.Data == null)
            {
                _messages.ShowError(result.Message ?? "재고 조회 중 오류가 발생했습니다.");
                return false;
            }
            var selectedId = SelectedItem?.ProductId;
            _updatingProducts = true;
            try
            {
                Items.Clear();
                foreach (var item in result.Data.Items) Items.Add(item);
                SelectedItem = Items.FirstOrDefault(x => x.ProductId == selectedId);
                ApplyListPage(result.Data.Total, result.Data.Page, result.Data.Size);
            }
            finally { _updatingProducts = false; }
            if (_activeProductId != SelectedItem?.ProductId) OnSelectedItemChanged(SelectedItem);
            else if (SelectedItem != null) await LoadLotsAsync(_lotPage);
            NotifySelection();
            return true;
        }

        protected override void Reset()
        {
            ++_listVersion;
            SearchKeyword = string.Empty;
            IncludeZeroStock = false;
            SelectedItem = null;
            Items.Clear();
            ResetListPage();
        }
        protected override void New() => SelectedItem = null;

        protected override void OnSelectedItemChanged(InventoryDto? item)
        {
            if (_updatingProducts || _activeProductId == item?.ProductId) return;
            _activeProductId = item?.ProductId;
            ++_lotVersion;
            SelectedLot = null;
            ResetHistory();
            Lots.Clear();
            _lotPage = 1; _lotTotal = 0; _lotTotalQty = 0;
            LotKeyword = string.Empty;
            SelectedMovementType = "전체"; DateFrom = null; DateTo = null;
            LotsLoading = item != null;
            LotStatus = item == null ? "품목을 선택하세요." : "선택한 품목의 재고 조회를 준비하고 있습니다…";
            NotifySelection();
            if (item != null) _ = LoadSelectedLotsAfterDelayAsync(_lotVersion);
        }

        private async Task LoadSelectedLotsAfterDelayAsync(int selectionVersion)
        {
            await Task.Delay(ProductSelectionDelayMs);
            // A new selection, reset or explicit refresh supersedes this pending lookup.
            // Keep the existing response version check for requests already sent.
            if (selectionVersion != _lotVersion || SelectedItem == null) return;
            await LoadLotsAsync(1);
        }

        private async Task LoadLotsAsync(int page)
        {
            var product = SelectedItem;
            if (product == null) return;
            var version = ++_lotVersion;
            // A newer stock lookup supersedes every older history snapshot as well.
            ++_historyVersion;
            HistoryLoading = false;
            Movements.Clear(); _historyTotal = 0;
            OnPropertyChanged(nameof(HistoryPageText));
            var keyword = LotKeyword.Trim();
            var includeZero = IncludeZeroStock || product.CurrentQty == 0;
            LotsLoading = true;
            LotStatus = "LOT 재고를 조회하고 있습니다…";
            try
            {
                var route = $"{ApiRoutes.Inventories}/{product.ProductId}/lots?page={Math.Max(1, page)}&size={DetailPageSize}&include_zero={includeZero.ToString().ToLowerInvariant()}";
                if (keyword.Length > 0) route += $"&q={Uri.EscapeDataString(keyword)}";
                var result = await _api.GetAsync<InventoryLotListDto>(route);
                if (version != _lotVersion || SelectedItem?.ProductId != product.ProductId) return;
                var data = result.Data;
                if (!result.Success || data == null) { ClearLots(result.Message ?? "LOT 재고를 조회하지 못했습니다. 다시 조회하세요."); return; }
                if (!IsValidLotSnapshot(data, product.ProductId))
                { ClearLots("LOT 조회 응답이 올바르지 않습니다. 서버 버전을 확인하세요."); return; }
                if (page > Pages(data.Total)) { await LoadLotsAsync(Pages(data.Total)); return; }
                _loadedLotKeyword = keyword;
                _loadedIncludeZero = includeZero;
                ApplyLotSnapshot(product, data);
                // Apply this request's status before awaiting history. A new selection
                // may take ownership of the screen while that nested request runs.
                if (IsHistoryOpen && SelectedLot != null) await LoadHistoryAsync(_historyPage);
            }
            catch (Exception)
            {
                if (version == _lotVersion) ClearLots("LOT 재고 조회 중 오류가 발생했습니다. 다시 조회하세요.");
            }
            finally { if (version == _lotVersion) LotsLoading = false; }
        }

        private void OpenHistory()
        {
            if (!HasSelectedLot) return;
            IsHistoryOpen = true;
            _ = LoadHistoryAsync(1);
        }

        private async Task LoadHistoryAsync(int page)
        {
            var product = SelectedItem;
            var lot = SelectedLot;
            if (!IsHistoryOpen || product == null || lot == null) return;
            var version = ++_historyVersion;
            var lotVersion = _lotVersion;
            Movements.Clear();
            _historyTotal = 0; _historyPage = 1;
            OnPropertyChanged(nameof(HistoryPageText));
            if (DateFrom.HasValue && DateTo.HasValue && DateFrom.Value.Date > DateTo.Value.Date)
            { HistoryLoading = false; HistoryStatus = "시작일은 종료일보다 늦을 수 없습니다."; return; }
            HistoryLoading = true;
            HistoryStatus = "선택한 LOT의 입·출고 이력을 조회하고 있습니다…";
            try
            {
                var parts = new List<string> { $"product_id={product.ProductId}", $"product_inventory_lot_id={lot.ProductInventoryLotId}", $"page={Math.Max(1, page)}", $"size={DetailPageSize}" };
                parts.Add($"stock_page={_lotPage}");
                parts.Add($"stock_size={DetailPageSize}");
                parts.Add($"stock_include_zero={_loadedIncludeZero.ToString().ToLowerInvariant()}");
                if (_loadedLotKeyword.Length > 0) parts.Add($"stock_q={Uri.EscapeDataString(_loadedLotKeyword)}");
                var type = ToMovementTypeCode(SelectedMovementType);
                if (type.Length > 0) parts.Add($"movement_type={type}");
                if (DateFrom.HasValue) parts.Add($"date_from={DateFrom.Value:yyyy-MM-dd}");
                if (DateTo.HasValue) parts.Add($"date_to={DateTo.Value:yyyy-MM-dd}");
                var result = await _api.GetAsync<InventoryMovementListDto>($"{ApiRoutes.InventoryMovements}?{string.Join("&", parts)}");
                if (version != _historyVersion || lotVersion != _lotVersion || SelectedItem?.ProductId != product.ProductId || SelectedLot?.ProductInventoryLotId != lot.ProductInventoryLotId) return;
                var data = result.Data;
                if (!result.Success || data == null) { HistoryStatus = result.Message ?? "이력을 조회하지 못했습니다. 다시 조회하세요."; return; }
                if (data.ProductInventoryLotId != lot.ProductInventoryLotId || data.Items.Any(x => x.ProductId != product.ProductId || x.ProductInventoryLotId != lot.ProductInventoryLotId))
                { HistoryStatus = "선택한 LOT의 이력인지 확인할 수 없습니다. 서버 버전을 확인하세요."; return; }
                var snapshot = data.StockSnapshot;
                if (snapshot == null || !IsValidLotSnapshot(snapshot, product.ProductId) || !data.CurrentQty.HasValue
                    || snapshot.Items.Any(x => x.ProductInventoryLotId == lot.ProductInventoryLotId && x.CurrentQty != data.CurrentQty.Value))
                { HistoryStatus = "재고 합계와 이력을 함께 확인할 수 없습니다. 서버 버전을 확인하세요."; return; }
                if (page > Pages(data.Total)) { await LoadHistoryAsync(Pages(data.Total)); return; }
                ApplyLotSnapshot(product, snapshot);
                if (SelectedLot == null) return;
                foreach (var item in data.Items) Movements.Add(item);
                _historyPage = data.Page; _historyTotal = data.Total;
                HistoryStatus = data.HistoryWarning ?? (Movements.Count == 0 ? "조회 조건에 해당하는 이력이 없습니다." : "최신 처리 순서입니다. 처리 후 재고는 각 처리 직후의 LOT 잔액입니다. 정정 수량은 음수로 표시됩니다.");
                NotifySelection();
            }
            catch (Exception)
            {
                if (version == _historyVersion) HistoryStatus = "재고 이력 조회 중 오류가 발생했습니다. 다시 조회하세요.";
            }
            finally { if (version == _historyVersion) HistoryLoading = false; }
        }

        private static bool IsValidLotSnapshot(InventoryLotListDto data, long productId) =>
            data.ProductId == productId && data.Page >= 1 && data.Size == DetailPageSize && data.Total >= 0
            && data.Items.All(x => x.ProductId == productId && x.ProductInventoryLotId > 0)
            && data.Items.Select(x => x.ProductInventoryLotId).Distinct().Count() == data.Items.Count;

        private void ApplyLotSnapshot(InventoryDto product, InventoryLotListDto data)
        {
            // Preserve the user's selection at response time, including a cleared selection.
            var selectedId = SelectedLot?.ProductInventoryLotId;
            _lotPage = data.Page; _lotTotal = data.Total; _lotTotalQty = data.TotalQty;
            product.CurrentQty = data.ProductCurrentQty;
            product.UpdatedAt = data.ProductUpdatedAt;
            _updatingLots = true;
            try
            {
                Lots.Clear();
                foreach (var item in data.Items) Lots.Add(item);
                SelectedLot = Lots.FirstOrDefault(x => x.ProductInventoryLotId == selectedId);
            }
            finally { _updatingLots = false; }
            if (SelectedLot == null) ResetHistory();
            LotStatus = data.StockWarning ?? (Lots.Count == 0 ? "조회 조건에 해당하는 LOT가 없습니다. 재고 0 포함 여부를 확인하세요." : "LOT 선택 후 상세보기로 이력을 확인하세요. 현재 재고는 예약수량을 포함합니다.");
            NotifySelection();
        }

        private void ClearLots(string message)
        {
            SelectedLot = null;
            Lots.Clear();
            _lotPage = 1; _lotTotal = 0; _lotTotalQty = 0;
            LotStatus = message;
            NotifySelection();
        }
        private void ResetHistory()
        {
            ++_historyVersion;
            IsHistoryOpen = false;
            Movements.Clear(); _historyPage = 1; _historyTotal = 0;
            HistoryLoading = false;
            HistoryStatus = "상세보기를 누르면 선택한 LOT의 입·출고 이력이 이곳에 표시됩니다.";
        }
        private void NotifySelection()
        {
            OnPropertyChanged(nameof(HasSelectedLot));
            OnPropertyChanged(nameof(SelectedProductText));
            OnPropertyChanged(nameof(SelectedLotText));
            OnPropertyChanged(nameof(LotPageText));
            OnPropertyChanged(nameof(LotSummaryText));
            OnPropertyChanged(nameof(HistoryPageText));
            RefreshCommands();
        }
        private void RefreshCommands()
        {
            LoadLotsCommand.RaiseCanExecuteChanged(); LotPreviousCommand.RaiseCanExecuteChanged(); LotNextCommand.RaiseCanExecuteChanged();
            OpenHistoryCommand.RaiseCanExecuteChanged(); OpenAdjustmentCommand.RaiseCanExecuteChanged();
            SearchHistoryCommand.RaiseCanExecuteChanged(); HistoryPreviousCommand.RaiseCanExecuteChanged(); HistoryNextCommand.RaiseCanExecuteChanged(); ClearHistoryPeriodCommand.RaiseCanExecuteChanged();
        }
        private void OpenAdjustment()
        {
            if (SelectedItem == null || SelectedLot == null) return;
            var viewModel = new InventoryAdjustmentWindowViewModel(_api, _messages, SelectedItem, SelectedLot);
            viewModel.CloseRequested += saved => { if (saved) SearchCommand.Execute(null); };
            RequestOpenAdjustment?.Invoke(viewModel);
        }
        private void OpenInitialInventoryBulkUpload()
        {
            var viewModel = new InitialInventoryBulkUploadWindowViewModel(_api, _messages);
            viewModel.UploadCompleted += () => SearchCommand.Execute(null);
            RequestOpenInitialInventoryBulkUpload?.Invoke(viewModel);
        }
        private async Task CheckConsistencyAsync()
        {
            var result = await _api.GetAsync<InventoryConsistencyListDto>(ApiRoutes.InventoryConsistency);
            if (!result.Success || result.Data == null) { _messages.ShowError(result.Message ?? "재고 정합성 점검 중 오류가 발생했습니다."); return; }
            if (result.Data.Total == 0) { _messages.ShowInfo("재고 정합성 불일치 품목이 없습니다."); return; }
            var preview = string.Join(Environment.NewLine, result.Data.Items.Take(10).Select(x => $"{x.ProductCode} / 총재고 {x.CurrentQty:N0} / LOT합계 {x.LotQty:N0} / 이력합계 {x.MovementQty:N0}"));
            _messages.ShowWarning($"재고 정합성 불일치 품목 {result.Data.Total:N0}건이 있습니다.\n\n{preview}", "재고 정합성 점검");
        }
        private static string ToMovementTypeCode(string label) => label switch
        {
            "기초재고" => "INITIAL_STOCK", "검수입고" => "INSPECTION_IN", "출고" => "SHIP_OUT", "재고증가" => "ADJUST_IN", "재고감소" => "ADJUST_OUT", _ => string.Empty
        };
    }
}
