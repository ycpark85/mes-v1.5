using ClosedXML.Excel;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.OrderLines.Dtos;
using Mes.Wpf.Views.Shell;
using Microsoft.Win32;
using System;
using System.Windows;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Linq;
using System.Threading.Tasks;

namespace Mes.Wpf.Modules.OrderLines.ViewModels
{
    public class OrderLineBulkImportPageViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly Func<object?>? _createListPage;

        private bool _isLoading;
        private string _selectedFilePath = string.Empty;
        private OrderLineBulkValidateResultDto? _validationResult;
        private OrderLineBulkCommitResultDto? _commitResult;
        private OrderLineBulkValidateRowDto? _selectedValidationRow;

        public OrderLineBulkImportPageViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            Func<object?>? createListPage = null)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _createListPage = createListPage;

            SourceRows = new ObservableCollection<OrderLineBulkImportRowDto>();
            ValidationGroups = new ObservableCollection<OrderLineBulkValidateGroupDto>();
            FlatRows = new ObservableCollection<OrderLineBulkValidateRowDto>();

            SelectFileCommand = new RelayCommand(SelectFile);
            ValidateCommand = new AsyncRelayCommand(ValidateAsync);
            CommitCommand = new AsyncRelayCommand(CommitAsync);
            ResetCommand = new RelayCommand(Reset);
            RemoveSelectedRowCommand = new AsyncRelayCommand(RemoveSelectedRowAsync);
            RemoveErrorRowsCommand = new AsyncRelayCommand(RemoveErrorRowsAsync);
        }

        public ObservableCollection<OrderLineBulkImportRowDto> SourceRows { get; }
        public ObservableCollection<OrderLineBulkValidateGroupDto> ValidationGroups { get; }
        public ObservableCollection<OrderLineBulkValidateRowDto> FlatRows { get; }

        public RelayCommand SelectFileCommand { get; }
        public AsyncRelayCommand ValidateCommand { get; }
        public AsyncRelayCommand CommitCommand { get; }
        public RelayCommand ResetCommand { get; }
        public AsyncRelayCommand RemoveSelectedRowCommand { get; }
        public AsyncRelayCommand RemoveErrorRowsCommand { get; }

        public bool IsLoading
        {
            get => _isLoading;
            set => SetProperty(ref _isLoading, value);
        }

        public string SelectedFilePath
        {
            get => _selectedFilePath;
            set => SetProperty(ref _selectedFilePath, value);
        }

        public OrderLineBulkValidateRowDto? SelectedValidationRow
        {
            get => _selectedValidationRow;
            set => SetProperty(ref _selectedValidationRow, value);
        }

        public OrderLineBulkValidateResultDto? ValidationResult
        {
            get => _validationResult;
            set
            {
                if (SetProperty(ref _validationResult, value))
                {
                    OnPropertyChanged(nameof(TotalRowCount));
                    OnPropertyChanged(nameof(ReadyRowCount));
                    OnPropertyChanged(nameof(ReviewRowCount));
                    OnPropertyChanged(nameof(ErrorRowCount));
                    OnPropertyChanged(nameof(CanCommit));
                }
            }
        }

        public OrderLineBulkCommitResultDto? CommitResult
        {
            get => _commitResult;
            set => SetProperty(ref _commitResult, value);
        }

        public int TotalRowCount => ValidationResult?.TotalRowCount ?? 0;
        public int ReadyRowCount => ValidationResult?.ReadyRowCount ?? 0;
        public int ReviewRowCount => ValidationResult?.ReviewRowCount ?? 0;
        public int ErrorRowCount => ValidationResult?.ErrorRowCount ?? 0;

        public bool CanCommit =>
            ValidationGroups.Count > 0 &&
            ValidationGroups.All(x => x.CanCommit) &&
            FlatRows.All(x => x.Status != "ERROR");

        public Task InitializeAsync()
        {
            Reset();
            return Task.CompletedTask;
        }

        private void SelectFile()
        {
            var dialog = new OpenFileDialog
            {
                Filter = "Excel Files (*.xlsx)|*.xlsx|All Files (*.*)|*.*",
                Multiselect = false
            };

            if (dialog.ShowDialog() != true)
            {
                return;
            }

            SelectedFilePath = dialog.FileName;

            try
            {
                var rows = ReadRowsFromExcel(dialog.FileName);
                LoadRows(rows);

                _messageService.ShowInfo($"{SourceRows.Count}건을 불러왔습니다.");
            }
            catch (Exception ex)
            {
                _messageService.ShowError($"엑셀 파일 읽기 중 오류가 발생했습니다.\n{ex.Message}");
            }
        }

        public void LoadRows(ObservableCollection<OrderLineBulkImportRowDto> rows)
        {
            SourceRows.Clear();
            foreach (var row in rows)
            {
                NormalizeRow(row);
                SourceRows.Add(row);
            }
        }

        private async Task ValidateAsync()
        {
            if (SourceRows.Count == 0)
            {
                _messageService.ShowWarning("검증할 업로드 데이터가 없습니다.");
                return;
            }

            IsLoading = true;
            try
            {
                var request = new OrderLineBulkValidateRequest
                {
                    Items = new ObservableCollection<OrderLineBulkImportRowDto>(SourceRows)
                };

                var result = await _apiClient.PostBulkAsync<OrderLineBulkValidateRequest, OrderLineBulkValidateResultDto>(
                    ApiRoutes.OrderLinesBulkValidate,
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "벌크 검증 중 오류가 발생했습니다.");
                    return;
                }

                ValidationResult = result.Data;
                ValidationGroups.Clear();
                FlatRows.Clear();

                foreach (var group in result.Data.Groups)
                {
                    ValidationGroups.Add(group);
                    foreach (var row in group.Rows)
                    {
                        if (!row.CanApplyProductNameChange)
                        {
                            row.ApplyProductNameChange = false;
                        }

                        FlatRows.Add(row);
                    }
                }

                OnPropertyChanged(nameof(CanCommit));
                _messageService.ShowInfo("검증이 완료되었습니다.");
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task CommitAsync()
        {
            if (!CanCommit)
            {
                _messageService.ShowWarning("등록 가능한 상태가 아닙니다.");
                return;
            }

            var confirmed = _messageService.Confirm("검증 결과를 기준으로 일괄 등록하시겠습니까?", "벌크 등록");
            if (!confirmed)
            {
                return;
            }

            IsLoading = true;
            try
            {
                var request = new OrderLineBulkCommitRequest
                {
                    Items = new ObservableCollection<OrderLineBulkImportRowDto>(SourceRows),
                    RowChoices = new ObservableCollection<OrderLineBulkCommitRowChoiceDto>(
                        FlatRows
                            .Select(x => new OrderLineBulkCommitRowChoiceDto
                            {
                                RowNumber = x.RowNumber,
                                ExpectedProductId = x.ProductId,
                                ExpectedMappingId = x.MappingId,
                                ApplyProductNameChange = x.ApplyProductNameChange
                            }))
                };

                var result = await _apiClient.PostBulkAsync<OrderLineBulkCommitRequest, OrderLineBulkCommitResultDto>(
                    ApiRoutes.OrderLinesBulkCommit,
                    request);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "벌크 등록 중 오류가 발생했습니다.");
                    return;
                }

                CommitResult = result.Data;

                CommitResult = result.Data;
                ApplyCommitResultToRows(result.Data);

                if (result.Data.FailureGroupCount > 0)
                {
                    _messageService.ShowWarning(
                        $"일부 등록이 완료되었습니다.\n성공 {result.Data.SuccessGroupCount}건 / 실패 {result.Data.FailureGroupCount}건\n\n성공한 행은 목록에서 제거했고, 실패한 행만 남겨두었습니다.");
                    return;
                }

                _messageService.ShowInfo("벌크 등록이 완료되었습니다.");

                var nextPage = _createListPage?.Invoke();
                if (nextPage != null && Application.Current.MainWindow is MainWindow mainWindow)
                {
                    mainWindow.MainContent.Content = nextPage;
                }
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void ApplyCommitResultToRows(OrderLineBulkCommitResultDto commitResult)
        {
            var successOrderNos = commitResult.Groups
                .Where(x => string.Equals(x.Status, "SUCCESS", StringComparison.OrdinalIgnoreCase))
                .Select(x => (x.ErpOrderNo ?? string.Empty).Trim())
                .Where(x => !string.IsNullOrWhiteSpace(x))
                .ToHashSet(StringComparer.OrdinalIgnoreCase);

            if (successOrderNos.Count == 0)
            {
                return;
            }

            foreach (var row in SourceRows
                .Where(x => successOrderNos.Contains((x.ErpOrderNo ?? string.Empty).Trim()))
                .ToList())
            {
                SourceRows.Remove(row);
            }

            foreach (var row in FlatRows
                .Where(x => successOrderNos.Contains((x.ErpOrderNo ?? string.Empty).Trim()))
                .ToList())
            {
                FlatRows.Remove(row);
            }

            foreach (var group in ValidationGroups
                .Where(x => successOrderNos.Contains((x.ErpOrderNo ?? string.Empty).Trim()))
                .ToList())
            {
                ValidationGroups.Remove(group);
            }

            if (ValidationResult != null)
            {
                foreach (var group in ValidationResult.Groups
                    .Where(x => successOrderNos.Contains((x.ErpOrderNo ?? string.Empty).Trim()))
                    .ToList())
                {
                    ValidationResult.Groups.Remove(group);
                }

                RefreshValidationSummary();
            }

            OnPropertyChanged(nameof(CanCommit));
        }

        private void RefreshValidationSummary()
        {
            if (ValidationResult == null)
            {
                OnPropertyChanged(nameof(CanCommit));
                return;
            }

            ValidationResult.TotalRowCount = FlatRows.Count;
            ValidationResult.ReadyRowCount = FlatRows.Count(x => x.Status == "READY");
            ValidationResult.ReviewRowCount = FlatRows.Count(x => x.Status == "REVIEW");
            ValidationResult.ErrorRowCount = FlatRows.Count(x => x.Status == "ERROR");

            OnPropertyChanged(nameof(TotalRowCount));
            OnPropertyChanged(nameof(ReadyRowCount));
            OnPropertyChanged(nameof(ReviewRowCount));
            OnPropertyChanged(nameof(ErrorRowCount));
            OnPropertyChanged(nameof(CanCommit));
        }

        private async Task RemoveSelectedRowAsync()
        {
            if (SelectedValidationRow == null)
            {
                _messageService.ShowWarning("삭제할 행을 선택하세요.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"선택한 행을 삭제하시겠습니까?\n\n행번호: {SelectedValidationRow.RowNumber}\n주문번호: {SelectedValidationRow.ErpOrderNo}\n품목코드: {SelectedValidationRow.ProductCode}",
                "업로드 행 삭제");

            if (!confirmed)
            {
                return;
            }

            await RemoveRowsAndRevalidateAsync(new[] { SelectedValidationRow.RowNumber });
        }

        private async Task RemoveErrorRowsAsync()
        {
            var errorRowNumbers = FlatRows
                .Where(x => x.Status == "ERROR")
                .Select(x => x.RowNumber)
                .ToList();

            if (errorRowNumbers.Count == 0)
            {
                _messageService.ShowInfo("삭제할 오류 행이 없습니다.");
                return;
            }

            var confirmed = _messageService.Confirm(
                $"오류 행 {errorRowNumbers.Count}건을 모두 삭제하시겠습니까?",
                "오류 행 전체 삭제");

            if (!confirmed)
            {
                return;
            }

            await RemoveRowsAndRevalidateAsync(errorRowNumbers);
        }

        private async Task RemoveRowsAndRevalidateAsync(IEnumerable<int> rowNumbers)
        {
            var rowNumberSet = rowNumbers.ToHashSet();

            foreach (var row in SourceRows.Where(x => rowNumberSet.Contains(x.RowNumber)).ToList())
            {
                SourceRows.Remove(row);
            }

            SelectedValidationRow = null;

            if (SourceRows.Count == 0)
            {
                ValidationGroups.Clear();
                FlatRows.Clear();
                ValidationResult = null;
                CommitResult = null;
                OnPropertyChanged(nameof(CanCommit));
                _messageService.ShowInfo("업로드 데이터가 모두 삭제되었습니다.");
                return;
            }

            await ValidateAsync();
        }

        private void Reset()
        {
            SelectedFilePath = string.Empty;
            SourceRows.Clear();
            ValidationGroups.Clear();
            FlatRows.Clear();
            SelectedValidationRow = null;
            ValidationResult = null;
            CommitResult = null;
            OnPropertyChanged(nameof(CanCommit));
        }

        private static void NormalizeRow(OrderLineBulkImportRowDto row)
        {
            row.ErpOrderNo = row.ErpOrderNo?.Trim() ?? string.Empty;
            row.ProductCode = row.ProductCode?.Trim().ToUpperInvariant() ?? string.Empty;
            row.PartnerName = row.PartnerName?.Trim() ?? string.Empty;
            row.ErpProductDisplayName = row.ErpProductDisplayName?.Trim() ?? string.Empty;
            row.OrderQtyText = row.OrderQtyText?.Trim() ?? string.Empty;
            row.DueDateText = row.DueDateText?.Trim() ?? string.Empty;
            row.Remark = row.Remark?.Trim();
        }
        private ObservableCollection<OrderLineBulkImportRowDto> ReadRowsFromExcel(string filePath)
        {
            var rows = new ObservableCollection<OrderLineBulkImportRowDto>();

            using var workbook = new XLWorkbook(filePath);
            var worksheet = workbook.Worksheet(1);

            var lastRow = worksheet.LastRowUsed()?.RowNumber() ?? 0;
            if (lastRow < 2)
            {
                return rows;
            }

            for (var rowIndex = 2; rowIndex <= lastRow; rowIndex++)
            {
                var erpOrderNo = GetCellText(worksheet, rowIndex, 1);
                var productCode = GetCellText(worksheet, rowIndex, 2);
                var partnerName = GetCellText(worksheet, rowIndex, 3);
                var productDisplayName = GetCellText(worksheet, rowIndex, 4);
                var orderQtyText = GetCellText(worksheet, rowIndex, 5);
                var dueDateText = NormalizeDateText(GetCellText(worksheet, rowIndex, 9));
                var remark = GetCellText(worksheet, rowIndex, 12);

                if (string.IsNullOrWhiteSpace(erpOrderNo) &&
                    string.IsNullOrWhiteSpace(productCode) &&
                    string.IsNullOrWhiteSpace(partnerName) &&
                    string.IsNullOrWhiteSpace(productDisplayName) &&
                    string.IsNullOrWhiteSpace(orderQtyText))
                {
                    continue;
                }

                var dto = new OrderLineBulkImportRowDto
                {
                    RowNumber = rows.Count + 1,
                    ErpOrderNo = NormalizeOrderNo(erpOrderNo),
                    ProductCode = productCode?.Trim().ToUpperInvariant() ?? string.Empty,
                    PartnerName = partnerName?.Trim() ?? string.Empty,
                    ErpProductDisplayName = productDisplayName?.Trim() ?? string.Empty,
                    OrderQtyText = NormalizeQtyText(orderQtyText),
                    DueDateText = dueDateText,
                    Remark = string.IsNullOrWhiteSpace(remark) ? null : remark.Trim()
                };

                rows.Add(dto);
            }

            return rows;
        }

        private static string GetCellText(IXLWorksheet worksheet, int row, int col)
        {
            return worksheet.Cell(row, col).GetFormattedString()?.Trim() ?? string.Empty;
        }

        private static string NormalizeOrderNo(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            return value.Trim().Replace("  ", " ");
        }

        private static string NormalizeQtyText(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            return value.Trim().Replace(",", "");
        }

        private static string NormalizeDateText(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            value = value.Trim();

            if (DateTime.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.None, out var parsed))
            {
                return parsed.ToString("yyyy/MM/dd");
            }

            return value;
        }
    }
}
