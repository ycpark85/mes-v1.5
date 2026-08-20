using ClosedXML.Excel;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.Drawings.Dtos;
using Mes.Wpf.Modules.Products.Dtos;
using Mes.Wpf.Modules.Products.Services;
using Mes.Wpf.Modules.RoutingTemplates.Dtos;
using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Products.ViewModels
{
    public class ProductPageViewModel : CrudPageViewModelBase<ProductDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly IDrawingViewer _drawingViewer;

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private bool _isCodeEditable = true;
        private bool _isEditMode = true;
        private string _bulkFilePath = string.Empty;
        private string _bulkSummaryText = "대기 중";
        private string _loadingMessage = "처리 중입니다...";
        private string _drawingSearchKeyword = string.Empty;
        private string _selectedDrawingNo = string.Empty;
        private long? _selectedDrawingCurrentRevisionId;
        private CancellationTokenSource? _drawingSearchCts;

        public ProductPageViewModel(IApiClient apiClient, IMessageService messageService, IDrawingViewer drawingViewer)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _drawingViewer = drawingViewer;
            Items = new ObservableCollection<ProductDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };
            UomOptions = new ObservableCollection<string> { "EA", "Roll" };
            DrawingOptions = new ObservableCollection<DrawingDto>();
            RoutingTemplateOptions = new ObservableCollection<RoutingTemplateDto>();
            EditModel = new ProductEditModel();
            EditModel.Uom = "EA";
            BulkRows = new ObservableCollection<ProductBulkUploadRowModel>();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);
            DownloadTemplateCommand = new AsyncRelayCommand(DownloadTemplateAsync);
            SelectBulkFileCommand = new AsyncRelayCommand(SelectBulkFileAsync);
            UploadBulkCommand = new AsyncRelayCommand(UploadBulkAsync);
            ClearBulkRowsCommand = new RelayCommand(ClearBulkRows);
            EditCommand = new RelayCommand(EnterEditMode);
            ViewDrawingCommand = new RelayCommand(() => _ = ViewDrawingAsync());
        }

        public ObservableCollection<ProductDto> Items { get; }
        public ObservableCollection<string> UseYnOptions { get; }
        public ObservableCollection<string> UomOptions { get; }
        public ObservableCollection<DrawingDto> DrawingOptions { get; }
        public ObservableCollection<RoutingTemplateDto> RoutingTemplateOptions { get; }
        public ProductEditModel EditModel { get; }
        public ObservableCollection<ProductBulkUploadRowModel> BulkRows { get; }

        public AsyncRelayCommand SaveCommand { get; }
        public AsyncRelayCommand DeleteCommand { get; }
        public AsyncRelayCommand DownloadTemplateCommand { get; }
        public AsyncRelayCommand SelectBulkFileCommand { get; }
        public AsyncRelayCommand UploadBulkCommand { get; }
        public RelayCommand ClearBulkRowsCommand { get; }

        public RelayCommand EditCommand { get; }

        public RelayCommand ViewDrawingCommand { get; }

        public IApiClient ApiClient => _apiClient;

        public IMessageService MessageService => _messageService;

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

        public bool IsEditMode
        {
            get => _isEditMode;
            set
            {
                if (SetProperty(ref _isEditMode, value))
                {
                    OnPropertyChanged(nameof(IsReadOnlyMode));
                    OnPropertyChanged(nameof(CanSave));
                    OnPropertyChanged(nameof(CanEdit));
                }
            }
        }

        public bool IsReadOnlyMode => !IsEditMode;
        public bool CanSave => IsEditMode && !IsLoading;
        public bool CanEdit => !IsEditMode && SelectedItem != null && !IsLoading;

        public string BulkFilePath
        {
            get => _bulkFilePath;
            set => SetProperty(ref _bulkFilePath, value);
        }

        public string BulkSummaryText
        {
            get => _bulkSummaryText;
            set => SetProperty(ref _bulkSummaryText, value);
        }

        public string LoadingMessage
        {
            get => _loadingMessage;
            set => SetProperty(ref _loadingMessage, value);
        }

        public string DrawingSearchKeyword
        {
            get => _drawingSearchKeyword;
            set
            {
                if (SetProperty(ref _drawingSearchKeyword, value))
                {
                    _ = SearchDrawingsAsync(value);
                }
            }
        }

        public string SelectedDrawingNo
        {
            get => _selectedDrawingNo;
            set => SetProperty(ref _selectedDrawingNo, value);
        }
        public long? SelectedDrawingCurrentRevisionId
        {
            get => _selectedDrawingCurrentRevisionId;
            set => SetProperty(ref _selectedDrawingCurrentRevisionId, value);
        }

        public async Task InitializeAsync()
        {
            await LoadRoutingTemplateLookupAsync();
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();
            var result = await _apiClient.GetAsync<ProductListResponse>(route);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "품목 조회 중 오류가 발생했습니다.");
                return false;
            }

            Items.Clear();
            foreach (var item in result.Data.Items)
            {
                Items.Add(item);
            }

            ApplyListPage(result.Data.Total, result.Data.Page, result.Data.Size);
            return true;
        }

        protected override void Reset()
        {
            SearchKeyword = string.Empty;
            SelectedUseYn = "사용";
            SelectedItem = null;
            EditModel.Clear();
            EditModel.Uom = "EA";

            DrawingSearchKeyword = string.Empty;
            SelectedDrawingNo = string.Empty;
            SelectedDrawingCurrentRevisionId = null;
            DrawingOptions.Clear();

            IsCodeEditable = true;
            IsEditMode = true;

            _ = SearchDrawingsAsync(string.Empty);
        }

        protected override void New()
        {
            SelectedItem = null;
            EditModel.Clear();
            EditModel.Uom = "EA";

            DrawingSearchKeyword = string.Empty;
            SelectedDrawingNo = string.Empty;
            SelectedDrawingCurrentRevisionId = null;
            DrawingOptions.Clear();

            IsCodeEditable = true;
            IsEditMode = true;

            _ = SearchDrawingsAsync(string.Empty);
        }

        protected override void OnSelectedItemChanged(ProductDto? item)
        {
            _ = LoadToEditModelAsync(item);
        }

        private void EnterEditMode()
        {
            if (SelectedItem == null)
            {
                return;
            }

            IsEditMode = true;
            IsCodeEditable = false;

            _ = SearchDrawingsAsync(string.Empty);
        }

        private async Task LoadRoutingTemplateLookupAsync()
        {
            var routingResult = await _apiClient.GetAsync<PagedResult<RoutingTemplateDto>>(
                $"{ApiRoutes.RoutingTemplates}?page=1&size=100&is_active=true");

            if (!routingResult.Success || routingResult.Data == null)
            {
                _messageService.ShowError(routingResult.Message ?? "라우팅 목록 조회 중 오류가 발생했습니다.");
                return;
            }

            RoutingTemplateOptions.Clear();
            foreach (var item in routingResult.Data.Items)
            {
                RoutingTemplateOptions.Add(item);
            }
        }

        private async Task SaveAsync()
        {
            if (IsLoading)
            {
                return;
            }

            NormalizeEditModel();
            if (!ValidateForSave())
            {
                return;
            }

            IsLoading = true;
            try
            {
                if (SelectedItem == null)
                {
                    await CreateAsync();
                }
                else
                {
                    await UpdateAsync(SelectedItem.ProductId);
                }
            }
            finally
            {
                IsLoading = false;
                OnPropertyChanged(nameof(CanSave));
                OnPropertyChanged(nameof(CanEdit));
            }
        }

        private async Task DeleteAsync()
        {
            if (IsLoading)
            {
                return;
            }

            if (SelectedItem == null)
            {
                _messageService.ShowWarning("삭제할 항목을 먼저 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"[{SelectedItem.ProductCode}] {SelectedItem.ProductName} 항목을 삭제하시겠습니까?",
                "삭제 확인");

            if (!confirmed)
            {
                return;
            }

            IsLoading = true;
            try
            {
                var result = await _apiClient.DeleteAsync($"{ApiRoutes.Products}/{SelectedItem.ProductId}");
                if (!result.Success || !result.Data)
                {
                    _messageService.ShowError(result.Message ?? "품목 삭제 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();
                SelectedItem = null;
                EditModel.Clear();
                EditModel.Uom = "EA";

                DrawingSearchKeyword = string.Empty;
                SelectedDrawingNo = string.Empty;
                SelectedDrawingCurrentRevisionId = null;
                DrawingOptions.Clear();

                IsCodeEditable = true;
                IsEditMode = true;

                _ = SearchDrawingsAsync(string.Empty);

                _messageService.ShowInfo("삭제되었습니다.");
            }
            finally
            {
                IsLoading = false;
                OnPropertyChanged(nameof(CanSave));
                OnPropertyChanged(nameof(CanEdit));
            }
        }

        private async Task CreateAsync()
        {
            var request = new ProductCreateRequest
            {
                ProductCode = EditModel.ProductCode,
                ProductName = EditModel.ProductName,
                Uom = EditModel.Uom,
                DrawingId = EditModel.DrawingId ?? 0,
                RoutingTemplateId = EditModel.RoutingTemplateId ?? 0,
                PanelWidthMm = EditModel.PanelWidthMm,
                PanelLengthMm = EditModel.PanelLengthMm,
                ProductSpec = EditModel.ProductSpec,
                CutQtyPerPanel = EditModel.CutQtyPerPanel,
                IsActive = EditModel.UseYn == "사용",
                Memo = EditModel.Memo
            };

            var result = await _apiClient.PostAsync<ProductCreateRequest, ProductDto>(ApiRoutes.Products, request);
            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "품목 저장 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            var createdItem = Items.FirstOrDefault(x => x.ProductCode == request.ProductCode);
            if (createdItem != null)
            {
                SelectedItem = createdItem;
                await LoadToEditModelAsync(createdItem);
            }
            else
            {
                SelectedItem = null;
                EditModel.Clear();
                EditModel.Uom = "EA";

                DrawingSearchKeyword = string.Empty;
                SelectedDrawingNo = string.Empty;
                SelectedDrawingCurrentRevisionId = null;
                DrawingOptions.Clear();

                IsCodeEditable = true;
                IsEditMode = true;

                _ = SearchDrawingsAsync(string.Empty);
            }

            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long productId)
        {
            var request = new ProductUpdateRequest
            {
                ProductName = EditModel.ProductName,
                Uom = EditModel.Uom,
                DrawingId = EditModel.DrawingId ?? 0,
                RoutingTemplateId = EditModel.RoutingTemplateId ?? 0,
                PanelWidthMm = EditModel.PanelWidthMm,
                PanelLengthMm = EditModel.PanelLengthMm,
                ProductSpec = EditModel.ProductSpec,
                CutQtyPerPanel = EditModel.CutQtyPerPanel,
                IsActive = EditModel.UseYn == "사용",
                Memo = EditModel.Memo
            };

            var result = await _apiClient.PatchAsync<ProductUpdateRequest, ProductDto>(
                $"{ApiRoutes.Products}/{productId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "품목 수정 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();

            var updatedItem = Items.FirstOrDefault(x => x.ProductId == productId);
            if (updatedItem != null)
            {
                SelectedItem = updatedItem;
                await LoadToEditModelAsync(updatedItem);
            }
            else
            {
                await LoadToEditModelAsync(result.Data);
            }

            IsCodeEditable = false;
            IsEditMode = false;
            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task LoadToEditModelAsync(ProductDto? item)
        {
            if (item == null)
            {
                EditModel.Clear();
                EditModel.Uom = "EA";

                DrawingSearchKeyword = string.Empty;
                SelectedDrawingNo = string.Empty;
                SelectedDrawingCurrentRevisionId = null;
                DrawingOptions.Clear();

                IsCodeEditable = true;
                IsEditMode = true;

                _ = SearchDrawingsAsync(string.Empty);
                return;
            }

            EditModel.LoadFromDto(item);
            IsCodeEditable = false;
            IsEditMode = false;

            // 상세 선택 시 검색어는 비우고, 표시용 도면번호만 먼저 세팅
            DrawingSearchKeyword = string.Empty;
            SelectedDrawingNo = item.DrawingNo ?? string.Empty;
            SelectedDrawingCurrentRevisionId = null;
            DrawingOptions.Clear();

            // current_revision_id 포함 상세 도면정보 재조회
            await LoadSelectedDrawingAsync(item.DrawingId);
        }

        private async Task LoadSelectedDrawingAsync(long drawingId)
        {
            if (drawingId <= 0)
            {
                SelectedDrawingNo = string.Empty;
                SelectedDrawingCurrentRevisionId = null;
                return;
            }

            var result = await _apiClient.GetAsync<DrawingDto>($"{ApiRoutes.Drawings}/{drawingId}");
            if (!result.Success || result.Data == null)
            {
                SelectedDrawingNo = string.Empty;
                SelectedDrawingCurrentRevisionId = null;
                return;
            }

            SelectedDrawingNo = result.Data.DrawingNo ?? string.Empty;
            SelectedDrawingCurrentRevisionId = result.Data.CurrentRevisionId;

            DrawingOptions.Clear();
            DrawingOptions.Add(result.Data);
        }

        public void SelectDrawing(DrawingDto? drawing)
        {
            if (drawing == null)
            {
                EditModel.DrawingId = null;
                SelectedDrawingNo = string.Empty;
                SelectedDrawingCurrentRevisionId = null;
                return;
            }

            EditModel.DrawingId = drawing.DrawingId;
            SelectedDrawingNo = drawing.DrawingNo ?? string.Empty;
            SelectedDrawingCurrentRevisionId = drawing.CurrentRevisionId;
            DrawingSearchKeyword = drawing.DrawingNo ?? string.Empty;
        }

        private async Task ViewDrawingAsync()
        {
            if (!EditModel.DrawingId.HasValue || EditModel.DrawingId.Value <= 0)
            {
                _messageService.ShowWarning("도면을 먼저 선택하세요.");
                return;
            }

            IsLoading = true;
            LoadingMessage = "파일 여는 중...";
            await Task.Yield();

            try
            {
                await _drawingViewer.OpenCurrentDrawingAsync(EditModel.DrawingId.Value);
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private bool ValidateForSave()
        {
            if (SelectedItem == null && string.IsNullOrWhiteSpace(EditModel.ProductCode))
            {
                _messageService.ShowWarning("품목코드는 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.ProductName))
            {
                _messageService.ShowWarning("품목명은 필수입니다.");
                return false;
            }

            if (EditModel.Uom != "EA" && EditModel.Uom != "Roll")
            {
                _messageService.ShowWarning("단위는 EA 또는 Roll만 선택할 수 있습니다.");
                return false;
            }

            if (!EditModel.DrawingId.HasValue || EditModel.DrawingId.Value <= 0)
            {
                _messageService.ShowWarning("도면을 선택하세요.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(SelectedDrawingNo))
            {
                _messageService.ShowWarning("도면번호를 확인하세요.");
                return false;
            }

            if (!EditModel.RoutingTemplateId.HasValue || EditModel.RoutingTemplateId.Value <= 0)
            {
                _messageService.ShowWarning("라우팅을 선택하세요.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.ProductCode = (EditModel.ProductCode ?? string.Empty).Trim().ToUpperInvariant();
            EditModel.ProductName = (EditModel.ProductName ?? string.Empty).Trim();
            EditModel.Uom = (EditModel.Uom ?? string.Empty).Trim();
            EditModel.ProductSpec = string.IsNullOrWhiteSpace(EditModel.ProductSpec) ? null : EditModel.ProductSpec.Trim();
            EditModel.Memo = string.IsNullOrWhiteSpace(EditModel.Memo) ? null : EditModel.Memo.Trim();
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

            return $"{ApiRoutes.Products}?{string.Join("&", queryParts)}";
        }

        public void LoadBulkRows(IEnumerable<ProductBulkUploadRowModel> rows, string filePath)
        {
            BulkRows.Clear();

            foreach (var row in rows.OrderBy(x => x.RowNumber))
            {
                row.ClearValidation();
                BulkRows.Add(row);
            }

            BulkFilePath = filePath;
            BulkSummaryText = $"불러온 건수: {BulkRows.Count}건";
        }

        private void ClearBulkRows()
        {
            BulkRows.Clear();
            BulkFilePath = string.Empty;
            BulkSummaryText = "대기 중";
        }

        private async Task DownloadTemplateAsync()
        {
            var dialog = new SaveFileDialog
            {
                Title = "품목 업로드 템플릿 저장",
                Filter = "Excel Files (*.xlsx)|*.xlsx",
                FileName = "product_upload_template.xlsx",
                DefaultExt = ".xlsx"
            };

            if (dialog.ShowDialog() != true)
            {
                return;
            }

            IsLoading = true;
            LoadingMessage = "템플릿 생성 중...";
            await Task.Yield();

            try
            {
                var targetPath = dialog.FileName;

                await Task.Run(() =>
                {
                    using var workbook = new XLWorkbook();
                    var worksheet = workbook.Worksheets.Add("Products");

                    worksheet.Cell(1, 1).Value = "product_code";
                    worksheet.Cell(1, 2).Value = "product_name";
                    worksheet.Cell(1, 3).Value = "uom";
                    worksheet.Cell(1, 4).Value = "drawing_no";
                    worksheet.Cell(1, 5).Value = "template_code";
                    worksheet.Cell(1, 6).Value = "panel_width_mm";
                    worksheet.Cell(1, 7).Value = "panel_length_mm";
                    worksheet.Cell(1, 8).Value = "product_spec";
                    worksheet.Cell(1, 9).Value = "cut_qty_per_panel";
                    worksheet.Cell(1, 10).Value = "is_active";
                    worksheet.Cell(1, 11).Value = "memo";

                    worksheet.Cell(2, 1).Value = "P-001";
                    worksheet.Cell(2, 2).Value = "샘플품목";
                    worksheet.Cell(2, 3).Value = "EA";
                    worksheet.Cell(2, 4).Value = "DWG-001";
                    worksheet.Cell(2, 5).Value = "RT-001";
                    worksheet.Cell(2, 6).Value = 100;
                    worksheet.Cell(2, 7).Value = 200;
                    worksheet.Cell(2, 8).Value = "SPEC";
                    worksheet.Cell(2, 9).Value = 2;
                    worksheet.Cell(2, 10).Value = true;
                    worksheet.Cell(2, 11).Value = "비고";

                    worksheet.Columns().AdjustToContents();
                    workbook.SaveAs(targetPath);
                });

                _messageService.ShowInfo("템플릿이 저장되었습니다.");
            }
            catch (Exception ex)
            {
                _messageService.ShowError($"템플릿 생성 중 오류가 발생했습니다.\n{ex.Message}");
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private async Task SelectBulkFileAsync()
        {
            var dialog = new OpenFileDialog
            {
                Title = "품목 업로드 파일 선택",
                Filter = "Excel Files (*.xlsx)|*.xlsx",
                Multiselect = false
            };

            if (dialog.ShowDialog() != true)
            {
                return;
            }

            IsLoading = true;
            LoadingMessage = "엑셀 파일 읽는 중...";
            await Task.Yield();

            try
            {
                var selectedPath = dialog.FileName;
                var rows = await Task.Run(() => ProductBulkExcelParser.Parse(selectedPath));
                LoadBulkRows(rows, selectedPath);
                NormalizeBulkRows();
                ValidateBulkRows();
            }
            catch (Exception ex)
            {
                BulkRows.Clear();
                BulkFilePath = string.Empty;
                BulkSummaryText = "대기 중";
                _messageService.ShowError($"엑셀 파일을 읽는 중 오류가 발생했습니다.\n{ex.Message}");
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private async Task UploadBulkAsync()
        {
            if (IsLoading)
            {
                return;
            }

            NormalizeBulkRows();
            ValidateBulkRows();

            var validRows = BulkRows.Where(x => x.IsValid).ToList();
            if (validRows.Count == 0)
            {
                _messageService.ShowWarning("업로드할 유효 데이터가 없습니다.");
                return;
            }

            IsLoading = true;
            LoadingMessage = "데이터 업로드 중...";
            await Task.Yield();

            try
            {
                var request = new ProductBulkCreateRequest
                {
                    Items = validRows.Select(x => new ProductBulkItemRequest
                    {
                        RowNumber = x.RowNumber,
                        ProductCode = x.ProductCode,
                        ProductName = x.ProductName,
                        Uom = x.Uom,
                        DrawingNo = x.DrawingNo,
                        TemplateCode = x.TemplateCode,
                        PanelWidthMm = x.PanelWidthMm,
                        PanelLengthMm = x.PanelLengthMm,
                        ProductSpec = x.ProductSpec,
                        CutQtyPerPanel = x.CutQtyPerPanel,
                        IsActive = x.IsActive,
                        Memo = x.Memo
                    }).ToList()
                };

                var result = await _apiClient.PostBulkAsync<ProductBulkCreateRequest, ProductBulkResultDto>(
                    ApiRoutes.ProductsBulk,
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "품목 벌크 업로드 중 오류가 발생했습니다.");
                    return;
                }

                ApplyBulkResult(result.Data);
                await SearchAsync();
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
                //OnPropertyChanged(nameof(CanSave));
                //OnPropertyChanged(nameof(CanEdit));
            }
        }

        private void NormalizeBulkRows()
        {
            foreach (var row in BulkRows)
            {
                row.ProductCode = (row.ProductCode ?? string.Empty).Trim().ToUpperInvariant();
                row.ProductName = (row.ProductName ?? string.Empty).Trim();
                row.Uom = (row.Uom ?? string.Empty).Trim().ToUpperInvariant();
                row.DrawingNo = (row.DrawingNo ?? string.Empty).Trim().ToUpperInvariant();
                row.TemplateCode = (row.TemplateCode ?? string.Empty).Trim().ToUpperInvariant();
                row.ProductSpec = string.IsNullOrWhiteSpace(row.ProductSpec) ? null : row.ProductSpec.Trim();
                row.Memo = string.IsNullOrWhiteSpace(row.Memo) ? null : row.Memo.Trim();
                row.ClearValidation();
            }
        }

        private void ValidateBulkRows()
        {
            var seenProductCodes = new Dictionary<string, int>();
            var seenDrawingNos = new Dictionary<string, int>();

            foreach (var row in BulkRows.OrderBy(x => x.RowNumber))
            {
                if (string.IsNullOrWhiteSpace(row.ProductCode))
                {
                    MarkBulkRowError(row, "품목코드는 필수입니다.");
                    continue;
                }

                if (string.IsNullOrWhiteSpace(row.ProductName))
                {
                    MarkBulkRowError(row, "품목명은 필수입니다.");
                    continue;
                }

                if (string.IsNullOrWhiteSpace(row.Uom))
                {
                    MarkBulkRowError(row, "단위는 필수입니다.");
                    continue;
                }

                if (string.IsNullOrWhiteSpace(row.DrawingNo))
                {
                    MarkBulkRowError(row, "도면번호는 필수입니다.");
                    continue;
                }

                if (string.IsNullOrWhiteSpace(row.TemplateCode))
                {
                    MarkBulkRowError(row, "라우팅코드는 필수입니다.");
                    continue;
                }

                if (seenProductCodes.TryGetValue(row.ProductCode, out var firstProductRow))
                {
                    MarkBulkRowError(row, $"중복 품목코드입니다. 첫 행: {firstProductRow}");
                    continue;
                }

                seenProductCodes[row.ProductCode] = row.RowNumber;

                if (seenDrawingNos.TryGetValue(row.DrawingNo, out var firstDrawingRow))
                {
                    MarkBulkRowError(row, $"중복 도면번호입니다. 첫 행: {firstDrawingRow}");
                    continue;
                }

                seenDrawingNos[row.DrawingNo] = row.RowNumber;
            }

            var invalidCount = BulkRows.Count(x => !x.IsValid);
            var validCount = BulkRows.Count - invalidCount;
            BulkSummaryText = $"검증 완료 - 전체: {BulkRows.Count}건 / 유효: {validCount}건 / 오류: {invalidCount}건";
        }

        private void ApplyBulkResult(ProductBulkResultDto result)
        {
            foreach (var row in BulkRows)
            {
                row.ClearValidation();
            }

            foreach (var error in result.Errors)
            {
                var target = BulkRows.FirstOrDefault(x => x.RowNumber == error.RowNumber);
                if (target != null)
                {
                    MarkBulkRowError(target, error.Message);
                }
            }

            BulkSummaryText = $"업로드 완료 - 성공: {result.SuccessCount}건 / 실패: {result.FailureCount}건 / 전체: {result.TotalCount}건";

            if (result.FailureCount == 0)
            {
                _messageService.ShowInfo("벌크 업로드가 완료되었습니다.");
            }
            else
            {
                _messageService.ShowWarning("일부 행에 오류가 있습니다. 결과를 확인하세요.");
            }
        }

        private void MarkBulkRowError(ProductBulkUploadRowModel row, string message)
        {
            row.IsValid = false;
            row.ErrorMessage = message;
        }

        private async Task SearchDrawingsAsync(string keyword)
        {
            _drawingSearchCts?.Cancel();
            _drawingSearchCts = new CancellationTokenSource();
            var token = _drawingSearchCts.Token;

            try
            {
                await Task.Delay(400, token);

                var q = (keyword ?? string.Empty).Trim();
                if (string.IsNullOrWhiteSpace(q))
                {
                    DrawingOptions.Clear();
                    return;
                }

                var route = $"{ApiRoutes.Drawings}?page=1&size=20&is_active=true&q={Uri.EscapeDataString(q)}";
                var result = await _apiClient.GetAsync<PagedResult<DrawingDto>>(route);

                if (token.IsCancellationRequested)
                {
                    return;
                }

                DrawingOptions.Clear();

                if (!result.Success || result.Data == null)
                {
                    return;
                }

                foreach (var item in result.Data.Items)
                {
                    DrawingOptions.Add(item);
                }
            }
            catch (TaskCanceledException)
            {
            }
        }
    }
}
