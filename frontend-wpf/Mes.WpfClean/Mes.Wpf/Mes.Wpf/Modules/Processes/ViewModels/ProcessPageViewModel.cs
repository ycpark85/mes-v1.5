using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Processes.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Processes.ViewModels
{
    public class ProcessPageViewModel : CrudPageViewModelBase<ProcessDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private bool _isCodeEditable = true;

        public ProcessPageViewModel(IApiClient apiClient, IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<ProcessDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };
            ProcessTypeOptions = new ObservableCollection<string> { "INTERNAL", "OUTSOURCE" };

            EditModel = new ProcessEditModel();

            //SearchCommand = new AsyncRelayCommand(SearchAsync);
            //ResetCommand = new RelayCommand(Reset);
            //NewCommand = new RelayCommand(New);
            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);
        }

        public ObservableCollection<ProcessDto> Items { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public ObservableCollection<string> ProcessTypeOptions { get; }

        public ProcessEditModel EditModel { get; }

        //public AsyncRelayCommand SearchCommand { get; }

        //public RelayCommand ResetCommand { get; }

        //public RelayCommand NewCommand { get; }

        public AsyncRelayCommand SaveCommand { get; }

        public AsyncRelayCommand DeleteCommand { get; }

        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public string SelectedUseYn
        {
            get => _selectedUseYn;
            set => SetProperty(ref _selectedUseYn, value);
        }

        //public bool IsLoading
        //{
        //    get => _isLoading;
        //    set => SetProperty(ref _isLoading, value);
        //}

        public bool IsCodeEditable
        {
            get => _isCodeEditable;
            set => SetProperty(ref _isCodeEditable, value);
        }

        //public ProcessDto? SelectedItem
        //{
        //    get => _selectedItem;
        //    set
        //    {
        //        if (SetProperty(ref _selectedItem, value))
        //        {
        //            LoadToEditModel(value);
        //        }
        //    }
        //}

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();
            var result = await _apiClient.GetAsync<ProcessListDto>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "공정 조회 중 오류");
                return false;
            }

            Items.Clear();
            foreach (var item in result.Data?.Items ?? [])
                Items.Add(item);

            ApplyListPage(
                result.Data?.Total ?? 0,
                result.Data?.Page ?? ListPage,
                result.Data?.Size ?? ListPageSize);
            return true;
        }
        protected override void Reset()
        {
            SearchKeyword = string.Empty;
            SelectedUseYn = "사용";
            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;
        }

        protected override void New()
        {
            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;
        }

        private async Task SaveAsync()
        {
            NormalizeEditModel();

            if (!ValidateForSave())
                return;

            IsLoading = true;

            try
            {
                if (EditModel.ProcessId.HasValue)
                {
                    await UpdateAsync(EditModel.ProcessId.Value);
                }
                else
                {
                    await CreateAsync();
                }
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task DeleteAsync()
        {
            if (SelectedItem == null || !EditModel.ProcessId.HasValue)
            {
                _messageService.ShowWarning("삭제할 항목을 먼저 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.ProcessCode}] {SelectedItem.ProcessName} 항목을 삭제하시겠습니까?",
                "삭제 확인");

            if (!confirmed) return;

            IsLoading = true;
            try
            {
                var result = await _apiClient.DeleteAsync($"{ApiRoutes.Processes}/{SelectedItem.ProcessId}");
                if (!result.Success || !result.Data)
                {
                    _messageService.ShowError(result.Message ?? "공정 삭제 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();
                SelectedItem = null;
                EditModel.Clear();
                IsCodeEditable = true;
                _messageService.ShowInfo("삭제되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task CreateAsync()
        {
            var request = new ProcessCreateRequest
            {
                ProcessCode = EditModel.ProcessCode,
                ProcessName = EditModel.ProcessName,
                ProcessType = EditModel.ProcessType,
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PostAsync<ProcessCreateRequest, ProcessDto>(
                ApiRoutes.Processes,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "공정 저장 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long processId)
        {
            var request = new ProcessUpdateRequest
            {
                ProcessName = EditModel.ProcessName,
                ProcessType = EditModel.ProcessType,
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PatchAsync<ProcessUpdateRequest, ProcessDto>(
                $"{ApiRoutes.Processes}/{processId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "공정 수정 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private void LoadToEditModel(ProcessDto? item)
        {
            if (item == null)
            {
                EditModel.Clear();
                IsCodeEditable = true;
                return;
            }

            EditModel.LoadFromDto(item);
            IsCodeEditable = false;
        }

        private bool ValidateForSave()
        {
            if (!EditModel.ProcessId.HasValue && string.IsNullOrWhiteSpace(EditModel.ProcessCode))
            {
                _messageService.ShowWarning("공정코드는 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.ProcessName))
            {
                _messageService.ShowWarning("공정명은 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.ProcessType))
            {
                _messageService.ShowWarning("공정구분은 필수입니다.");
                return false;
            }

            if (EditModel.ProcessType != "INTERNAL" && EditModel.ProcessType != "OUTSOURCE")
            {
                _messageService.ShowWarning("공정구분은 INTERNAL 또는 OUTSOURCE 여야 합니다.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.ProcessCode = EditModel.ProcessCode?.Trim() ?? string.Empty;
            EditModel.ProcessName = EditModel.ProcessName?.Trim() ?? string.Empty;
            EditModel.ProcessType = EditModel.ProcessType?.Trim().ToUpperInvariant() ?? "INTERNAL";
        }

        protected override void OnSelectedItemChanged(ProcessDto? item)
        {
            LoadToEditModel(item);
        }

        private string BuildListUrl()
        {
            var queryParts = new List<string>
            {
                $"page={ListPage}",
                $"size={ListPageSize}"
            };

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(SearchKeyword.Trim())}");
            }

            if (SelectedUseYn == "사용")
            {
                queryParts.Add("is_active=true");
            }
            else if (SelectedUseYn == "미사용")
            {
                queryParts.Add("is_active=false");
            }

            return $"{ApiRoutes.Processes}?{string.Join("&", queryParts)}";
        }
    }
}
