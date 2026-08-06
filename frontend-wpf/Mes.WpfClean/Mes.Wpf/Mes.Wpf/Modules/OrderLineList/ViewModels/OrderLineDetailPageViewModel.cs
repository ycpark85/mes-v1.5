using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.OrderLineList.Dtos;
using Mes.Wpf.Modules.LotDetails.ViewModels;
using Mes.Wpf.Modules.LotDetails.Views;

using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.OrderLineList.ViewModels
{
    public class OrderLineDetailPageViewModel : CrudPageViewModelBase<OrderLineDetailLotDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly Func<Task>? _goBackAsync;
        private readonly Func<long, Task>? _openLotDetailAsync;

        private long _orderLineId;
        private bool _isEditMode;

        private string _orderNo = string.Empty;
        private int _lineNo;

        private long _partnerId;
        private string _partnerName = string.Empty;

        private long _productId;
        private string _productCode = string.Empty;
        private string _productName = string.Empty;

        private DateTime _orderDate;
        private DateTime _dueDate;
        private int _orderQty;
        private int _loadedOrderQty;
        private string _uom = string.Empty;

        private string? _customerPo;
        private string? _memo;

        private string _status = string.Empty;
        private string _statusDisplay = string.Empty;
        private bool _isActive;

        private bool _canEdit;
        private bool _canSave;
        private bool _canCancelOrder;
        private bool _canCreateBaseLot;

        public OrderLineDetailPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            Func<Task>? goBackAsync = null,
            Func<long, Task>? openLotDetailAsync = null)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _goBackAsync = goBackAsync;
            _openLotDetailAsync = openLotDetailAsync;

            Lots = new ObservableCollection<OrderLineDetailLotDto>();
            Timeline = new ObservableCollection<OrderLineTimelineItemDto>();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            CancelOrderCommand = new AsyncRelayCommand(CancelOrderAsync);
            RefreshCommand = new AsyncRelayCommand(RefreshAsync);
            CreateBaseLotCommand = new AsyncRelayCommand(CreateBaseLotAsync);
            OpenLotDetailCommand = new AsyncRelayCommand(OpenLotDetailAsync);
            EditCommand = new RelayCommand(EnterEditMode);
            BackCommand = new AsyncRelayCommand(BackAsync);
            
        }

        public ObservableCollection<OrderLineDetailLotDto> Lots { get; }
        public ObservableCollection<OrderLineTimelineItemDto> Timeline { get; }

        public AsyncRelayCommand SaveCommand { get; }
        public AsyncRelayCommand CancelOrderCommand { get; }
        public AsyncRelayCommand RefreshCommand { get; }
        public AsyncRelayCommand CreateBaseLotCommand { get; }
        public AsyncRelayCommand OpenLotDetailCommand { get; }

        public AsyncRelayCommand BackCommand { get; }
        public RelayCommand EditCommand { get; }

        public long OrderLineId
        {
            get => _orderLineId;
            set => SetProperty(ref _orderLineId, value);
        }

        public bool IsEditMode
        {
            get => _isEditMode;
            set
            {
                if (SetProperty(ref _isEditMode, value))
                {
                    OnPropertyChanged(nameof(IsReadOnly));
                    OnPropertyChanged(nameof(CanEditNow));
                    OnPropertyChanged(nameof(CanSaveNow));
                }
            }
        }

        public bool IsReadOnly => !IsEditMode;

        public string OrderNo
        {
            get => _orderNo;
            set => SetProperty(ref _orderNo, value);
        }

        public int LineNo
        {
            get => _lineNo;
            set => SetProperty(ref _lineNo, value);
        }

        public long PartnerId
        {
            get => _partnerId;
            set => SetProperty(ref _partnerId, value);
        }

        public string PartnerName
        {
            get => _partnerName;
            set => SetProperty(ref _partnerName, value);
        }

        public long ProductId
        {
            get => _productId;
            set => SetProperty(ref _productId, value);
        }

        public string ProductCode
        {
            get => _productCode;
            set => SetProperty(ref _productCode, value);
        }

        public string ProductName
        {
            get => _productName;
            set => SetProperty(ref _productName, value);
        }

        public DateTime OrderDate
        {
            get => _orderDate;
            set => SetProperty(ref _orderDate, value);
        }

        public DateTime DueDate
        {
            get => _dueDate;
            set => SetProperty(ref _dueDate, value);
        }

        public int OrderQty
        {
            get => _orderQty;
            set => SetProperty(ref _orderQty, value);
        }

        public string Uom
        {
            get => _uom;
            set => SetProperty(ref _uom, value);
        }

        public string? CustomerPo
        {
            get => _customerPo;
            set => SetProperty(ref _customerPo, value);
        }

        public string? Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public string Status
        {
            get => _status;
            set => SetProperty(ref _status, value);
        }

        public string StatusDisplay
        {
            get => _statusDisplay;
            set => SetProperty(ref _statusDisplay, value);
        }

        public bool IsActive
        {
            get => _isActive;
            set => SetProperty(ref _isActive, value);
        }

        public bool CanEdit
        {
            get => _canEdit;
            set
            {
                if (SetProperty(ref _canEdit, value))
                {
                    OnPropertyChanged(nameof(CanEditNow));
                    OnPropertyChanged(nameof(CanSaveNow));
                }
            }
        }

        public bool CanSave
        {
            get => _canSave;
            set
            {
                if (SetProperty(ref _canSave, value))
                {
                    OnPropertyChanged(nameof(CanSaveNow));
                }
            }
        }

        public bool CanCancelOrder
        {
            get => _canCancelOrder;
            set => SetProperty(ref _canCancelOrder, value);
        }

        public bool CanCreateBaseLot
        {
            get => _canCreateBaseLot;
            set => SetProperty(ref _canCreateBaseLot, value);
        }

        public bool CanEditNow => CanEdit && !IsEditMode;
        public bool CanSaveNow => CanSave && IsEditMode;
        public bool HasSelectedLot => SelectedItem != null;

        public async Task InitializeAsync(long orderLineId)
        {
            OrderLineId = orderLineId;
            await SearchAsync();
        }

        protected override async Task LoadListAsync()
        {
            if (OrderLineId <= 0)
            {
                _messageService.ShowWarning("유효한 수주 ID가 없습니다.");
                return;
            }

            var result = await _apiClient.GetAsync<OrderLineDetailDto>(
                $"{ApiRoutes.OrderLines}/{OrderLineId}/detail"
            );

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "수주상세 조회 중 오류가 발생했습니다.");
                return;
            }

            ApplyDetail(result.Data);
            IsEditMode = false;
        }

        protected override void Reset()
        {
            IsEditMode = false;
            SelectedItem = null;
        }

        protected override void New()
        {
            // 상세 화면에서는 신규 생성 사용 안 함
        }

        protected override void OnSelectedItemChanged(OrderLineDetailLotDto? item)
        {
            OnPropertyChanged(nameof(HasSelectedLot));
        }

        private async Task BackAsync()
        {
            if (_goBackAsync == null)
            {
                _messageService.ShowWarning("목록 화면 연결이 설정되지 않았습니다.");
                return;
            }

            await _goBackAsync();
        }

        private void ApplyDetail(OrderLineDetailDto dto)
        {
            OrderLineId = dto.OrderLineId;
            OrderNo = dto.OrderNo;
            LineNo = dto.LineNo;

            PartnerId = dto.PartnerId;
            PartnerName = dto.PartnerName;

            ProductId = dto.ProductId;
            ProductCode = dto.ProductCode;
            ProductName = dto.ProductName;

            OrderDate = dto.OrderDate;
            DueDate = dto.DueDate;
            OrderQty = dto.OrderQty;
            _loadedOrderQty = dto.OrderQty;
            Uom = dto.Uom;

            CustomerPo = dto.CustomerPo;
            Memo = dto.Memo;

            Status = dto.Status;
            StatusDisplay = dto.StatusDisplay;
            IsActive = dto.IsActive;

            CanEdit = dto.CanEdit;
            CanSave = dto.CanSave;
            CanCancelOrder = dto.CanCancelOrder;
            CanCreateBaseLot = dto.CanCreateBaseLot;

            Lots.Clear();
            foreach (var lot in dto.Lots)
                Lots.Add(lot);

            Timeline.Clear();
            foreach (var item in dto.Timeline)
                Timeline.Add(item);

            SelectedItem = null;
        }

        public void EnterEditMode()
        {
            if (!CanEdit)
            {
                _messageService.ShowWarning("현재 상태에서는 수정할 수 없습니다.");
                return;
            }

            IsEditMode = true;
        }

        private async Task RefreshAsync()
        {
            await SearchAsync();
        }

        private async Task SaveAsync()
        {
            if (!CanSave)
            {
                _messageService.ShowWarning("현재 상태에서는 저장할 수 없습니다.");
                return;
            }

            if (!IsEditMode)
            {
                _messageService.ShowWarning("수정 모드에서만 저장할 수 있습니다.");
                return;
            }

            if (OrderQty <= 0)
            {
                _messageService.ShowWarning("수주수량은 0보다 커야 합니다.");
                return;
            }

            if (OrderQty != _loadedOrderQty)
            {
                var impactMessage = Lots.Count == 0
                    ? $"수주수량을 {_loadedOrderQty:N0}에서 {OrderQty:N0}(으)로 변경합니다.\n기존 처리계획은 해제되며 다시 확인해야 합니다.\n계속하시겠습니까?"
                    : $"수주수량을 {_loadedOrderQty:N0}에서 {OrderQty:N0}(으)로 변경합니다.\n작업이 시작되지 않은 LOT라면 처리계획과 LOT 수량도 함께 변경됩니다.\n부분재고 계획은 기존 예약재고를 유지하고 부족 생산량을 다시 계산합니다.\n계속하시겠습니까?";

                if (!_messageService.Confirm(impactMessage, "수주수량 변경 확인"))
                {
                    return;
                }
            }

            IsLoading = true;
            try
            {
                var request = new OrderLineDetailUpdateRequest
                {
                    DueDate = DueDate,
                    OrderQty = OrderQty,
                    Memo = Memo
                };

                var result = await _apiClient.PatchAsync<OrderLineDetailUpdateRequest, OrderLineDetailDto>(
                    $"{ApiRoutes.OrderLines}/{OrderLineId}/detail",
                    request
                );

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "수주상세 저장 중 오류가 발생했습니다.");
                    return;
                }

                ApplyDetail(result.Data);
                IsEditMode = false;
                _messageService.ShowInfo("저장되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task CancelOrderAsync()
        {
            if (!CanCancelOrder)
            {
                _messageService.ShowWarning("현재 수주는 취소할 수 없습니다.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{OrderNo}] 수주를 취소하시겠습니까?",
                "수주 취소 확인"
            );
            if (!confirmed)
                return;

            IsLoading = true;
            try
            {
                var result = await _apiClient.PostAsync<object, OrderLineDetailDto>(
                    $"{ApiRoutes.OrderLines}/{OrderLineId}/cancel",
                    new { }
                );

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "수주취소 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();
                IsEditMode = false;
                _messageService.ShowInfo("수주가 취소되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task CreateBaseLotAsync()
        {
            if (!CanCreateBaseLot)
            {
                _messageService.ShowWarning("현재 상태에서는 기본 LOT를 생성할 수 없습니다.");
                return;
            }

            await Task.CompletedTask;
            _messageService.ShowInfo($"기본 LOT 생성 연결 예정: OrderLineId={OrderLineId}");
        }

        private async Task OpenLotDetailAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("LOT를 먼저 선택하세요.");
                return;
            }

            if (SelectedItem.LotId <= 0)
            {
                _messageService.ShowWarning("LOT 정보가 없습니다.");
                return;
            }

            var windowVm = new LotDetailWindowViewModel(_apiClient, _messageService);

            await windowVm.InitializeAsync(SelectedItem.LotId);

            var window = new LotDetailWindow(windowVm);
            window.ShowDialog();
        }
    }
}
