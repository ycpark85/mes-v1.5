using ClosedXML.Excel;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Common.ViewModels;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.Partners.Dtos;
using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.Partners.ViewModels
{
    public class PartnerPageViewModel : CrudPageViewModelBase<PartnerDto>
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private string _searchKeyword = string.Empty;
        private string _selectedUseYn = "사용";
        private string _bulkFilePath = string.Empty;
        private string _bulkSummaryText = "대기 중";
        private string _loadingMessage = "처리 중입니다...";

        public PartnerPageViewModel(IApiClient apiClient, IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            Items = new ObservableCollection<PartnerDto>();
            UseYnOptions = new ObservableCollection<string> { "사용", "미사용" };
            PartnerTypeOptions = new ObservableCollection<string> { "CUSTOMER", "VENDOR" };
            EditModel = new PartnerEditModel();

            SaveCommand = new AsyncRelayCommand(SaveAsync);
            DeleteCommand = new AsyncRelayCommand(DeleteAsync);

            BulkRows = new ObservableCollection<PartnerBulkUploadRowModel>();
            DownloadTemplateCommand = new AsyncRelayCommand(DownloadTemplateAsync);
            SelectBulkFileCommand = new AsyncRelayCommand(SelectBulkFileAsync);
            UploadBulkCommand = new AsyncRelayCommand(UploadBulkAsync);
            ClearBulkRowsCommand = new RelayCommand(ClearBulkRows);
        }

        public ObservableCollection<PartnerDto> Items { get; }

        public ObservableCollection<string> UseYnOptions { get; }

        public ObservableCollection<string> PartnerTypeOptions { get; }

        public PartnerEditModel EditModel { get; }

        public ObservableCollection<PartnerBulkUploadRowModel> BulkRows { get; }

        public AsyncRelayCommand SaveCommand { get; }

        public AsyncRelayCommand DeleteCommand { get; }

        public AsyncRelayCommand DownloadTemplateCommand { get; }

        public AsyncRelayCommand SelectBulkFileCommand { get; }

        public AsyncRelayCommand UploadBulkCommand { get; }

        public RelayCommand ClearBulkRowsCommand { get; }

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

        public async Task InitializeAsync()
        {
            await SearchAsync();
        }

        protected override async Task<bool> LoadListAsync()
        {
            var route = BuildListUrl();
            var result = await _apiClient.GetAsync<PartnerListDto>(route);

            if (!result.Success)
            {
                _messageService.ShowError(result.Message ?? "거래처 조회 중 오류가 발생했습니다.");
                return false;
            }

            Items.Clear();

            foreach (var item in result.Data?.Items ?? new List<PartnerDto>())
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
            ClearBulkRows();
        }

        protected override void New()
        {
            SelectedItem = null;
            EditModel.Clear();
        }

        protected override void OnSelectedItemChanged(PartnerDto? item)
        {
            if (item == null)
            {
                EditModel.Clear();
                return;
            }

            EditModel.LoadFromDto(item);
        }

        private async Task SaveAsync()
        {
            NormalizeEditModel();

            if (!ValidateForSave())
                return;

            IsLoading = true;
            LoadingMessage = EditModel.PartnerId.HasValue ? "거래처 수정 중..." : "거래처 저장 중...";
            await Task.Yield();

            try
            {
                if (EditModel.PartnerId.HasValue)
                {
                    await UpdateAsync(EditModel.PartnerId.Value);
                }
                else
                {
                    await CreateAsync();
                }
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private async Task CreateAsync()
        {
            var request = new PartnerCreateRequest
            {
                PartnerType = EditModel.PartnerType,
                Name = EditModel.Name,
                BusinessNo = EmptyToNull(EditModel.BusinessNo),
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PostAsync<PartnerCreateRequest, PartnerDto>(
                ApiRoutes.Partners,
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "거래처 저장 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();
            SelectedItem = null;
            EditModel.Clear();
            _messageService.ShowInfo("저장되었습니다.");
        }

        private async Task UpdateAsync(long partnerId)
        {
            var request = new PartnerUpdateRequest
            {
                PartnerType = EditModel.PartnerType,
                Name = EditModel.Name,
                BusinessNo = EmptyToNull(EditModel.BusinessNo),
                IsActive = EditModel.IsActive
            };

            var result = await _apiClient.PatchAsync<PartnerUpdateRequest, PartnerDto>(
                $"{ApiRoutes.Partners}/{partnerId}",
                request);

            if (!result.Success || result.Data == null)
            {
                _messageService.ShowError(result.Message ?? "거래처 수정 중 오류가 발생했습니다.");
                return;
            }

            await SearchAsync();
            SelectedItem = null;
            EditModel.Clear();
            _messageService.ShowInfo("수정되었습니다.");
        }

        private async Task DeleteAsync()
        {
            if (SelectedItem == null)
                return;

            if (!_messageService.Confirm("삭제하시겠습니까?"))
                return;

            IsLoading = true;
            LoadingMessage = "거래처 삭제 중...";
            await Task.Yield();

            try
            {
                var result = await _apiClient.DeleteAsync($"{ApiRoutes.Partners}/{SelectedItem.PartnerId}");

                if (!result.Success)
                {
                    _messageService.ShowError(result.Message ?? "거래처 삭제 중 오류가 발생했습니다.");
                    return;
                }

                await SearchAsync();
                SelectedItem = null;
                EditModel.Clear();

                _messageService.ShowInfo("삭제되었습니다.");
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        public void LoadBulkRows(IEnumerable<PartnerBulkUploadRowModel> rows, string filePath)
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
                Title = "거래처 업로드 템플릿 저장",
                Filter = "Excel Files (*.xlsx)|*.xlsx",
                FileName = "partner_upload_template.xlsx",
                DefaultExt = ".xlsx"
            };

            if (dialog.ShowDialog() != true)
                return;

            IsLoading = true;
            LoadingMessage = "템플릿 생성 중...";
            await Task.Yield();

            try
            {
                var targetPath = dialog.FileName;

                await Task.Run(() =>
                {
                    using var workbook = new XLWorkbook();
                    var worksheet = workbook.Worksheets.Add("Partners");

                    worksheet.Cell(1, 1).Value = "거래처구분";
                    worksheet.Cell(1, 2).Value = "거래처명";
                    worksheet.Cell(1, 3).Value = "사업자번호";
                    worksheet.Cell(1, 4).Value = "사용여부";

                    worksheet.Cell(2, 1).Value = "CUSTOMER";
                    worksheet.Cell(2, 2).Value = "샘플거래처";
                    worksheet.Cell(2, 3).Value = "123-45-67890";
                    worksheet.Cell(2, 4).Value = "사용";

                    worksheet.Range(1, 1, 1, 4).Style.Font.Bold = true;
                    worksheet.Columns().AdjustToContents();

                    workbook.SaveAs(targetPath);
                });

                _messageService.ShowInfo("템플릿 파일이 저장되었습니다.");
            }
            catch (Exception ex)
            {
                _messageService.ShowError($"템플릿 저장 중 오류가 발생했습니다.\n{ex.Message}");
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
                Title = "거래처 엑셀 파일 선택",
                Filter = "Excel Files (*.xlsx;*.xls)|*.xlsx;*.xls",
                Multiselect = false,
                CheckFileExists = true
            };

            if (dialog.ShowDialog() != true)
                return;

            IsLoading = true;
            LoadingMessage = "엑셀 파일 읽는 중...";
            await Task.Yield();

            try
            {
                var selectedPath = dialog.FileName;

                var rows = await Task.Run(() =>
                {
                    var tempPath = CopyToTempFile(selectedPath);
                    try
                    {
                        return ParseBulkRowsFromExcel(tempPath).ToList();
                    }
                    finally
                    {
                        TryDeleteTempFile(tempPath);
                    }
                });

                LoadBulkRows(rows, selectedPath);
                _messageService.ShowInfo($"엑셀 파일을 불러왔습니다. ({BulkRows.Count}건)");
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
                var request = new PartnerBulkCreateRequest
                {
                    Items = validRows.Select(x => new PartnerBulkItemRequest
                    {
                        RowNumber = x.RowNumber,
                        PartnerType = x.PartnerType,
                        Name = x.Name,
                        BusinessNo = x.BusinessNo,
                        IsActive = x.IsActive
                    }).ToList()
                };

                var result = await _apiClient.PostBulkAsync<PartnerBulkCreateRequest, PartnerBulkCreateResultDto>(
                    ApiRoutes.PartnersBulk,
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "거래처 벌크 업로드 중 오류가 발생했습니다.");
                    return;
                }

                ApplyBulkResult(result.Data);
                await SearchAsync();

                _messageService.ShowInfo(
                    $"업로드 완료\n성공: {result.Data.SuccessCount}건\n실패: {result.Data.FailureCount}건");
            }
            finally
            {
                IsLoading = false;
                LoadingMessage = "처리 중입니다...";
            }
        }

        private void NormalizeBulkRows()
        {
            foreach (var row in BulkRows)
            {
                row.PartnerType = (row.PartnerType ?? "CUSTOMER").Trim().ToUpperInvariant();
                row.Name = (row.Name ?? string.Empty).Trim();
                row.BusinessNo = (row.BusinessNo ?? string.Empty).Trim().Replace("-", "");
                row.ClearValidation();
            }
        }

        private void ValidateBulkRows()
        {
            var seenBusinessNos = new Dictionary<string, int>();

            foreach (var row in BulkRows.OrderBy(x => x.RowNumber))
            {
                if (string.IsNullOrWhiteSpace(row.Name))
                {
                    MarkBulkRowError(row, "거래처명은 필수입니다.");
                    continue;
                }

                if (string.IsNullOrWhiteSpace(row.PartnerType))
                {
                    MarkBulkRowError(row, "거래처구분은 필수입니다.");
                    continue;
                }

                if (row.PartnerType != "CUSTOMER" && row.PartnerType != "VENDOR")
                {
                    MarkBulkRowError(row, "거래처구분은 CUSTOMER 또는 VENDOR 여야 합니다.");
                    continue;
                }

                if (string.IsNullOrWhiteSpace(row.BusinessNo))
                {
                    MarkBulkRowError(row, "사업자번호는 필수입니다.");
                    continue;
                }

                if (seenBusinessNos.TryGetValue(row.BusinessNo, out var firstRowNumber))
                {
                    MarkBulkRowError(row, $"중복 사업자번호입니다. 첫 행: {firstRowNumber}");
                    continue;
                }

                seenBusinessNos[row.BusinessNo] = row.RowNumber;
            }

            var invalidCount = BulkRows.Count(x => !x.IsValid);
            var validCount = BulkRows.Count - invalidCount;
            BulkSummaryText = $"검증 완료 - 전체: {BulkRows.Count}건 / 유효: {validCount}건 / 오류: {invalidCount}건";
        }

        private void ApplyBulkResult(PartnerBulkCreateResultDto result)
        {
            foreach (var row in BulkRows)
            {
                row.ClearValidation();
            }

            foreach (var error in result.Errors)
            {
                var target = BulkRows.FirstOrDefault(x => x.RowNumber == error.RowNumber);
                if (target == null)
                    continue;

                target.IsValid = false;

                if (string.IsNullOrWhiteSpace(target.ErrorMessage))
                    target.ErrorMessage = $"{error.Field}: {error.Message}";
                else
                    target.ErrorMessage += $"\n{error.Field}: {error.Message}";
            }

            BulkSummaryText = $"업로드 결과 - 전체: {result.TotalCount}건 / 성공: {result.SuccessCount}건 / 실패: {result.FailureCount}건";
        }

        private void MarkBulkRowError(PartnerBulkUploadRowModel row, string message)
        {
            row.IsValid = false;
            row.ErrorMessage = message;
        }

        private IEnumerable<PartnerBulkUploadRowModel> ParseBulkRowsFromExcel(string filePath)
        {
            if (!File.Exists(filePath))
                throw new FileNotFoundException("선택한 파일을 찾을 수 없습니다.", filePath);

            using var workbook = new XLWorkbook(filePath);
            var worksheet = workbook.Worksheets.First();

            var headerMap = BuildHeaderMap(worksheet);

            var partnerTypeColumn = GetRequiredColumnIndex(headerMap, "partner_type");
            var nameColumn = GetRequiredColumnIndex(headerMap, "name");
            var businessNoColumn = GetRequiredColumnIndex(headerMap, "business_no");
            var isActiveColumn = GetOptionalColumnIndex(headerMap, "is_active");

            var rows = new List<PartnerBulkUploadRowModel>();
            var lastRow = worksheet.LastRowUsed()?.RowNumber() ?? 0;

            for (var rowNumber = 2; rowNumber <= lastRow; rowNumber++)
            {
                var partnerType = ReadCellString(worksheet, rowNumber, partnerTypeColumn);
                var name = ReadCellString(worksheet, rowNumber, nameColumn);
                var businessNo = ReadCellString(worksheet, rowNumber, businessNoColumn);
                var isActiveText = isActiveColumn.HasValue
                    ? ReadCellString(worksheet, rowNumber, isActiveColumn.Value)
                    : string.Empty;

                if (string.IsNullOrWhiteSpace(partnerType) &&
                    string.IsNullOrWhiteSpace(name) &&
                    string.IsNullOrWhiteSpace(businessNo) &&
                    string.IsNullOrWhiteSpace(isActiveText))
                {
                    continue;
                }

                rows.Add(new PartnerBulkUploadRowModel
                {
                    RowNumber = rowNumber,
                    PartnerType = string.IsNullOrWhiteSpace(partnerType) ? "CUSTOMER" : partnerType,
                    Name = name,
                    BusinessNo = businessNo,
                    IsActive = ParseIsActive(isActiveText),
                    IsValid = true,
                    ErrorMessage = string.Empty
                });
            }

            return rows;
        }

        private Dictionary<string, int> BuildHeaderMap(IXLWorksheet worksheet)
        {
            var map = new Dictionary<string, int>();
            var headerRow = worksheet.Row(1);
            var lastColumn = worksheet.LastColumnUsed()?.ColumnNumber() ?? 0;

            for (var column = 1; column <= lastColumn; column++)
            {
                var rawHeader = headerRow.Cell(column).GetString().Trim();
                if (string.IsNullOrWhiteSpace(rawHeader))
                    continue;

                var normalizedHeader = NormalizeExcelHeader(rawHeader);

                if (!map.ContainsKey(normalizedHeader))
                    map.Add(normalizedHeader, column);
            }

            return map;
        }

        private int GetRequiredColumnIndex(Dictionary<string, int> headerMap, string headerKey)
        {
            if (headerMap.TryGetValue(headerKey, out var columnIndex))
                return columnIndex;

            throw new InvalidOperationException($"엑셀 헤더를 찾을 수 없습니다: {headerKey}");
        }

        private int? GetOptionalColumnIndex(Dictionary<string, int> headerMap, string headerKey)
        {
            return headerMap.TryGetValue(headerKey, out var columnIndex) ? columnIndex : null;
        }

        private string NormalizeExcelHeader(string header)
        {
            var value = header.Trim().Replace(" ", string.Empty).Replace("_", string.Empty).ToUpperInvariant();

            return value switch
            {
                "거래처구분" => "partner_type",
                "구분" => "partner_type",
                "PARTNERTYPE" => "partner_type",

                "거래처명" => "name",
                "이름" => "name",
                "NAME" => "name",

                "사업자번호" => "business_no",
                "BUSINESSNO" => "business_no",

                "사용여부" => "is_active",
                "사용" => "is_active",
                "ISACTIVE" => "is_active",

                _ => value
            };
        }

        private string ReadCellString(IXLWorksheet worksheet, int rowNumber, int columnNumber)
        {
            return worksheet.Cell(rowNumber, columnNumber).GetString().Trim();
        }

        private bool ParseIsActive(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
                return true;

            var normalized = value.Trim().ToUpperInvariant();

            return normalized switch
            {
                "Y" => true,
                "YES" => true,
                "TRUE" => true,
                "1" => true,
                "사용" => true,

                "N" => false,
                "NO" => false,
                "FALSE" => false,
                "0" => false,
                "미사용" => false,

                _ => true
            };
        }

        private bool ValidateForSave()
        {
            if (string.IsNullOrWhiteSpace(EditModel.Name))
            {
                _messageService.ShowWarning("거래처명은 필수입니다.");
                return false;
            }

            if (string.IsNullOrWhiteSpace(EditModel.PartnerType))
            {
                _messageService.ShowWarning("거래처구분은 필수입니다.");
                return false;
            }

            if (EditModel.PartnerType != "CUSTOMER" && EditModel.PartnerType != "VENDOR")
            {
                _messageService.ShowWarning("거래처구분은 CUSTOMER 또는 VENDOR 여야 합니다.");
                return false;
            }

            return true;
        }

        private void NormalizeEditModel()
        {
            EditModel.PartnerType = (EditModel.PartnerType ?? "CUSTOMER").Trim().ToUpperInvariant();
            EditModel.Name = (EditModel.Name ?? string.Empty).Trim();
            EditModel.BusinessNo = EditModel.BusinessNo?.Trim();
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

            return $"{ApiRoutes.Partners}?{string.Join("&", queryParts)}";
        }

        private static string? EmptyToNull(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static string CopyToTempFile(string sourcePath)
        {
            var extension = Path.GetExtension(sourcePath);
            var tempPath = Path.Combine(Path.GetTempPath(), $"partner-upload-{Guid.NewGuid():N}{extension}");
            File.Copy(sourcePath, tempPath, true);
            return tempPath;
        }

        private static void TryDeleteTempFile(string tempPath)
        {
            try
            {
                if (File.Exists(tempPath))
                    File.Delete(tempPath);
            }
            catch
            {
            }
        }
    }
}
