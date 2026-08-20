using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.Processes.Dtos;
using Mes.Wpf.Modules.RoutingTemplates.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.RoutingTemplates.ViewModels
{
    public class RoutingTemplateStepPageViewModel : CrudPageViewModelBase<RoutingTemplateDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private RoutingTemplateDto? _selectedTemplate;
        private RoutingTemplateStepDto? _selectedStep;
        private ProcessDto? _selectedProcess;

        public RoutingTemplateStepPageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<RoutingTemplateDto>();
            StepItems = new ObservableCollection<RoutingTemplateStepDto>();
            ProcessItems = new ObservableCollection<ProcessDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };

            EditModel = new RoutingTemplateStepEditModel();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);
        }

        public ObservableCollection<RoutingTemplateDto> Items { get; }

        public ObservableCollection<RoutingTemplateStepDto> StepItems { get; }

        public ObservableCollection<ProcessDto> ProcessItems { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public RoutingTemplateStepEditModel EditModel { get; }

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

        public RoutingTemplateDto? SelectedTemplate
        {
            get => _selectedTemplate;
            set
            {
                if (SetProperty(ref _selectedTemplate, value))
                {
                    _ = OnSelectedTemplateChangedAsync(value);
                }
            }
        }

        public RoutingTemplateStepDto? SelectedStep
        {
            get => _selectedStep;
            set
            {
                if (SetProperty(ref _selectedStep, value))
                {
                    LoadStepToEditModel(value);
                }
            }
        }

        public ProcessDto? SelectedProcess
        {
            get => _selectedProcess;
            set
            {
                if (SetProperty(ref _selectedProcess, value))
                {
                    EditModel.ProcessId = value?.ProcessId;
                    EditModel.ProcessCode = value?.ProcessCode ?? string.Empty;
                    EditModel.ProcessName = value?.ProcessName ?? string.Empty;
                }
            }
        }

        public async Task InitializeAsync()
        {
            await LoadProcessItemsAsync();
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildTemplateListUrl();
            var result = await _apiClient.GetAsync<PagedResult<RoutingTemplateDto>>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "라우팅 템플릿 조회 중 오류가 발생했습니다.");
                return false;
            }

            Items.Clear();

            foreach (var item in result.Data?.Items ?? Enumerable.Empty<RoutingTemplateDto>())
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
            SelectedTemplate = null;
            SelectedStep = null;
            SelectedProcess = null;

            StepItems.Clear();
            EditModel.Clear();
        }

        protected override void New()
        {
            if (SelectedTemplate == null)
            {
                _messageService.ShowWarning("라우팅 템플릿을 먼저 선택하세요.");
                return;
            }

            SelectedStep = null;
            SelectedProcess = null;

            EditModel.Clear();
            EditModel.RoutingTemplateId = SelectedTemplate.RoutingTemplateId;
            EditModel.TemplateCode = SelectedTemplate.TemplateCode;
            EditModel.TemplateName = SelectedTemplate.TemplateName;
            EditModel.Sequence = GetNextSequence();
            EditModel.IsActive = true;
        }

        protected override void OnSelectedItemChanged(RoutingTemplateDto? item)
        {
            // 이 화면은 SelectedTemplate를 주 선택값으로 사용
        }

        private async Task OnSelectedTemplateChangedAsync(RoutingTemplateDto? template)
        {
            SelectedItem = template;
            SelectedStep = null;
            SelectedProcess = null;

            StepItems.Clear();
            EditModel.Clear();

            if (template == null)
            {
                return;
            }

            EditModel.RoutingTemplateId = template.RoutingTemplateId;
            EditModel.TemplateCode = template.TemplateCode;
            EditModel.TemplateName = template.TemplateName;
            EditModel.Sequence = GetNextSequence();
            EditModel.IsActive = true;

            await LoadStepItemsAsync(template.RoutingTemplateId);

            EditModel.RoutingTemplateId = template.RoutingTemplateId;
            EditModel.TemplateCode = template.TemplateCode;
            EditModel.TemplateName = template.TemplateName;
            EditModel.Sequence = GetNextSequence();
            EditModel.IsActive = true;
        }

        private async Task LoadStepItemsAsync(long routingTemplateId)
        {
            var route = $"{ApiRoutes.RoutingTemplates}/{routingTemplateId}/steps?page=1&size=100&is_active=true";
            var result = await _apiClient.GetAsync<PagedResult<RoutingTemplateStepDto>>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "라우팅 Step 조회 중 오류가 발생했습니다.");
                return;
            }

            StepItems.Clear();

            foreach (var item in (result.Data?.Items ?? Enumerable.Empty<RoutingTemplateStepDto>())
                                 .OrderBy(x => x.StepSeq))
            {
                var process = ProcessItems.FirstOrDefault(x => x.ProcessId == item.ProcessId);
                if (process != null)
                {
                    item.ProcessCode = process.ProcessCode;
                    item.ProcessName = process.ProcessName;
                }

                StepItems.Add(item);
            }
        }

        private async Task LoadProcessItemsAsync()
        {
            var route = $"{ApiRoutes.Processes}?page=1&size=100&is_active=true";
            var result = await _apiClient.GetAsync<PagedResult<ProcessDto>>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "공정 목록 조회 중 오류가 발생했습니다.");
                return;
            }

            ProcessItems.Clear();

            foreach (var item in result.Data?.Items ?? Enumerable.Empty<ProcessDto>())
            {
                ProcessItems.Add(item);
            }
        }

        private void LoadStepToEditModel(RoutingTemplateStepDto? item)
        {
            if (SelectedTemplate == null)
            {
                EditModel.Clear();
                SelectedProcess = null;
                return;
            }

            if (item == null)
            {
                EditModel.Clear();
                EditModel.RoutingTemplateId = SelectedTemplate.RoutingTemplateId;
                EditModel.TemplateCode = SelectedTemplate.TemplateCode;
                EditModel.TemplateName = SelectedTemplate.TemplateName;
                EditModel.Sequence = GetNextSequence();
                EditModel.IsActive = true;
                SelectedProcess = null;
                return;
            }

            EditModel.LoadFromDto(item, SelectedTemplate);

            SelectedProcess = ProcessItems.FirstOrDefault(x => x.ProcessId == item.ProcessId)
                              ?? ProcessItems.FirstOrDefault(x => x.ProcessCode == item.ProcessCode);
        }

        private async Task SaveAsync()
        {
            NormalizeEditModel();

            if (!ValidateForSave())
            {
                return;
            }

            IsLoading = true;
            try
            {
                if (EditModel.RoutingStepId.HasValue)
                {
                    await UpdateAsync(EditModel.RoutingStepId.Value);
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

        private async Task CreateAsync()
        {
            var request = new RoutingTemplateStepCreateRequest
            {
                StepSeq = EditModel.Sequence,
                ProcessId = EditModel.ProcessId!.Value,
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PostAsync<RoutingTemplateStepCreateRequest, RoutingTemplateStepDto>(
                $"{ApiRoutes.RoutingTemplates}/{EditModel.RoutingTemplateId!.Value}/steps",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "라우팅 Step 저장 중 오류가 발생했습니다.");
                return;
            }

            await ReloadAfterSaveAsync();
            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long routingStepId)
        {
            var request = new RoutingTemplateStepUpdateRequest
            {
                StepSeq = EditModel.Sequence,
                ProcessId = EditModel.ProcessId!.Value,
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PatchAsync<RoutingTemplateStepUpdateRequest, RoutingTemplateStepDto>(
                $"{ApiRoutes.RoutingTemplates}/{SelectedTemplate!.RoutingTemplateId}/steps/{routingStepId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "라우팅 Step 수정 중 오류가 발생했습니다.");
                return;
            }

            await ReloadAfterSaveAsync();
            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task DeleteAsync()
        {
            if (SelectedTemplate == null || SelectedStep == null || !EditModel.RoutingStepId.HasValue)
            {
                _messageService.ShowWarning("삭제할 Step을 먼저 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                 $"[STEP {SelectedStep.StepSeq}] 항목을 완전히 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.",
                 "삭제 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;
            try
            {
                var result = await _apiClient.DeleteAsync(
                    $"{ApiRoutes.RoutingTemplates}/{SelectedTemplate.RoutingTemplateId}/steps/{EditModel.RoutingStepId.Value}");

                if (!result.Success || !result.Data)
                {
                    _messageService.ShowError(result.Message ?? "라우팅 Step 삭제 중 오류가 발생했습니다.");
                    return;
                }

                await ReloadAfterSaveAsync();
                _messageService.ShowInfo("삭제되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task ReloadAfterSaveAsync()
        {
            if (SelectedTemplate == null)
            {
                return;
            }

            var template = SelectedTemplate;

            await LoadStepItemsAsync(template.RoutingTemplateId);

            SelectedStep = null;
            SelectedProcess = null;

            EditModel.Clear();
            EditModel.RoutingTemplateId = template.RoutingTemplateId;
            EditModel.TemplateCode = template.TemplateCode;
            EditModel.TemplateName = template.TemplateName;
            EditModel.Sequence = GetNextSequence();
            EditModel.IsActive = true;
        }

        private bool ValidateForSave()
        {
            if (SelectedTemplate == null || !EditModel.RoutingTemplateId.HasValue)
            {
                _messageService.ShowWarning("라우팅 템플릿을 먼저 선택하세요.");
                return false;
            }

            if (!EditModel.ProcessId.HasValue)
            {
                _messageService.ShowWarning("공정을 선택하세요.");
                return false;
            }

            if (EditModel.Sequence <= 0)
            {
                _messageService.ShowWarning("순서는 1 이상이어야 합니다.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.TemplateCode = EditModel.TemplateCode?.Trim() ?? string.Empty;
            EditModel.TemplateName = EditModel.TemplateName?.Trim() ?? string.Empty;
            EditModel.ProcessCode = EditModel.ProcessCode?.Trim().ToUpperInvariant() ?? string.Empty;
            EditModel.ProcessName = EditModel.ProcessName?.Trim() ?? string.Empty;
        }

        private int GetNextSequence()
        {
            return StepItems.Count == 0 ? 1 : StepItems.Max(x => x.StepSeq) + 1;
        }

        private string BuildTemplateListUrl()
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

        private string BuildStepListUrl(long routingTemplateId)
        {
            return $"{ApiRoutes.RoutingTemplates}/{routingTemplateId}/steps?page=1&size=100&is_active=true";
        }
    }
}
