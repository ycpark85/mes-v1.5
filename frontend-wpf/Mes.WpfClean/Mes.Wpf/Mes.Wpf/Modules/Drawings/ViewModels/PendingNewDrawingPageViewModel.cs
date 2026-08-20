using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.Drawings.Dtos;
using Mes.Wpf.Modules.Drawings.Services;
using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Drawings.ViewModels
{
    public class PendingNewDrawingPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly IDrawingFileOpener _drawingFileOpener;

        private string _searchKeyword = string.Empty;
        private PendingNewDrawingDto? _selectedItem;
        private DrawingRevisionDto? _selectedRevision;
        private string _drawingUploadPath = string.Empty;
        private string _originalUploadPath = string.Empty;
        private string _plateUploadPath = string.Empty;
        private bool _isDrawingFileDirty;
        private bool _isOriginalFileDirty;
        private bool _isPlateFileDirty;
        private bool _isLoading;
        private string _loadingMessage = "처리 중입니다...";
        private string _summaryText = "대기 중";
        private int _currentPage = 1;
        private int _pageSize = 100;
        private int _totalCount;

        public PendingNewDrawingPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            IDrawingFileOpener drawingFileOpener)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _drawingFileOpener = drawingFileOpener;

            Items = new ObservableCollection<PendingNewDrawingDto>();
            RevisionItems = new ObservableCollection<DrawingRevisionDto>();
            RevisionEditModel = new DrawingRevisionEditModel();

            SearchCommand = new AsyncRelayCommand(SearchFirstPageAsync);
            ResetCommand = new RelayCommand(Reset);
            PreviousPageCommand = new AsyncRelayCommand(
                GoPreviousPageAsync,
                () => !IsLoading && HasPreviousPage);
            NextPageCommand = new AsyncRelayCommand(
                GoNextPageAsync,
                () => !IsLoading && HasNextPage);
            NewRevisionCommand = new RelayCommand(NewRevision);
            SaveRevisionBundleCommand = new AsyncRelayCommand(SaveRevisionBundleAsync);
            SaveChangedFilesCommand = new AsyncRelayCommand(SaveChangedFilesAsync);

            BrowseDrawingFileCommand = new RelayCommand(BrowseDrawingFile);
            BrowseOriginalFileCommand = new RelayCommand(BrowseOriginalFile);
            BrowsePlateFileCommand = new RelayCommand(BrowsePlateFile);

            OpenDrawingFileCommand = new RelayCommand(() => _ = OpenDrawingFileAsync());
            OpenOriginalFileCommand = new RelayCommand(() => _ = OpenOriginalFileAsync());
            OpenPlateFileCommand = new RelayCommand(() => _ = OpenPlateFileAsync());
        }

        public ObservableCollection<PendingNewDrawingDto> Items { get; }
        public ObservableCollection<DrawingRevisionDto> RevisionItems { get; }
        public DrawingRevisionEditModel RevisionEditModel { get; }

        public AsyncRelayCommand SearchCommand { get; }
        public RelayCommand ResetCommand { get; }
        public AsyncRelayCommand PreviousPageCommand { get; }
        public AsyncRelayCommand NextPageCommand { get; }
        public RelayCommand NewRevisionCommand { get; }
        public AsyncRelayCommand SaveRevisionBundleCommand { get; }
        public AsyncRelayCommand SaveChangedFilesCommand { get; }

        public RelayCommand BrowseDrawingFileCommand { get; }
        public RelayCommand BrowseOriginalFileCommand { get; }
        public RelayCommand BrowsePlateFileCommand { get; }
        public RelayCommand OpenDrawingFileCommand { get; }
        public RelayCommand OpenOriginalFileCommand { get; }
        public RelayCommand OpenPlateFileCommand { get; }

        public int TotalPages => Math.Max(1, (int)Math.Ceiling((double)_totalCount / _pageSize));
        public bool HasPreviousPage => _currentPage > 1;
        public bool HasNextPage => _currentPage < TotalPages;
        public string PageDisplayText => $"{_currentPage:N0} / {TotalPages:N0} 페이지 (총 {_totalCount:N0}건)";

        public string SearchKeyword
        {
            get => _searchKeyword;
            set => SetProperty(ref _searchKeyword, value);
        }

        public PendingNewDrawingDto? SelectedItem
        {
            get => _selectedItem;
            set
            {
                if (SetProperty(ref _selectedItem, value))
                {
                    _ = LoadSelectedDrawingAsync(value);
                    RaiseAllStates();
                }
            }
        }

        public DrawingRevisionDto? SelectedRevision
        {
            get => _selectedRevision;
            set
            {
                if (SetProperty(ref _selectedRevision, value))
                {
                    LoadRevisionToEditModel(value);
                }
            }
        }

        public string DrawingUploadPath
        {
            get => _drawingUploadPath;
            set
            {
                if (SetProperty(ref _drawingUploadPath, value))
                {
                    IsDrawingFileDirty = !string.IsNullOrWhiteSpace(value);
                    RaiseFileStates();
                }
            }
        }

        public string OriginalUploadPath
        {
            get => _originalUploadPath;
            set
            {
                if (SetProperty(ref _originalUploadPath, value))
                {
                    IsOriginalFileDirty = !string.IsNullOrWhiteSpace(value);
                    RaiseFileStates();
                }
            }
        }

        public string PlateUploadPath
        {
            get => _plateUploadPath;
            set
            {
                if (SetProperty(ref _plateUploadPath, value))
                {
                    IsPlateFileDirty = !string.IsNullOrWhiteSpace(value);
                    RaiseFileStates();
                }
            }
        }

        public bool IsDrawingFileDirty
        {
            get => _isDrawingFileDirty;
            set => SetProperty(ref _isDrawingFileDirty, value);
        }

        public bool IsOriginalFileDirty
        {
            get => _isOriginalFileDirty;
            set => SetProperty(ref _isOriginalFileDirty, value);
        }

        public bool IsPlateFileDirty
        {
            get => _isPlateFileDirty;
            set => SetProperty(ref _isPlateFileDirty, value);
        }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    RaisePageState();
                }
            }
        }

        public string LoadingMessage
        {
            get => _loadingMessage;
            set => SetProperty(ref _loadingMessage, value);
        }

        public string SummaryText
        {
            get => _summaryText;
            set => SetProperty(ref _summaryText, value);
        }

        public string SelectedDrawingNo => SelectedItem?.DrawingNo ?? string.Empty;
        public string SelectedProductCode => SelectedItem?.ProductCode ?? string.Empty;
        public string SelectedProductName => SelectedItem?.ProductName ?? string.Empty;

        public bool HasSelectedDrawing => SelectedItem != null;
        public bool CanCreateRevision => SelectedItem != null;
        public bool CanManageRevisionFiles => RevisionEditModel.RevisionId.HasValue;

        public bool CanSaveChangedFiles =>
            RevisionEditModel.RevisionId.HasValue &&
            (
                (IsDrawingFileDirty && !string.IsNullOrWhiteSpace(DrawingUploadPath)) ||
                (IsOriginalFileDirty && !string.IsNullOrWhiteSpace(OriginalUploadPath)) ||
                (IsPlateFileDirty && !string.IsNullOrWhiteSpace(PlateUploadPath))
            );

        public string DrawingUploadFileName =>
            string.IsNullOrWhiteSpace(DrawingUploadPath) ? string.Empty : Path.GetFileName(DrawingUploadPath);

        public string OriginalUploadFileName =>
            string.IsNullOrWhiteSpace(OriginalUploadPath) ? string.Empty : Path.GetFileName(OriginalUploadPath);

        public string PlateUploadFileName =>
            string.IsNullOrWhiteSpace(PlateUploadPath) ? string.Empty : Path.GetFileName(PlateUploadPath);

        public string DrawingDisplayFileName =>
            !string.IsNullOrWhiteSpace(DrawingUploadFileName)
                ? DrawingUploadFileName
                : RevisionEditModel.DrawingFileName;

        public string OriginalDisplayFileName =>
            !string.IsNullOrWhiteSpace(OriginalUploadFileName)
                ? OriginalUploadFileName
                : RevisionEditModel.OriginalFileName;

        public string PlateDisplayFileName =>
            !string.IsNullOrWhiteSpace(PlateUploadFileName)
                ? PlateUploadFileName
                : RevisionEditModel.PlateFileName;

        public async Task InitializeAsync()
        {
            await SearchFirstPageAsync();
        }

        private async Task SearchFirstPageAsync()
        {
            _currentPage = 1;
            RaisePageState();
            await SearchAsync();
        }

        private async Task<bool> SearchAsync()
        {
            IsLoading = true;
            LoadingMessage = "신규작성도면 조회 중...";

            try
            {
                var selectedDrawingId = SelectedItem?.DrawingId;
                var result = await _apiClient.GetAsync<PagedResult<PendingNewDrawingDto>>(BuildListUrl());

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "신규작성도면 조회 중 오류가 발생했습니다.");
                    return false;
                }

                Items.Clear();
                foreach (var item in result.Data.Items ?? new List<PendingNewDrawingDto>())
                {
                    Items.Add(item);
                }

                SummaryText = $"대상: {result.Data.Total}건";
                _totalCount = Math.Max(0, result.Data.Total);
                _currentPage = Math.Max(1, result.Data.Page);
                _pageSize = result.Data.Size > 0 ? result.Data.Size : _pageSize;
                RaisePageState();

                SelectedItem = selectedDrawingId.HasValue
                    ? Items.FirstOrDefault(x => x.DrawingId == selectedDrawingId.Value)
                    : null;

                if (SelectedItem == null)
                {
                    ClearSelectionDetail();
                }

                return true;
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private void Reset()
        {
            SearchKeyword = string.Empty;
            _ = SearchFirstPageAsync();
        }

        private async Task GoPreviousPageAsync()
        {
            if (HasPreviousPage)
            {
                var previousPage = _currentPage;
                _currentPage--;
                RaisePageState();
                if (!await SearchAsync())
                {
                    _currentPage = previousPage;
                    RaisePageState();
                }
            }
        }

        private async Task GoNextPageAsync()
        {
            if (HasNextPage)
            {
                var previousPage = _currentPage;
                _currentPage++;
                RaisePageState();
                if (!await SearchAsync())
                {
                    _currentPage = previousPage;
                    RaisePageState();
                }
            }
        }

        private void RaisePageState()
        {
            OnPropertyChanged(nameof(TotalPages));
            OnPropertyChanged(nameof(HasPreviousPage));
            OnPropertyChanged(nameof(HasNextPage));
            OnPropertyChanged(nameof(PageDisplayText));
            PreviousPageCommand.RaiseCanExecuteChanged();
            NextPageCommand.RaiseCanExecuteChanged();
        }

        private string BuildListUrl()
        {
            var queryParts = new List<string>
            {
                $"page={_currentPage}",
                $"size={_pageSize}"
            };

            if (!string.IsNullOrWhiteSpace(SearchKeyword))
            {
                queryParts.Add($"q={Uri.EscapeDataString(SearchKeyword.Trim())}");
            }

            return $"{ApiRoutes.PendingNewDrawings}?{string.Join("&", queryParts)}";
        }

        private async Task LoadSelectedDrawingAsync(PendingNewDrawingDto? item)
        {
            if (item == null)
            {
                ClearSelectionDetail();
                return;
            }

            await LoadRevisionListAsync(item.DrawingId);
            RaiseAllStates();
        }

        private async Task LoadRevisionListAsync(long drawingId)
        {
            var route = $"{ApiRoutes.Drawings}/{drawingId}/revisions?page=1&size=100";
            var result = await _apiClient.GetAsync<PagedResult<DrawingRevisionDto>>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "리비전 조회 중 오류가 발생했습니다.");
                return;
            }

            var selectedRevisionId = SelectedRevision?.RevisionId ?? RevisionEditModel.RevisionId;

            RevisionItems.Clear();
            foreach (var item in result.Data?.Items ?? new List<DrawingRevisionDto>())
            {
                RevisionItems.Add(item);
            }

            SelectedRevision = selectedRevisionId.HasValue
                ? RevisionItems.FirstOrDefault(x => x.RevisionId == selectedRevisionId.Value)
                : RevisionItems.FirstOrDefault(x => x.RevisionId == SelectedItem?.CurrentRevisionId)
                    ?? RevisionItems.FirstOrDefault();

            if (SelectedRevision == null)
            {
                RevisionEditModel.Clear();
                ClearUploadPaths();
                ClearDirtyFlags();
            }

            RaiseAllStates();
        }

        private void NewRevision()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("먼저 작업할 도면을 선택하세요.");
                return;
            }

            SelectedRevision = null;
            RevisionEditModel.Clear();
            ClearUploadPaths();
            ClearDirtyFlags();
            RaiseAllStates();
        }

        private async Task SaveRevisionBundleAsync()
        {
            if (SelectedItem == null)
            {
                _messageService.ShowWarning("먼저 작업할 도면을 선택하세요.");
                return;
            }

            if (RevisionEditModel.RevisionId.HasValue)
            {
                _messageService.ShowWarning("기존 리비전의 파일 변경은 '파일 변경 저장'을 사용하세요.");
                return;
            }

            RevisionEditModel.RevNo = RevisionEditModel.RevNo?.Trim() ?? string.Empty;

            if (string.IsNullOrWhiteSpace(RevisionEditModel.RevNo))
            {
                _messageService.ShowWarning("Rev No를 입력하세요.");
                return;
            }

            if (string.IsNullOrWhiteSpace(DrawingUploadPath) || !File.Exists(DrawingUploadPath))
            {
                _messageService.ShowWarning("도면파일을 선택하세요.");
                return;
            }

            var missingFilePath = DrawingMultipartContentFactory.FindMissingFile(
                DrawingUploadPath,
                OriginalUploadPath,
                PlateUploadPath);
            if (missingFilePath != null)
            {
                _messageService.ShowWarning($"선택한 파일을 찾을 수 없습니다.\n{missingFilePath}");
                return;
            }

            IsLoading = true;
            LoadingMessage = "리비전 및 도면파일 저장 중...";
            await Task.Yield();

            var completed = false;

            try
            {
                using var content = DrawingMultipartContentFactory.CreateRevisionBundle(
                    RevisionEditModel.RevNo,
                    true,
                    DrawingUploadPath,
                    OriginalUploadPath,
                    PlateUploadPath);

                var result = await _apiClient.PostMultipartAsync<DrawingRevisionDto>(
                    $"{ApiRoutes.Drawings}/{SelectedItem.DrawingId}/revisions/bundle",
                    content);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "리비전 저장 중 오류가 발생했습니다.");
                    return;
                }

                completed = true;
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }

            if (completed)
            {
                _messageService.ShowInfo("도면파일이 저장되었습니다.");
                await SearchAsync();
            }
        }

        private async Task SaveChangedFilesAsync()
        {
            if (SelectedItem == null || !RevisionEditModel.RevisionId.HasValue)
            {
                _messageService.ShowWarning("먼저 리비전을 선택하세요.");
                return;
            }

            if (!CanSaveChangedFiles)
            {
                _messageService.ShowWarning("변경된 파일이 없습니다.");
                return;
            }

            if (!HasRevisionFile("DRAWING") &&
                (string.IsNullOrWhiteSpace(DrawingUploadPath) || !File.Exists(DrawingUploadPath)))
            {
                _messageService.ShowWarning("도면파일을 선택하세요.");
                return;
            }

            IsLoading = true;
            LoadingMessage = "변경 파일 저장 중...";
            await Task.Yield();

            var completed = false;

            try
            {
                if (IsDrawingFileDirty && !string.IsNullOrWhiteSpace(DrawingUploadPath))
                {
                    if (!await SaveChangedFileInternalAsync("DRAWING", DrawingUploadPath)) return;
                }

                if (IsOriginalFileDirty && !string.IsNullOrWhiteSpace(OriginalUploadPath))
                {
                    if (!await SaveChangedFileInternalAsync("ORIGINAL", OriginalUploadPath)) return;
                }

                if (IsPlateFileDirty && !string.IsNullOrWhiteSpace(PlateUploadPath))
                {
                    if (!await SaveChangedFileInternalAsync("PLATE", PlateUploadPath)) return;
                }

                completed = true;
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }

            if (completed)
            {
                _messageService.ShowInfo("변경된 파일이 저장되었습니다.");
                await SearchAsync();
            }
        }

        private async Task<bool> SaveChangedFileInternalAsync(string fileKind, string filePath)
        {
            if (HasRevisionFile(fileKind))
            {
                return await ReplaceRevisionFileInternalAsync(fileKind, filePath);
            }

            return await UploadRevisionFileInternalAsync(RevisionEditModel.RevisionId!.Value, fileKind, filePath);
        }

        private async Task<bool> UploadRevisionFileInternalAsync(long revisionId, string fileKind, string filePath)
        {
            if (SelectedItem == null)
            {
                return false;
            }

            if (string.IsNullOrWhiteSpace(filePath) || !File.Exists(filePath))
            {
                _messageService.ShowWarning($"{GetFileKindDisplayName(fileKind)}을 선택하세요.");
                return false;
            }

            using var content = DrawingMultipartContentFactory.CreateSingleFile(fileKind, filePath, true);

            var result = await _apiClient.PostMultipartAsync<DrawingRevisionFileDto>(
                $"{ApiRoutes.Drawings}/{SelectedItem.DrawingId}/revisions/{revisionId}/files",
                content);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? $"{GetFileKindDisplayName(fileKind)} 업로드 중 오류가 발생했습니다.");
                return false;
            }

            return true;
        }

        private async Task<bool> ReplaceRevisionFileInternalAsync(string fileKind, string filePath)
        {
            if (SelectedItem == null || !RevisionEditModel.RevisionId.HasValue)
            {
                _messageService.ShowWarning("먼저 리비전을 선택하세요.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(filePath) || !File.Exists(filePath))
            {
                _messageService.ShowWarning($"{GetFileKindDisplayName(fileKind)}을 선택하세요.");
                return false;
            }

            using var content = DrawingMultipartContentFactory.CreateSingleFile(fileKind, filePath, false);

            var result = await _apiClient.PatchMultipartAsync<DrawingRevisionFileDto>(
                $"{ApiRoutes.Drawings}/{SelectedItem.DrawingId}/revisions/{RevisionEditModel.RevisionId.Value}/files/{fileKind}",
                content);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? $"{GetFileKindDisplayName(fileKind)} 교체 중 오류가 발생했습니다.");
                return false;
            }

            return true;
        }

        private async Task OpenDrawingFileAsync()
        {
            await OpenRevisionFileAsync(RevisionEditModel.DrawingFileId, RevisionEditModel.DrawingFileName);
        }

        private async Task OpenOriginalFileAsync()
        {
            await OpenRevisionFileAsync(RevisionEditModel.OriginalFileId, RevisionEditModel.OriginalFileName);
        }

        private async Task OpenPlateFileAsync()
        {
            await OpenRevisionFileAsync(RevisionEditModel.PlateFileId, RevisionEditModel.PlateFileName);
        }

        private async Task OpenRevisionFileAsync(long? revisionFileId, string? fileName)
        {
            if (!revisionFileId.HasValue)
            {
                _messageService.ShowWarning("열 수 있는 파일이 없습니다.");
                return;
            }

            var url = _apiClient.BuildAbsoluteUrl(
                $"{ApiRoutes.Drawings}/revision-files/{revisionFileId.Value}/download");

            IsLoading = true;
            LoadingMessage = "파일 여는 중...";

            try
            {
                await _drawingFileOpener.OpenRevisionFileAsync(url, fileName);
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private void BrowseDrawingFile()
        {
            DrawingUploadPath = PickFile();
        }

        private void BrowseOriginalFile()
        {
            OriginalUploadPath = PickFile();
        }

        private void BrowsePlateFile()
        {
            PlateUploadPath = PickFile();
        }

        private void LoadRevisionToEditModel(DrawingRevisionDto? item)
        {
            if (item == null)
            {
                RevisionEditModel.Clear();
                ClearUploadPaths();
                ClearDirtyFlags();
                RaiseAllStates();
                return;
            }

            RevisionEditModel.LoadFromDto(item);
            ClearUploadPaths();
            ClearDirtyFlags();
            RaiseAllStates();
        }

        private void ClearSelectionDetail()
        {
            SelectedRevision = null;
            RevisionItems.Clear();
            RevisionEditModel.Clear();
            ClearUploadPaths();
            ClearDirtyFlags();
            RaiseAllStates();
        }

        private static string PickFile()
        {
            var dialog = new OpenFileDialog
            {
                Filter = "모든 파일|*.*"
            };

            return dialog.ShowDialog() == true ? dialog.FileName : string.Empty;
        }

        private void ClearUploadPaths()
        {
            _drawingUploadPath = string.Empty;
            _originalUploadPath = string.Empty;
            _plateUploadPath = string.Empty;

            OnPropertyChanged(nameof(DrawingUploadPath));
            OnPropertyChanged(nameof(OriginalUploadPath));
            OnPropertyChanged(nameof(PlateUploadPath));

            RaiseFileStates();
        }

        private void ClearDirtyFlags()
        {
            IsDrawingFileDirty = false;
            IsOriginalFileDirty = false;
            IsPlateFileDirty = false;
            OnPropertyChanged(nameof(CanSaveChangedFiles));
        }

        private bool HasRevisionFile(string fileKind)
        {
            return fileKind switch
            {
                "DRAWING" => RevisionEditModel.DrawingFileId.HasValue,
                "ORIGINAL" => RevisionEditModel.OriginalFileId.HasValue,
                "PLATE" => RevisionEditModel.PlateFileId.HasValue,
                _ => false
            };
        }

        private void RaiseFileStates()
        {
            OnPropertyChanged(nameof(DrawingUploadFileName));
            OnPropertyChanged(nameof(OriginalUploadFileName));
            OnPropertyChanged(nameof(PlateUploadFileName));
            OnPropertyChanged(nameof(DrawingDisplayFileName));
            OnPropertyChanged(nameof(OriginalDisplayFileName));
            OnPropertyChanged(nameof(PlateDisplayFileName));
            OnPropertyChanged(nameof(CanManageRevisionFiles));
            OnPropertyChanged(nameof(CanSaveChangedFiles));
        }

        private void RaiseAllStates()
        {
            RaiseFileStates();
            OnPropertyChanged(nameof(SelectedDrawingNo));
            OnPropertyChanged(nameof(SelectedProductCode));
            OnPropertyChanged(nameof(SelectedProductName));
            OnPropertyChanged(nameof(HasSelectedDrawing));
            OnPropertyChanged(nameof(CanCreateRevision));
            OnPropertyChanged(nameof(CanManageRevisionFiles));
        }

        private static string GetFileKindDisplayName(string fileKind)
        {
            return fileKind switch
            {
                "DRAWING" => "도면파일",
                "ORIGINAL" => "원본파일",
                "PLATE" => "판작업파일",
                _ => "파일"
            };
        }
    }
}
