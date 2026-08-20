using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Partners.Dtos;
using Mes.Wpf.Modules.Users.Dtos;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Users.ViewModels
{
    public class UserPageViewModel : CrudPageViewModelBase<UserDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private const string VendorPortalRoleCode = "VENDOR_PORTAL";

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private bool _isLoginIdEditable = true;

        public UserPageViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<UserDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };
            RoleOptions = new ObservableCollection<UserRoleCheckItem>();
            VendorPartnerOptions = new ObservableCollection<PartnerDto>();

            EditModel = new UserEditModel();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);
            ResetPasswordCommand = new AsyncRelayCommand(ResetPasswordAsync);
        }

        public ObservableCollection<UserDto> Items { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public ObservableCollection<UserRoleCheckItem> RoleOptions { get; }

        public ObservableCollection<PartnerDto> VendorPartnerOptions { get; }

        public UserEditModel EditModel { get; }

        public AsyncRelayCommand SaveCommand { get; }

        public AsyncRelayCommand DeleteCommand { get; }

        public AsyncRelayCommand ResetPasswordCommand { get; }

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

        public bool IsLoginIdEditable
        {
            get => _isLoginIdEditable;
            set => SetProperty(ref _isLoginIdEditable, value);
        }

        public async Task InitializeAsync()
        {
            await LoadRoleOptionsAsync();
            await LoadVendorPartnerOptionsAsync();
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();

            var result = await _apiClient.GetAsync<UserListResponse>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "회원 조회 중 오류가 발생했습니다.");
                return false;
            }

            Items.Clear();

            foreach (var item in result.Data?.Items ?? new List<UserDto>())
            {
                Items.Add(item);
            }

            ApplyListPage(
                result.Data?.Total ?? 0,
                result.Data?.Page ?? ListPage,
                result.Data?.Size ?? ListPageSize);
            return true;
        }

        protected override void OnSelectedItemChanged(UserDto? item)
        {
            LoadToEditModel(item);
        }

        protected override void Reset()
        {
            SearchKeyword = string.Empty;
            SelectedUseYn = "사용";
            SelectedItem = null;
            EditModel.Clear();
            ClearRoleSelection();
            IsLoginIdEditable = true;
        }

        protected override void New()
        {
            SelectedItem = null;
            EditModel.Clear();
            ClearRoleSelection();
            IsLoginIdEditable = true;
        }

        private async Task LoadRoleOptionsAsync()
        {
            var result = await _apiClient.GetAsync<List<UserRoleOptionDto>>(
                ApiRoutes.UserRoleOptions);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "역할 목록 조회 중 오류가 발생했습니다.");
                return;
            }

            RoleOptions.Clear();

            foreach (var role in result.Data ?? new List<UserRoleOptionDto>())
            {
                var item = new UserRoleCheckItem();
                item.LoadFromDto(role);
                RoleOptions.Add(item);
            }
        }

        private async Task SaveAsync()
        {
            NormalizeEditModel();
            SyncSelectedRolesToEditModel();

            if (!ValidateForSave())
            {
                return;
            }

            IsLoading = true;

            try
            {
                if (EditModel.UserId.HasValue)
                {
                    await UpdateAsync(EditModel.UserId.Value);
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
            if (SelectedItem == null || !EditModel.UserId.HasValue)
            {
                _messageService.ShowWarning("삭제할 회원을 먼저 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.LoginId}] {SelectedItem.UserName} 회원을 삭제하시겠습니까?",
                "삭제 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;

            try
            {
                var result = await _apiClient.DeleteAsync(
                    $"{ApiRoutes.Users}/{SelectedItem.UserId}");

                if (!result.Success || !result.Data)
                {
                    _messageService.ShowError(result.Message ?? "회원 삭제 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();

                SelectedItem = null;
                EditModel.Clear();
                ClearRoleSelection();
                IsLoginIdEditable = true;

                _messageService.ShowInfo("삭제되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task ResetPasswordAsync()
        {
            if (SelectedItem == null || !EditModel.UserId.HasValue)
            {
                _messageService.ShowWarning("비밀번호를 초기화할 회원을 먼저 선택하세요.");
                return;
            }

            EditModel.ResetPassword = EditModel.ResetPassword?.Trim() ?? string.Empty;

            if (string.IsNullOrWhiteSpace(EditModel.ResetPassword))
            {
                _messageService.ShowWarning("새 비밀번호를 입력하세요.");
                return;
            }

            if (EditModel.ResetPassword.Length < 6)
            {
                _messageService.ShowWarning("비밀번호는 최소 6자리 이상입니다.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.LoginId}] {SelectedItem.UserName} 회원의 비밀번호를 초기화하시겠습니까?",
                "비밀번호 초기화 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;

            try
            {
                var request = new UserResetPasswordRequest
                {
                    NewPassword = EditModel.ResetPassword
                };

                var result = await _apiClient.PatchAsync<UserResetPasswordRequest, UserDto>(
                    $"{ApiRoutes.Users}/{SelectedItem.UserId}/reset-password",
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "비밀번호 초기화 중 오류가 발생했습니다.");
                    return;
                }

                EditModel.ResetPassword = string.Empty;

                _messageService.ShowInfo("비밀번호가 초기화되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task CreateAsync()
        {
            var request = new UserCreateRequest
            {
                LoginId = EditModel.LoginId,
                UserName = EditModel.UserName,
                Password = EditModel.InitialPassword,
                RoleIds = EditModel.RoleIds,
                Department = EmptyToNull(EditModel.Department),
                Position = EmptyToNull(EditModel.Position),
                IsActive = EditModel.IsActive,
                IsVendorUser = EditModel.IsVendorUser,
                VendorPartnerId = EditModel.IsVendorUser ? EditModel.VendorPartnerId : null,
                VendorAccessActive = true
            };

            var result = await _apiClient.PostAsync<UserCreateRequest, UserDto>(
                ApiRoutes.Users,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "회원 저장 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            ClearRoleSelection();
            IsLoginIdEditable = true;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long userId)
        {
            var request = new UserUpdateRequest
            {
                UserName = EditModel.UserName,
                RoleIds = EditModel.RoleIds,
                Department = EmptyToNull(EditModel.Department),
                Position = EmptyToNull(EditModel.Position),
                IsActive = EditModel.IsActive,
                IsVendorUser = EditModel.IsVendorUser,
                VendorPartnerId = EditModel.IsVendorUser ? EditModel.VendorPartnerId : null,
                VendorAccessActive = true
            };

            var result = await _apiClient.PatchAsync<UserUpdateRequest, UserDto>(
                $"{ApiRoutes.Users}/{userId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "회원 수정 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            SelectedItem = null;
            EditModel.Clear();
            ClearRoleSelection();
            IsLoginIdEditable = true;

            _messageService.ShowInfo("저장되었습니다.");
        }

        private void LoadToEditModel(UserDto? item)
        {
            if (item == null)
            {
                EditModel.Clear();
                ClearRoleSelection();
                IsLoginIdEditable = true;
                return;
            }

            EditModel.LoadFromDto(item);
            ApplyRoleSelection(EditModel.RoleIds);
            IsLoginIdEditable = false;
        }

        private bool ValidateForSave()
        {
            if (!EditModel.UserId.HasValue && string.IsNullOrWhiteSpace(EditModel.LoginId))
            {
                _messageService.ShowWarning("아이디는 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.UserName))
            {
                _messageService.ShowWarning("사용자명은 필수입니다.");
                return false;
            }

            if (!EditModel.UserId.HasValue)
            {
                if (string.IsNullOrWhiteSpace(EditModel.InitialPassword))
                {
                    _messageService.ShowWarning("신규 회원의 초기 비밀번호는 필수입니다.");
                    return false;
                }

                if (EditModel.InitialPassword.Length < 6)
                {
                    _messageService.ShowWarning("초기 비밀번호는 최소 6자리 이상입니다.");
                    return false;
                }
            }

            if (EditModel.RoleIds == null || EditModel.RoleIds.Count == 0)
            {
                _messageService.ShowWarning("역할은 최소 1개 이상 선택해야 합니다.");
                return false;
            }

            if (EditModel.IsVendorUser && !EditModel.VendorPartnerId.HasValue)
            {
                _messageService.ShowWarning("외주업체 계정은 외주업체를 선택해야 합니다.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.LoginId = EditModel.LoginId?.Trim() ?? string.Empty;
            EditModel.UserName = EditModel.UserName?.Trim() ?? string.Empty;
            EditModel.InitialPassword = EditModel.InitialPassword?.Trim() ?? string.Empty;
            EditModel.ResetPassword = EditModel.ResetPassword?.Trim() ?? string.Empty;
            EditModel.Department = EditModel.Department?.Trim() ?? string.Empty;
            EditModel.Position = EditModel.Position?.Trim() ?? string.Empty;
        }

        private void SyncSelectedRolesToEditModel()
        {
            EditModel.RoleIds = RoleOptions
                .Where(x => x.IsSelected)
                .Select(x => x.RoleId)
                .Distinct()
                .OrderBy(x => x)
                .ToList();

            if (EditModel.IsVendorUser)
            {
                var vendorRole = RoleOptions.FirstOrDefault(x => x.RoleCode == VendorPortalRoleCode);
                if (vendorRole != null && !EditModel.RoleIds.Contains(vendorRole.RoleId))
                {
                    vendorRole.IsSelected = true;
                    EditModel.RoleIds.Add(vendorRole.RoleId);
                    EditModel.RoleIds = EditModel.RoleIds
                        .Distinct()
                        .OrderBy(x => x)
                        .ToList();
                }
            }
        }

        private void ApplyRoleSelection(List<long> roleIds)
        {
            var selectedRoleIds = new HashSet<long>(roleIds ?? new List<long>());

            foreach (var role in RoleOptions)
            {
                role.IsSelected = selectedRoleIds.Contains(role.RoleId);
            }
        }

        private void ClearRoleSelection()
        {
            foreach (var role in RoleOptions)
            {
                role.IsSelected = false;
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

            return $"{ApiRoutes.Users}?{string.Join("&", queryParts)}";
        }

        private static string? EmptyToNull(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private async Task LoadVendorPartnerOptionsAsync()
        {
            var result = await _apiClient.GetAsync<PartnerListDto>(
                $"{ApiRoutes.Partners}?page=1&size=100&is_active=true&partner_type=VENDOR");

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "외주업체 목록 조회 중 오류가 발생했습니다.");
                return;
            }

            VendorPartnerOptions.Clear();

            foreach (var partner in (result.Data?.Items ?? new List<PartnerDto>())
                         .Where(x => x.PartnerType == "VENDOR")
                         .OrderBy(x => x.Name))
            {
                VendorPartnerOptions.Add(partner);
            }
        }
    }
}
