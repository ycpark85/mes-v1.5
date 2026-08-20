using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.ProductionDaily.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows.Input;

namespace Mes.Wpf.Modules.ProductionDaily.ViewModels
{
    public class ProductionDailyPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private bool _isLoading;
        private string _partnerKeyword = string.Empty;
        private string _productKeyword = string.Empty;
        private string _selectedStatus = "IN_PROGRESS";
        private int _totalCount;
        private int _currentPage = 1;
        private int _pageSize = 100;

        public ProductionDailyPageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<ProductionDailyRowDto>();
            StatusOptions = new ObservableCollection<ProductionDailyStatusOption>
            {
                new("IN_PROGRESS", "진행중"),
                new("COMPLETED", "완료")
            };

            SearchCommand = new AsyncRelayCommand(SearchFirstPageAsync, () => !IsLoading);
            ResetCommand = new AsyncRelayCommand(ResetAsync, () => !IsLoading);
            PreviousPageCommand = new AsyncRelayCommand(
                GoPreviousPageAsync,
                () => !IsLoading && HasPreviousPage);
            NextPageCommand = new AsyncRelayCommand(
                GoNextPageAsync,
                () => !IsLoading && HasNextPage);
        }

        public ObservableCollection<ProductionDailyRowDto> Items { get; }
        public ObservableCollection<ProductionDailyStatusOption> StatusOptions { get; }
        public ICommand SearchCommand { get; }
        public ICommand ResetCommand { get; }
        public ICommand PreviousPageCommand { get; }
        public ICommand NextPageCommand { get; }

        public int TotalPages => Math.Max(1, (int)Math.Ceiling((double)TotalCount / _pageSize));
        public bool HasPreviousPage => _currentPage > 1;
        public bool HasNextPage => _currentPage < TotalPages;
        public string PageDisplayText => $"{_currentPage:N0} / {TotalPages:N0} 페이지 (총 {TotalCount:N0}건)";

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

        public string PartnerKeyword
        {
            get => _partnerKeyword;
            set => SetProperty(ref _partnerKeyword, value);
        }

        public string ProductKeyword
        {
            get => _productKeyword;
            set => SetProperty(ref _productKeyword, value);
        }

        public string SelectedStatus
        {
            get => _selectedStatus;
            set => SetProperty(ref _selectedStatus, value);
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

        public async Task InitializeAsync()
        {
            await SearchFirstPageAsync();
        }

        private async Task SearchFirstPageAsync()
        {
            _currentPage = 1;
            RaisePagePropertiesChanged();
            await SearchAsync();
        }

        private async Task<bool> SearchAsync()
        {
            IsLoading = true;

            try
            {
                var result = await _apiClient.GetAsync<ProductionDailyListDto>(BuildListUrl());

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "생산진행현황 조회 중 오류가 발생했습니다.");
                    return false;
                }

                Items.Clear();

                foreach (var item in result.Data.Items)
                {
                    Items.Add(item);
                }

                TotalCount = result.Data.Total;
                _currentPage = Math.Max(1, result.Data.Page);
                _pageSize = result.Data.Size > 0 ? result.Data.Size : _pageSize;
                RaisePagePropertiesChanged();
                return true;
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task ResetAsync()
        {
            PartnerKeyword = string.Empty;
            ProductKeyword = string.Empty;
            SelectedStatus = "IN_PROGRESS";
            _currentPage = 1;

            await SearchAsync();
        }

        private async Task GoPreviousPageAsync()
        {
            if (HasPreviousPage)
            {
                var previousPage = _currentPage;
                _currentPage--;
                RaisePagePropertiesChanged();
                if (!await SearchAsync())
                {
                    _currentPage = previousPage;
                    RaisePagePropertiesChanged();
                }
            }
        }

        private async Task GoNextPageAsync()
        {
            if (HasNextPage)
            {
                var previousPage = _currentPage;
                _currentPage++;
                RaisePagePropertiesChanged();
                if (!await SearchAsync())
                {
                    _currentPage = previousPage;
                    RaisePagePropertiesChanged();
                }
            }
        }

        private string BuildListUrl()
        {
            var queryParts = new List<string>
            {
                $"page={_currentPage}",
                $"size={_pageSize}",
                $"status={Uri.EscapeDataString(SelectedStatus)}"
            };

            if (!string.IsNullOrWhiteSpace(PartnerKeyword))
            {
                queryParts.Add($"partner_q={Uri.EscapeDataString(PartnerKeyword.Trim())}");
            }

            if (!string.IsNullOrWhiteSpace(ProductKeyword))
            {
                queryParts.Add($"product_q={Uri.EscapeDataString(ProductKeyword.Trim())}");
            }

            return $"{ApiRoutes.ProductionDaily}?{string.Join("&", queryParts)}";
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
