using System;
using System.Threading.Tasks;

namespace Mes.Wpf.Core.Common.ViewModels
{
    public abstract class CrudPageViewModelBase<TItem> : ViewModelBase
    {
        private bool _isLoading;
        private TItem? _selectedItem;
        private int _listPage = 1;
        private int _listPageSize = 100;
        private int _listTotalCount;

        protected CrudPageViewModelBase()
        {
            SearchCommand = new AsyncRelayCommand(SearchAsync);
            ResetCommand = new RelayCommand(Reset);
            NewCommand = new RelayCommand(New);
            ListPreviousPageCommand = new AsyncRelayCommand(
                GoToPreviousListPageAsync,
                () => !IsLoading && ListHasPreviousPage);
            ListNextPageCommand = new AsyncRelayCommand(
                GoToNextListPageAsync,
                () => !IsLoading && ListHasNextPage);
        }

        public AsyncRelayCommand SearchCommand { get; }
        public RelayCommand ResetCommand { get; }
        public RelayCommand NewCommand { get; }
        public AsyncRelayCommand ListPreviousPageCommand { get; }
        public AsyncRelayCommand ListNextPageCommand { get; }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    RaiseListPageStateChanged();
                }
            }
        }

        public int ListPage
        {
            get => _listPage;
            private set
            {
                if (SetProperty(ref _listPage, Math.Max(1, value)))
                {
                    RaiseListPageStateChanged();
                }
            }
        }

        public int ListPageSize
        {
            get => _listPageSize;
            private set
            {
                if (SetProperty(ref _listPageSize, Math.Max(1, value)))
                {
                    RaiseListPageStateChanged();
                }
            }
        }

        public int ListTotalCount
        {
            get => _listTotalCount;
            private set
            {
                if (SetProperty(ref _listTotalCount, Math.Max(0, value)))
                {
                    RaiseListPageStateChanged();
                }
            }
        }

        public int ListTotalPages => Math.Max(
            1,
            (int)Math.Ceiling(ListTotalCount / (double)ListPageSize));

        public bool ListHasPreviousPage => ListPage > 1;
        public bool ListHasNextPage => ListPage < ListTotalPages;
        public string ListPageDisplayText =>
            $"{ListPage:N0} / {ListTotalPages:N0} 페이지 (총 {ListTotalCount:N0}건)";

        public TItem? SelectedItem
        {
            get => _selectedItem;
            set
            {
                if (SetProperty(ref _selectedItem, value))
                {
                    OnSelectedItemChanged(value);
                }
            }
        }

        protected async Task SearchAsync()
        {
            ListPage = 1;
            await LoadListPageAsync();
        }

        protected abstract Task<bool> LoadListAsync();

        protected void ApplyListPage(int totalCount, int page, int pageSize)
        {
            ListPageSize = pageSize;
            ListTotalCount = totalCount;
            ListPage = Math.Min(Math.Max(1, page), ListTotalPages);
            RaiseListPageStateChanged();
        }

        protected void ResetListPage()
        {
            ListPage = 1;
            ListTotalCount = 0;
        }

        protected virtual void OnSelectedItemChanged(TItem? item) { }
        protected virtual void Reset() { }
        protected virtual void New() { }

        private async Task GoToPreviousListPageAsync()
        {
            if (!ListHasPreviousPage)
            {
                return;
            }

            var previousPage = ListPage;
            ListPage--;
            if (!await LoadListPageAsync())
            {
                ListPage = previousPage;
            }
        }

        private async Task GoToNextListPageAsync()
        {
            if (!ListHasNextPage)
            {
                return;
            }

            var previousPage = ListPage;
            ListPage++;
            if (!await LoadListPageAsync())
            {
                ListPage = previousPage;
            }
        }

        private async Task<bool> LoadListPageAsync()
        {
            IsLoading = true;
            try
            {
                return await LoadListAsync();
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void RaiseListPageStateChanged()
        {
            OnPropertyChanged(nameof(ListTotalPages));
            OnPropertyChanged(nameof(ListHasPreviousPage));
            OnPropertyChanged(nameof(ListHasNextPage));
            OnPropertyChanged(nameof(ListPageDisplayText));
            ListPreviousPageCommand?.RaiseCanExecuteChanged();
            ListNextPageCommand?.RaiseCanExecuteChanged();
        }
    }
}
