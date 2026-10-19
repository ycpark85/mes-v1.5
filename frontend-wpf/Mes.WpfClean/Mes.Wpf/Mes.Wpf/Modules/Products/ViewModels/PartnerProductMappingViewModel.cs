using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.OrderLines.Dtos;
using Mes.Wpf.Modules.Products.Dtos;
using System.Collections.ObjectModel;

namespace Mes.Wpf.Modules.Products.ViewModels;

public class PartnerProductMappingViewModel : ViewModelBase
{
    private readonly ProductDto _product;
    private bool _isBusy;
    private int _page = 1;
    private int _total;
    private string _status = "연결 목록을 불러오세요.";
    private string _erpCode = string.Empty;
    private string _customerName;
    private string? _customerSpec;
    private OrderLinePartnerLookupDto? _partner;
    private PartnerProductMappingDto? _selected;

    public PartnerProductMappingViewModel(IApiClient api, IMessageService messages, ProductDto product)
    {
        ApiClient = api;
        MessageService = messages;
        _product = product;
        _customerName = product.ProductName;
        _customerSpec = product.ProductSpec;
        RefreshCommand = new AsyncRelayCommand(RefreshAsync, () => !IsBusy);
        AddCommand = new AsyncRelayCommand(AddAsync, () => !IsBusy);
        DeactivateCommand = new AsyncRelayCommand(DeactivateAsync, () => !IsBusy && SelectedMapping?.IsActive == true);
        PreviousCommand = new AsyncRelayCommand(async () => { _page--; await RefreshAsync(); }, () => !IsBusy && _page > 1);
        NextCommand = new AsyncRelayCommand(async () => { _page++; await RefreshAsync(); }, () => !IsBusy && _page * 20 < _total);
    }

    public IApiClient ApiClient { get; }
    public IMessageService MessageService { get; }
    public string ProductSummary => $"{_product.ProductCode} · {_product.ProductName} · 도면 {_product.DrawingNo}";
    public ObservableCollection<PartnerProductMappingDto> Items { get; } = new();
    public AsyncRelayCommand RefreshCommand { get; }
    public AsyncRelayCommand AddCommand { get; }
    public AsyncRelayCommand DeactivateCommand { get; }
    public AsyncRelayCommand PreviousCommand { get; }
    public AsyncRelayCommand NextCommand { get; }
    public bool IsBusy { get => _isBusy; private set { SetProperty(ref _isBusy, value); OnPropertyChanged(nameof(CanEdit)); NotifyCommands(); } }
    public bool CanEdit => !IsBusy;
    public string StatusText { get => _status; private set => SetProperty(ref _status, value); }
    public string PageText => $"{_page} / {Math.Max(1, (_total + 19) / 20)} 페이지 · 전체 {_total}건 (해제 이력 포함)";
    public string ErpCode { get => _erpCode; set => SetProperty(ref _erpCode, value); }
    public string CustomerName { get => _customerName; set => SetProperty(ref _customerName, value); }
    public string? CustomerSpec { get => _customerSpec; set => SetProperty(ref _customerSpec, value); }
    public string PartnerName => _partner?.Name ?? "고객 거래처를 선택하세요";
    public PartnerProductMappingDto? SelectedMapping { get => _selected; set { SetProperty(ref _selected, value); DeactivateCommand.RaiseCanExecuteChanged(); } }

    public void SelectPartner(OrderLinePartnerLookupDto partner)
    {
        if (IsBusy) return;
        if (partner.PartnerType != "CUSTOMER") { MessageService.ShowWarning("고객 거래처를 선택하세요."); return; }
        _partner = partner;
        OnPropertyChanged(nameof(PartnerName));
    }

    private void NotifyCommands()
    {
        RefreshCommand.RaiseCanExecuteChanged(); AddCommand.RaiseCanExecuteChanged(); DeactivateCommand.RaiseCanExecuteChanged();
        PreviousCommand.RaiseCanExecuteChanged(); NextCommand.RaiseCanExecuteChanged();
    }

    public async Task RefreshAsync()
    {
        if (IsBusy) return;
        IsBusy = true;
        try { await LoadAsync(); }
        finally { IsBusy = false; }
    }

    private async Task LoadAsync()
    {
        StatusText = "연결 목록을 불러오는 중입니다...";
        var result = await ApiClient.GetAsync<PagedResult<PartnerProductMappingDto>>(
            $"{ApiRoutes.Products}/{_product.ProductId}/partner-mappings?page={_page}&size=20&include_inactive=true");
        Items.Clear();
        SelectedMapping = null;
        if (!result.Success || result.Data == null)
        {
            StatusText = result.Message ?? "연결 목록을 불러오지 못했습니다. 새로고침을 눌러 재시도하세요.";
            MessageService.ShowError(StatusText);
            return;
        }
        _total = result.Data.Total;
        foreach (var row in result.Data.Items) Items.Add(row);
        OnPropertyChanged(nameof(PageText));
        StatusText = Items.Count == 0 ? "등록된 연결이 없습니다. 아래에서 첫 거래처를 연결하세요." : "거래처와 ERP 코드로 수주를 자동 연결합니다. 품명은 구분 기준에 포함되지 않습니다.";
    }

    public async Task AddAsync()
    {
        if (IsBusy) return;
        var code = ErpCode.Trim().ToUpperInvariant();
        var name = CustomerName.Trim();
        if (_partner == null || code.Length is < 1 or > 60 || name.Length is < 1 or > 200 || CustomerSpec?.Trim().Length > 100)
        {
            MessageService.ShowWarning("고객 거래처, ERP 코드(60자 이내), 거래처 품명(200자 이내)을 입력하세요. 규격은 100자 이내입니다.");
            return;
        }
        var request = new PartnerProductMappingCreateRequest
        {
            PartnerId = _partner.PartnerId, ErpProductCode = code, CustomerProductName = name,
            CustomerProductSpec = string.IsNullOrWhiteSpace(CustomerSpec) ? null : CustomerSpec.Trim()
        };
        IsBusy = true;
        try
        {
            var result = await ApiClient.PostAsync<PartnerProductMappingCreateRequest, PartnerProductMappingDto>(
                $"{ApiRoutes.Products}/{_product.ProductId}/partner-mappings", request);
            if (!result.Success || result.Data == null) { MessageService.ShowError(result.Message ?? "연결하지 못했습니다."); return; }
            _page = 1;
            await LoadAsync();
            MessageService.ShowInfo("거래처가 연결되었습니다. 수주 엑셀을 다시 검증하면 연결 결과를 확인할 수 있습니다.");
        }
        finally { IsBusy = false; }
    }

    public async Task DeactivateAsync()
    {
        var selected = SelectedMapping;
        if (IsBusy || selected?.IsActive != true) return;
        if (!MessageService.Confirm($"{selected.PartnerName} / {selected.ErpProductCode} 연결을 해제하시겠습니까?\n기존 수주는 유지됩니다. 이후 수주는 재연결 전까지 등록되지 않습니다.", "연결 해제")) return;
        IsBusy = true;
        try
        {
            var result = await ApiClient.DeleteAsync($"{ApiRoutes.Products}/{_product.ProductId}/partner-mappings/{selected.MappingId}");
            if (!result.Success || !result.Data) { MessageService.ShowError(result.Message ?? "연결을 해제하지 못했습니다."); return; }
            await LoadAsync();
        }
        finally { IsBusy = false; }
    }
}
