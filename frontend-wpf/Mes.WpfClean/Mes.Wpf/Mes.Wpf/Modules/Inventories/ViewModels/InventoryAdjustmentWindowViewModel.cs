using System;
using System.Threading.Tasks;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Inventories.Dtos;

namespace Mes.Wpf.Modules.Inventories.ViewModels
{
    public class InventoryAdjustmentWindowViewModel : ViewModelBase
    {
        private readonly IApiClient _api;
        private readonly IMessageService _messages;
        private readonly long _productId;
        private readonly long _lotId;
        private string _direction = "재고증가";
        private long _qty;
        private string _memo = string.Empty;
        private bool _isLoading;
        public InventoryAdjustmentWindowViewModel(IApiClient api, IMessageService messages,
            InventoryDto product, InventoryLotDto lot)
        {
            _api = api; _messages = messages;
            _productId = product.ProductId; _lotId = lot.ProductInventoryLotId;
            ProductName = product.ProductName; LotNo = lot.LotNo; CurrentQty = lot.CurrentQty; Uom = product.Uom;
            SaveCommand = new AsyncRelayCommand(SaveAsync, () => !IsLoading);
            CloseCommand = new RelayCommand(() => CloseRequested?.Invoke(false), () => !IsLoading);
        }
        public event Action<bool>? CloseRequested;
        public string ProductName { get; }
        public string LotNo { get; }
        public long CurrentQty { get; }
        public string Uom { get; }
        public string[] Directions { get; } = new[] { "재고증가", "재고감소" };
        public string Direction { get => _direction; set => SetProperty(ref _direction, value); }
        public long Qty { get => _qty; set => SetProperty(ref _qty, value); }
        public string Memo { get => _memo; set => SetProperty(ref _memo, value); }
        public bool IsLoading
        {
            get => _isLoading;
            private set
            {
                SetProperty(ref _isLoading, value);
                OnPropertyChanged(nameof(CanInput));
                SaveCommand.RaiseCanExecuteChanged();
                CloseCommand.RaiseCanExecuteChanged();
            }
        }
        public bool CanInput => !IsLoading;
        public AsyncRelayCommand SaveCommand { get; }
        public RelayCommand CloseCommand { get; }
        private async Task SaveAsync()
        {
            if (Qty <= 0 || string.IsNullOrWhiteSpace(Memo) || Memo.Trim().Length > 1000)
            {
                _messages.ShowWarning("1 이상의 조정수량과 1,000자 이내의 조정 사유를 입력하세요.");
                return;
            }
            if (!Array.Exists(Directions, item => item == Direction)) return;
            if (!_messages.Confirm($"{ProductName}\nLOT: {LotNo}\n{Direction}: {Qty:N0} {Uom}\n사유: {Memo.Trim()}", "재고 조정 확인")) return;
            IsLoading = true;
            try
            {
                var request = new InventoryAdjustmentRequest { Qty = Qty, Memo = Memo.Trim() };
                var response = await _api.PostAsync<InventoryAdjustmentRequest, InventoryMovementDto>(
                    $"{ApiRoutes.Inventories}/{_productId}/lots/{_lotId}/adjust?direction={(Direction == "재고증가" ? "IN" : "OUT")}", request);
                if (!response.Success || response.Data is null)
                {
                    _messages.ShowError(response.Message ?? "재고 조정 응답을 확인하지 못했습니다. 재시도 전 재고와 이력을 조회하세요.");
                    return;
                }
                _messages.ShowInfo("선택한 LOT의 재고 조정이 완료되었습니다.");
                IsLoading = false;
                CloseRequested?.Invoke(true);
            }
            finally { IsLoading = false; }
        }
    }
}
