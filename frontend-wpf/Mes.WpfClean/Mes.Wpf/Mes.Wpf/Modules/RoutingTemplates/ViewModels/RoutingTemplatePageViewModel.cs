using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.RoutingTemplates.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.RoutingTemplates.ViewModels
{
    public class RoutingTemplatePageViewModel : CrudPageViewModelBase<RoutingTemplateDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private bool _isCodeEditable = true;

        public RoutingTemplatePageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<RoutingTemplateDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };
            EditModel = new RoutingTemplateEditModel();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);
        }

        public ObservableCollection<RoutingTemplateDto> Items { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public RoutingTemplateEditModel EditModel { get; }

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

        public bool IsCodeEditable
        {
            get => _isCodeEditable;
            set => SetProperty(ref _isCodeEditable, value);
        }

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();

            var result = await _apiClient.GetAsync<RoutingTemplateListDto>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "라우팅 템플릿 조회 중 오류");
                return false;
            }

            Items.Clear();

            foreach (var item in result.Data?.Items ?? [])
            {
                Items.Add(item);
            }

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
                if (EditModel.RoutingTemplateId.HasValue)
                {
                    await UpdateAsync(EditModel.RoutingTemplateId.Value);
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
            if (SelectedItem == null || !EditModel.RoutingTemplateId.HasValue)
            {
                _messageService.ShowWarning("삭제할 항목을 먼저 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.TemplateCode}] {SelectedItem.TemplateName} 항목을 삭제하시겠습니까?",
                "삭제 확인");

            if (!confirmed) return;

            IsLoading = true;
            try
            {
                var result = await _apiClient.DeleteAsync(
                    $"{ApiRoutes.RoutingTemplates}/{SelectedItem.RoutingTemplateId}");

                if (!result.Success || !result.Data)
                {
                    _messageService.ShowError(result.Message ?? "라우팅 템플릿 삭제 중 오류가 발생했습니다.");
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
            var request = new RoutingTemplateCreateRequest
            {
                TemplateCode = EditModel.TemplateCode,
                TemplateName = EditModel.TemplateName,
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PostAsync<RoutingTemplateCreateRequest, RoutingTemplateDto>(
                ApiRoutes.RoutingTemplates,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "라우팅 템플릿 저장 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long routingTemplateId)
        {
            var request = new RoutingTemplateUpdateRequest
            {
                TemplateName = EditModel.TemplateName,
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PatchAsync<RoutingTemplateUpdateRequest, RoutingTemplateDto>(
                $"{ApiRoutes.RoutingTemplates}/{routingTemplateId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "라우팅 템플릿 수정 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private void LoadToEditModel(RoutingTemplateDto? item)
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
            if (!EditModel.RoutingTemplateId.HasValue &&
                string.IsNullOrWhiteSpace(EditModel.TemplateCode))
            {
                _messageService.ShowWarning("템플릿 코드는 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.TemplateName))
            {
                _messageService.ShowWarning("템플릿명은 필수입니다.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.TemplateCode = EditModel.TemplateCode?.Trim() ?? string.Empty;
            EditModel.TemplateName = EditModel.TemplateName?.Trim() ?? string.Empty;
        }

        protected override void OnSelectedItemChanged(RoutingTemplateDto? item)
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

            return $"{ApiRoutes.RoutingTemplates}?{string.Join("&", queryParts)}";
        }
    }
}
