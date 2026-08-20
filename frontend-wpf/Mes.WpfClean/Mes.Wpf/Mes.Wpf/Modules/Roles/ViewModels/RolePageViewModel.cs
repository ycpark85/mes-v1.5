using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Roles.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Roles.ViewModels
{
    public class RolePageViewModel : CrudPageViewModelBase<RoleDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private bool _isCodeEditable = true;
        private bool _isPermissionEditable;

        public RolePageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<RoleDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };
            PermissionItems = new ObservableCollection<PermissionCheckItem>();

            EditModel = new RoleEditModel();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);
            SavePermissionsCommand = new AsyncRelayCommand(SavePermissionsAsync);
        }

        public ObservableCollection<RoleDto> Items { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public ObservableCollection<PermissionCheckItem> PermissionItems { get; }

        public RoleEditModel EditModel { get; }

        public AsyncRelayCommand SaveCommand { get; }

        public AsyncRelayCommand DeleteCommand { get; }

        public AsyncRelayCommand SavePermissionsCommand { get; }

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

        public bool IsPermissionEditable
        {
            get => _isPermissionEditable;
            set => SetProperty(ref _isPermissionEditable, value);
        }

        public async Task InitializeAsync()
        {
            await LoadPermissionItemsAsync();
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var result = await _apiClient.GetAsync<RoleListResponse>(BuildListUrl());

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "역할 조회 중 오류가 발생했습니다.");
                return false;
            }

            Items.Clear();

            foreach (var item in result.Data?.Items ?? new List<RoleDto>())
            {
                Items.Add(item);
            }

            ApplyListPage(
                result.Data?.Total ?? 0,
                result.Data?.Page ?? ListPage,
                result.Data?.Size ?? ListPageSize);
            return true;
        }

        protected override void OnSelectedItemChanged(RoleDto? item)
        {
            LoadToEditModel(item);

            if (item == null)
            {
                ClearPermissionSelection();
                return;
            }

            _ = LoadRolePermissionsAsync(item.RoleId);
        }

        protected override void Reset()
        {
            SearchKeyword = string.Empty;
            SelectedUseYn = "사용";
            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;
            IsPermissionEditable = false;
            ClearPermissionSelection();
        }

        protected override void New()
        {
            SelectedItem = null;
            EditModel.Clear();
            IsCodeEditable = true;
            IsPermissionEditable = false;
            ClearPermissionSelection();
        }

        private async Task LoadPermissionItemsAsync()
        {
            var result = await _apiClient.GetAsync<PermissionListResponse>(
                $"{ApiRoutes.Permissions}?page=1&size=500&is_active=true");

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "권한 목록 조회 중 오류가 발생했습니다.");
                return;
            }

            PermissionItems.Clear();

            foreach (var permission in result.Data?.Items ?? new List<PermissionDto>())
            {
                var item = new PermissionCheckItem();
                item.LoadFromDto(permission);
                PermissionItems.Add(item);
            }
        }

        private async Task LoadRolePermissionsAsync(long roleId)
        {
            ClearPermissionSelection();

            var result = await _apiClient.GetAsync<RolePermissionResponse>(
                $"{ApiRoutes.Roles}/{roleId}/permissions");

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "역할 권한 조회 중 오류가 발생했습니다.");
                return;
            }

            var selectedIds = new HashSet<long>(
                result.Data?.Permissions?.Select(x => x.PermissionId) ?? new List<long>());

            foreach (var item in PermissionItems)
            {
                item.IsSelected = selectedIds.Contains(item.PermissionId);
            }
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
                if (EditModel.RoleId.HasValue)
                {
                    await UpdateAsync(EditModel.RoleId.Value);
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
            var request = new RoleCreateRequest
            {
                RoleCode = EditModel.RoleCode,
                RoleName = EditModel.RoleName,
                Description = EmptyToNull(EditModel.Description),
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PostAsync<RoleCreateRequest, RoleDto>(
                ApiRoutes.Roles,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "역할 저장 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            ClearPermissionSelection();
            IsCodeEditable = true;
            IsPermissionEditable = false;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long roleId)
        {
            var request = new RoleUpdateRequest
            {
                RoleName = EditModel.RoleName,
                Description = EmptyToNull(EditModel.Description),
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PatchAsync<RoleUpdateRequest, RoleDto>(
                $"{ApiRoutes.Roles}/{roleId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "역할 수정 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            ClearPermissionSelection();
            IsCodeEditable = true;
            IsPermissionEditable = false;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task DeleteAsync()
        {
            if (SelectedItem == null || !EditModel.RoleId.HasValue)
            {
                _messageService.ShowWarning("삭제할 역할을 먼저 선택하세요.");
                return;
            }

            if (EditModel.IsSystem)
            {
                _messageService.ShowWarning("시스템 역할은 삭제할 수 없습니다.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.RoleCode}] {SelectedItem.RoleName} 역할을 삭제하시겠습니까?",
                "삭제 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;

            try
            {
                var result = await _apiClient.DeleteAsync(
                    $"{ApiRoutes.Roles}/{SelectedItem.RoleId}");

                if (!result.Success || !result.Data)
                {
                    _messageService.ShowError(result.Message ?? "역할 삭제 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();

                SelectedItem = null;
                EditModel.Clear();
                ClearPermissionSelection();
                IsCodeEditable = true;
                IsPermissionEditable = false;

                _messageService.ShowInfo("삭제되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task SavePermissionsAsync()
        {
            if (SelectedItem == null || !EditModel.RoleId.HasValue)
            {
                _messageService.ShowWarning("권한을 저장할 역할을 먼저 선택하세요.");
                return;
            }

            if (EditModel.IsSystem)
            {
                _messageService.ShowWarning("시스템 역할의 권한은 변경할 수 없습니다.");
                return;
            }

            var selectedPermissionIds = PermissionItems
                .Where(x => x.IsSelected)
                .Select(x => x.PermissionId)
                .Distinct()
                .OrderBy(x => x)
                .ToList();

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.RoleCode}] {SelectedItem.RoleName} 역할의 권한을 저장하시겠습니까?",
                "권한 저장 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;

            try
            {
                var request = new RolePermissionUpdateRequest
                {
                    PermissionIds = selectedPermissionIds
                };

                var result = await _apiClient.PutAsync<RolePermissionUpdateRequest, RolePermissionResponse>(
                    $"{ApiRoutes.Roles}/{SelectedItem.RoleId}/permissions",
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "역할 권한 저장 중 오류가 발생했습니다.");
                    return;
                }

                await LoadRolePermissionsAsync(SelectedItem.RoleId);

                _messageService.ShowInfo("권한이 저장되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void LoadToEditModel(RoleDto? item)
        {
            if (item == null)
            {
                EditModel.Clear();
                IsCodeEditable = true;
                IsPermissionEditable = false;
                return;
            }

            EditModel.LoadFromDto(item);
            IsCodeEditable = false;
            IsPermissionEditable = !item.IsSystem;
        }

        private bool ValidateForSave()
        {
            if (!EditModel.RoleId.HasValue && string.IsNullOrWhiteSpace(EditModel.RoleCode))
            {
                _messageService.ShowWarning("역할코드는 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.RoleName))
            {
                _messageService.ShowWarning("역할명은 필수입니다.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.RoleCode = EditModel.RoleCode?.Trim().ToUpperInvariant() ?? string.Empty;
            EditModel.RoleName = EditModel.RoleName?.Trim() ?? string.Empty;
            EditModel.Description = EditModel.Description?.Trim() ?? string.Empty;
        }

        private void ClearPermissionSelection()
        {
            foreach (var item in PermissionItems)
            {
                item.IsSelected = false;
            }
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

            return $"{ApiRoutes.Roles}?{string.Join("&", queryParts)}";
        }

        private static string? EmptyToNull(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }
    }
}
