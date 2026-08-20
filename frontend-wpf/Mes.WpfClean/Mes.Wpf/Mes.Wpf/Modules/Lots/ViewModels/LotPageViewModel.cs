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
using Mes.Wpf.Modules.LotDetails.ViewModels;
using Mes.Wpf.Modules.LotDetails.Views;
using Mes.Wpf.Modules.Lots.Dtos;

namespace Mes.Wpf.Modules.Lots.ViewModels
{
    public class LotPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private bool _isLoading;
        private LotListItemDto? _selectedItem;
        private int _currentPage = 1;
        private int _pageSize = 20;
        private int _totalCount;

        public LotPageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            SearchModel = new LotProcessSearchModel();
            Items = new ObservableCollection<LotListItemDto>();

            StatusOptions = new ObservableCollection<string>
            {
                "전체",
                "생성",
                "진행중",
                "검수대기",
                "검수완료"
            };

            SearchCommand = new AsyncRelayCommand(SearchAsync, () => !IsLoading);
            ResetCommand = new AsyncRelayCommand(ResetAsync, () => !IsLoading);
            PrevPageCommand = new AsyncRelayCommand(GoPreviousPageAsync, () => !IsLoading && HasPreviousPage);
            NextPageCommand = new AsyncRelayCommand(GoNextPageAsync, () => !IsLoading && HasNextPage);
            OpenLotDetailCommand = new AsyncRelayCommand(OpenLotDetailAsync, () => !IsLoading && HasSelectedLot);
            OpenLotCertificateCommand = new AsyncRelayCommand(OpenLotCertificateAsync, () => !IsLoading && HasSelectedLot);
        }

        public LotProcessSearchModel SearchModel { get; }

        public ObservableCollection<LotListItemDto> Items { get; }

        public ObservableCollection<string> StatusOptions { get; }

        public ICommand SearchCommand { get; }

        public ICommand ResetCommand { get; }

        public ICommand PrevPageCommand { get; }

        public ICommand NextPageCommand { get; }

        public ICommand OpenLotDetailCommand { get; }

        public ICommand OpenLotCertificateCommand { get; }

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

        public LotListItemDto? SelectedItem
        {
            get => _selectedItem;
            set
            {
                if (SetProperty(ref _selectedItem, value))
                {
                    OnPropertyChanged(nameof(HasSelectedLot));
                    RaiseCommandCanExecuteChanged();
                }
            }
        }

        public bool HasSelectedLot => SelectedItem != null;

        public int CurrentPage
        {
            get => _currentPage;
            set
            {
                if (SetProperty(ref _currentPage, value))
                {
                    OnPropertyChanged(nameof(TotalPages));
                    OnPropertyChanged(nameof(HasPreviousPage));
                    OnPropertyChanged(nameof(HasNextPage));
                    OnPropertyChanged(nameof(PageDisplayText));
                    RaiseCommandCanExecuteChanged();
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
                    OnPropertyChanged(nameof(TotalPages));
                    OnPropertyChanged(nameof(HasPreviousPage));
                    OnPropertyChanged(nameof(HasNextPage));
                    OnPropertyChanged(nameof(PageDisplayText));
                    RaiseCommandCanExecuteChanged();
                }
            }
        }

        public int TotalCount
        {
            get => _totalCount;
            set
            {
                if (SetProperty(ref _totalCount, value))
                {
                    OnPropertyChanged(nameof(TotalPages));
                    OnPropertyChanged(nameof(HasPreviousPage));
                    OnPropertyChanged(nameof(HasNextPage));
                    OnPropertyChanged(nameof(PageDisplayText));
                    RaiseCommandCanExecuteChanged();
                }
            }
        }

        public int TotalPages
        {
            get
            {
                if (PageSize <= 0)
                {
                    return 1;
                }

                return Math.Max(1, (int)Math.Ceiling((double)TotalCount / PageSize));
            }
        }

        public bool HasPreviousPage => CurrentPage > 1;

        public bool HasNextPage => CurrentPage < TotalPages;

        public string PageDisplayText => $"{CurrentPage} / {TotalPages} (총 {TotalCount:N0}건)";

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        public async Task SearchAsync()
        {
            CurrentPage = 1;
            await SearchInternalAsync(keepSelection: false);
        }

        public async Task ResetAsync()
        {
            SearchModel.Clear();
            CurrentPage = 1;
            await SearchInternalAsync(keepSelection: false);
        }

        public async Task GoPreviousPageAsync()
        {
            if (!HasPreviousPage)
            {
                return;
            }

            CurrentPage--;
            await SearchInternalAsync(keepSelection: false);
        }

        public async Task GoNextPageAsync()
        {
            if (!HasNextPage)
            {
                return;
            }

            CurrentPage++;
            await SearchInternalAsync(keepSelection: false);
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

            var window = new LotDetailWindow(windowVm)
            {
                Owner = Application.Current?.MainWindow
            };

            window.ShowDialog();
        }

        private async Task OpenLotCertificateAsync()
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

            if (!CanOpenCertificate(SelectedItem))
            {
                _messageService.ShowWarning("아직 완료되지 않은 LOT입니다.\n성적서가 작성되지 않았습니다.");
                return;
            }

            var windowVm = new LotCertificateWindowViewModel(_apiClient, _messageService);

            await windowVm.InitializeAsync(SelectedItem.LotId);

            var window = new LotCertificateWindow(windowVm)
            {
                Owner = Application.Current?.MainWindow
            };

            window.ShowDialog();
        }
        private static bool CanOpenCertificate(LotListItemDto item)
        {
            return string.Equals(item.Status?.Trim(), "DONE", StringComparison.OrdinalIgnoreCase)
                   || string.Equals(item.ListStatus?.Trim(), "INSPECTION_DONE", StringComparison.OrdinalIgnoreCase)
                   || string.Equals(item.ListStatusDisplay?.Trim(), "검수완료", StringComparison.OrdinalIgnoreCase);
        }

        private async Task SearchInternalAsync(bool keepSelection)
        {
            var currentLotId = keepSelection ? SelectedItem?.LotId : null;

            try
            {
                IsLoading = true;

                NormalizeSearchInputs();

                var result = await _apiClient.GetAsync<LotListResponseDto>(BuildSearchUrl());

                if (!result.Success || result.Data == null)
                {
                    Items.Clear();
                    SelectedItem = null;
                    TotalCount = 0;

                    _messageService.ShowError(result.Message ?? "LOT 목록 조회에 실패했습니다.");
                    return;
                }

                Items.Clear();

                foreach (var item in result.Data.Items)
                {
                    Items.Add(item);
                }

                CurrentPage = result.Data.Meta?.Page ?? CurrentPage;
                PageSize = result.Data.Meta?.Size ?? PageSize;
                TotalCount = result.Data.Meta?.Total ?? Items.Count;

                if (Items.Count == 0)
                {
                    SelectedItem = null;
                    return;
                }

                if (currentLotId.HasValue)
                {
                    SelectedItem = Items.FirstOrDefault(x => x.LotId == currentLotId.Value);
                }
                else
                {
                    SelectedItem = null;
                }
            }
            finally
            {
                IsLoading = false;
            }
        }

        private string BuildSearchUrl()
        {
            var queryParts = new List<string>
            {
                $"page={CurrentPage}",
                $"size={PageSize}"
            };

            if (SearchModel.CreatedDateFrom.HasValue)
            {
                queryParts.Add($"created_date_from={SearchModel.CreatedDateFrom.Value:yyyy-MM-dd}");
            }

            if (SearchModel.CreatedDateTo.HasValue)
            {
                queryParts.Add($"created_date_to={SearchModel.CreatedDateTo.Value:yyyy-MM-dd}");
            }

            var keyword = SearchModel.Keyword?.Trim();

            if (!string.IsNullOrWhiteSpace(keyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(keyword)}");
            }

            var status = ConvertStatusToApiValue(SearchModel.SelectedStatus);

            if (!string.IsNullOrWhiteSpace(status))
            {
                queryParts.Add($"status={Uri.EscapeDataString(status)}");
            }

            return $"{ApiRoutes.Lots}?{string.Join("&", queryParts)}";
        }

        private static string ConvertStatusToApiValue(string? statusText)
        {
            var value = statusText?.Trim();

            return value switch
            {
                null or "" or "전체" => string.Empty,
                "생성" => "CREATED",
                "진행중" => "IN_PROGRESS",
                "검수대기" => "INSPECTION_WAITING",
                "검수완료" => "INSPECTION_DONE",
                _ => value
            };
        }

        private void NormalizeSearchInputs()
        {
            SearchModel.Keyword = SearchModel.Keyword?.Trim() ?? string.Empty;
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

            if (PrevPageCommand is AsyncRelayCommand prevPageCommand)
            {
                prevPageCommand.RaiseCanExecuteChanged();
            }

            if (NextPageCommand is AsyncRelayCommand nextPageCommand)
            {
                nextPageCommand.RaiseCanExecuteChanged();
            }

            if (OpenLotDetailCommand is AsyncRelayCommand openLotDetailCommand)
            {
                openLotDetailCommand.RaiseCanExecuteChanged();
            }

            if (OpenLotCertificateCommand is AsyncRelayCommand openLotCertificateCommand)
            {
                openLotCertificateCommand.RaiseCanExecuteChanged();
            }
        }
    }

}
