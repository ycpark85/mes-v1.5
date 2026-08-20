using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows.Input;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Lots.Dtos;
using Mes.Wpf.Modules.Products.Dtos;


namespace Mes.Wpf.Modules.Products.ViewModels
{
    public class ProductMonitoringPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly IDrawingViewer _drawingViewer;

        private string _partnerKeyword = string.Empty;
        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private bool _isLoading;
        private string _loadingMessage = "처리 중입니다...";
        private ProductDto? _selectedProduct;
        private LotListItemDto? _selectedLot;
        private int _productPage = 1;
        private int _productPageSize = 100;
        private int _productTotalCount;

        public ProductMonitoringPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            IDrawingViewer drawingViewer)
        {
            _apiClient = apiClient;
            _messageService = messageService;   
            _drawingViewer = drawingViewer;

            ProductItems = new ObservableCollection<ProductDto>();
            LotItems = new ObservableCollection<LotListItemDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };

            SearchCommand = new AsyncRelayCommand(SearchFirstPageAsync);
            ResetCommand = new AsyncRelayCommand(ResetAsync);
            LoadHistoryCommand = new AsyncRelayCommand(LoadHistoryAsync);
            OpenLotDetailCommand = new RelayCommand(_ => OpenLotDetail());
            ProductPreviousPageCommand = new AsyncRelayCommand(
                LoadPreviousProductPageAsync,
                () => ProductHasPreviousPage && !IsLoading);
            ProductNextPageCommand = new AsyncRelayCommand(
                LoadNextProductPageAsync,
                () => ProductHasNextPage && !IsLoading);
           
        }

        public event Action<long>? RequestOpenLotDetail;

        public ObservableCollection<ProductDto> ProductItems { get; }

        public ObservableCollection<LotListItemDto> LotItems { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public ICommand SearchCommand { get; }

        public ICommand ResetCommand { get; }

        public ICommand LoadHistoryCommand { get; }

        public ICommand OpenLotDetailCommand { get; }

        public ICommand ProductPreviousPageCommand { get; }

        public ICommand ProductNextPageCommand { get; }

        public int ProductTotalPages => Math.Max(1, (int)Math.Ceiling((double)_productTotalCount / _productPageSize));

        public bool ProductHasPreviousPage => _productPage > 1;

        public bool ProductHasNextPage => _productPage < ProductTotalPages;

        public string ProductPageDisplayText => $"{_productPage:N0} / {ProductTotalPages:N0} 페이지 (총 {_productTotalCount:N0}건)";

        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public string PartnerKeyword
        {
            get => _partnerKeyword;
            set => SetProperty(ref _partnerKeyword, value);
        }

        public string SelectedUseYn
        {
            get => _selectedUseYn;
            set => SetProperty(ref _selectedUseYn, value);
        }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    RaiseProductPageCommandStates();
                }
            }
        }

        public string LoadingMessage
        {
            get => _loadingMessage;
            set => SetProperty(ref _loadingMessage, value);
        }

        public ProductDto? SelectedProduct
        {
            get => _selectedProduct;
            set
            {
                if (SetProperty(ref _selectedProduct, value))
                {
                    SelectedLot = null;
                    OnPropertyChanged(nameof(SelectedProductName));
                    OnPropertyChanged(nameof(SelectedProductSummaryText));
                }
            }
        }

        public LotListItemDto? SelectedLot
        {
            get => _selectedLot;
            set => SetProperty(ref _selectedLot, value);
        }

        public string SelectedProductName => SelectedProduct?.ProductName ?? "-";

        public string SelectedProductSummaryText
        {
            get
            {
                if (SelectedProduct == null)
                {
                    return "품목을 선택하세요.";
                }

                return $"{SelectedProduct.ProductCode} / {SelectedProduct.ProductName}";
            }
        }

        public string LotCountText => $"{LotItems.Count}건 표시";

        public IApiClient ApiClient => _apiClient;

        public IMessageService MessageService => _messageService;

        public Task InitializeAsync()
        {
            ProductItems.Clear();
            LotItems.Clear();

            SelectedProduct = null;
            SelectedLot = null;

            OnPropertyChanged(nameof(SelectedProductName));
            OnPropertyChanged(nameof(SelectedProductSummaryText));
            OnPropertyChanged(nameof(LotCountText));
            ResetProductPagination();

            return Task.CompletedTask;
        }

        private async Task SearchFirstPageAsync()
        {
            _productPage = 1;
            RaiseProductPaginationProperties();
            await LoadProductsAsync();
        }

        private async Task<bool> LoadProductsAsync()
        {
            try
            {
                IsLoading = true;
                LoadingMessage = "품목을 조회 중입니다...";

                var route = BuildProductSearchUrl();

                var result = await _apiClient.GetAsync<ProductListResponse>(route);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "품목 목록을 조회하지 못했습니다.");
                    return false;
                }

                _productPage = Math.Max(1, result.Data.Page);
                _productPageSize = result.Data.Size > 0 ? result.Data.Size : _productPageSize;
                _productTotalCount = Math.Max(0, result.Data.Total);
                RaiseProductPaginationProperties();

                ProductItems.Clear();

                foreach (var item in result.Data.Items)
                {
                    ProductItems.Add(item);
                }

                SelectedProduct = null;
                SelectedLot = null;
                LotItems.Clear();
                OnPropertyChanged(nameof(LotCountText));
                return true;
            }
            finally
            {
                IsLoading = false;
            }
        }

        private Task ResetAsync()
        {
            PartnerKeyword = string.Empty;
            SearchKeyword = string.Empty;
            SelectedUseYn = "사용";

            SelectedProduct = null;
            SelectedLot = null;

            ProductItems.Clear();
            LotItems.Clear();
            ResetProductPagination();

            OnPropertyChanged(nameof(SelectedProductName));
            OnPropertyChanged(nameof(SelectedProductSummaryText));
            OnPropertyChanged(nameof(LotCountText));

            return Task.CompletedTask;
        }

        private async Task LoadPreviousProductPageAsync()
        {
            if (ProductHasPreviousPage)
            {
                await LoadProductPageAsync(_productPage - 1);
            }
        }

        private async Task LoadNextProductPageAsync()
        {
            if (ProductHasNextPage)
            {
                await LoadProductPageAsync(_productPage + 1);
            }
        }

        private async Task LoadProductPageAsync(int targetPage)
        {
            var previousPage = _productPage;
            _productPage = Math.Max(1, targetPage);
            RaiseProductPaginationProperties();

            if (!await LoadProductsAsync())
            {
                _productPage = previousPage;
                RaiseProductPaginationProperties();
            }
        }

        private void ResetProductPagination()
        {
            _productPage = 1;
            _productPageSize = 100;
            _productTotalCount = 0;
            RaiseProductPaginationProperties();
        }

        private void RaiseProductPaginationProperties()
        {
            OnPropertyChanged(nameof(ProductTotalPages));
            OnPropertyChanged(nameof(ProductHasPreviousPage));
            OnPropertyChanged(nameof(ProductHasNextPage));
            OnPropertyChanged(nameof(ProductPageDisplayText));
            RaiseProductPageCommandStates();
        }

        private void RaiseProductPageCommandStates()
        {
            (ProductPreviousPageCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            (ProductNextPageCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        }

        private async Task LoadHistoryAsync()
        {
            if (SelectedProduct == null)
            {
                _messageService.ShowWarning("품목을 먼저 선택하세요.");
                return;
            }

            if (SelectedProduct.ProductId <= 0)
            {
                _messageService.ShowWarning("품목 정보가 없습니다.");
                return;
            }

            try
            {
                IsLoading = true;
                LoadingMessage = "LOT 이력을 조회 중입니다...";

                var route =
                    $"{ApiRoutes.Lots}?product_id={SelectedProduct.ProductId}&page=1&size=10&sort=latest";

                var result = await _apiClient.GetAsync<LotListResponseDto>(route);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "LOT 이력을 조회하지 못했습니다.");
                    return;
                }

                LotItems.Clear();

                foreach (var item in result.Data.Items)
                {
                    LotItems.Add(item);
                }

                SelectedLot = null;
                OnPropertyChanged(nameof(LotCountText));
                OnPropertyChanged(nameof(SelectedProductName));
                OnPropertyChanged(nameof(SelectedProductSummaryText));
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void OpenLotDetail()
        {
            if (SelectedLot == null)
            {
                _messageService.ShowWarning("LOT를 먼저 선택하세요.");
                return;
            }

            if (SelectedLot.LotId <= 0)
            {
                _messageService.ShowWarning("LOT 정보가 없습니다.");
                return;
            }

            RequestOpenLotDetail?.Invoke(SelectedLot.LotId);
        }

        public async Task OpenDrawingAsync(ProductDto? product)
        {
            if (product == null)
            {
                _messageService.ShowWarning("품목을 먼저 선택하세요.");
                return;
            }

            if (product.DrawingId <= 0)
            {
                _messageService.ShowWarning("등록된 도면이 없습니다.");
                return;
            }

            try
            {
                IsLoading = true;
                LoadingMessage = "도면 파일을 여는 중입니다...";

                await Task.Yield();

                await _drawingViewer.OpenCurrentDrawingAsync(product.DrawingId);
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }


        private string BuildProductSearchUrl()
        {
            var route = $"{ApiRoutes.Products}?page={_productPage}&size={_productPageSize}";

            var partnerKeyword = PartnerKeyword?.Trim();
            var keyword = SearchKeyword?.Trim();

            if (!string.IsNullOrWhiteSpace(partnerKeyword))
            {
                route += $"&partner_q={Uri.EscapeDataString(partnerKeyword)}";
            }

            if (!string.IsNullOrWhiteSpace(keyword))
            {
                route += $"&q={Uri.EscapeDataString(keyword)}";
            }

            if (SelectedUseYn == "사용")
            {
                route += "&is_active=true";
            }
            else if (SelectedUseYn == "미사용")
            {
                route += "&is_active=false";
            }

            return route;
        }
    }
}
