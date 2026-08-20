using ClosedXML.Excel;
using Mes.Wpf.Modules.Products.Dtos;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Mes.Wpf.Modules.Products.Services
{
    internal static class ProductBulkExcelParser
    {
        public static IReadOnlyList<ProductBulkUploadRowModel> Parse(string filePath)
        {
            if (!File.Exists(filePath))
            {
                throw new FileNotFoundException("선택한 파일을 찾을 수 없습니다.", filePath);
            }

            using var workbookStream = OpenReadOnlySharedStream(filePath);
            using var workbook = new XLWorkbook(workbookStream);
            var worksheet = workbook.Worksheets.First();
            var headerMap = BuildHeaderMap(worksheet);

            var productCodeColumn = GetRequiredColumnIndex(headerMap, "product_code");
            var productNameColumn = GetRequiredColumnIndex(headerMap, "product_name");
            var uomColumn = GetRequiredColumnIndex(headerMap, "uom");
            var drawingNoColumn = GetRequiredColumnIndex(headerMap, "drawing_no");
            var templateCodeColumn = GetRequiredColumnIndex(headerMap, "template_code");
            var panelWidthColumn = GetOptionalColumnIndex(headerMap, "panel_width_mm");
            var panelLengthColumn = GetOptionalColumnIndex(headerMap, "panel_length_mm");
            var productSpecColumn = GetOptionalColumnIndex(headerMap, "product_spec");
            var cutQtyColumn = GetOptionalColumnIndex(headerMap, "cut_qty_per_panel");
            var isActiveColumn = GetOptionalColumnIndex(headerMap, "is_active");
            var memoColumn = GetOptionalColumnIndex(headerMap, "memo");
            var rows = new List<ProductBulkUploadRowModel>();
            var lastRow = worksheet.LastRowUsed()?.RowNumber() ?? 0;

            for (var rowNumber = 2; rowNumber <= lastRow; rowNumber++)
            {
                var row = new ProductBulkUploadRowModel
                {
                    RowNumber = rowNumber,
                    ProductCode = worksheet.Cell(rowNumber, productCodeColumn).GetString(),
                    ProductName = worksheet.Cell(rowNumber, productNameColumn).GetString(),
                    Uom = worksheet.Cell(rowNumber, uomColumn).GetString(),
                    DrawingNo = worksheet.Cell(rowNumber, drawingNoColumn).GetString(),
                    TemplateCode = worksheet.Cell(rowNumber, templateCodeColumn).GetString(),
                    PanelWidthMm = GetNullableInt(worksheet, rowNumber, panelWidthColumn),
                    PanelLengthMm = GetNullableInt(worksheet, rowNumber, panelLengthColumn),
                    ProductSpec = GetNullableString(worksheet, rowNumber, productSpecColumn),
                    CutQtyPerPanel = GetNullableInt(worksheet, rowNumber, cutQtyColumn),
                    IsActive = GetNullableBool(worksheet, rowNumber, isActiveColumn) ?? true,
                    Memo = GetNullableString(worksheet, rowNumber, memoColumn)
                };

                if (!IsEmptyRow(row))
                {
                    rows.Add(row);
                }
            }

            return rows;
        }

        private static MemoryStream OpenReadOnlySharedStream(string filePath)
        {
            using var fileStream = new FileStream(
                filePath, FileMode.Open, FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            var workbookStream = new MemoryStream();
            fileStream.CopyTo(workbookStream);
            workbookStream.Position = 0;
            return workbookStream;
        }

        private static Dictionary<string, int> BuildHeaderMap(IXLWorksheet worksheet)
        {
            var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            var lastColumn = worksheet.LastColumnUsed()?.ColumnNumber() ?? 0;

            for (var column = 1; column <= lastColumn; column++)
            {
                var header = worksheet.Cell(1, column).GetString().Trim();
                if (!string.IsNullOrWhiteSpace(header) && !map.ContainsKey(header))
                {
                    map[header] = column;
                }
            }

            return map;
        }

        private static int GetRequiredColumnIndex(
            IReadOnlyDictionary<string, int> headerMap,
            string columnName)
        {
            if (!headerMap.TryGetValue(columnName, out var index))
            {
                throw new InvalidOperationException($"필수 컬럼이 없습니다: {columnName}");
            }

            return index;
        }

        private static int? GetOptionalColumnIndex(
            IReadOnlyDictionary<string, int> headerMap,
            string columnName)
        {
            return headerMap.TryGetValue(columnName, out var index) ? index : null;
        }

        private static int? GetNullableInt(IXLWorksheet worksheet, int rowNumber, int? columnNumber)
        {
            var text = GetCellText(worksheet, rowNumber, columnNumber)?.Trim();
            return int.TryParse(text, out var value) ? value : null;
        }

        private static bool? GetNullableBool(IXLWorksheet worksheet, int rowNumber, int? columnNumber)
        {
            var text = GetCellText(worksheet, rowNumber, columnNumber)?.Trim();
            if (string.IsNullOrWhiteSpace(text))
            {
                return null;
            }

            if (bool.TryParse(text, out var boolValue))
            {
                return boolValue;
            }

            return text switch
            {
                "사용" => true,
                "미사용" => false,
                _ => null
            };
        }

        private static string? GetNullableString(IXLWorksheet worksheet, int rowNumber, int? columnNumber)
        {
            var text = GetCellText(worksheet, rowNumber, columnNumber);
            return string.IsNullOrWhiteSpace(text) ? null : text;
        }

        private static string? GetCellText(IXLWorksheet worksheet, int rowNumber, int? columnNumber)
        {
            return columnNumber.HasValue
                ? worksheet.Cell(rowNumber, columnNumber.Value).GetString()
                : null;
        }

        private static bool IsEmptyRow(ProductBulkUploadRowModel row)
        {
            return string.IsNullOrWhiteSpace(row.ProductCode)
                && string.IsNullOrWhiteSpace(row.ProductName)
                && string.IsNullOrWhiteSpace(row.Uom)
                && string.IsNullOrWhiteSpace(row.DrawingNo)
                && string.IsNullOrWhiteSpace(row.TemplateCode)
                && !row.PanelWidthMm.HasValue
                && !row.PanelLengthMm.HasValue
                && string.IsNullOrWhiteSpace(row.ProductSpec)
                && !row.CutQtyPerPanel.HasValue
                && string.IsNullOrWhiteSpace(row.Memo);
        }
    }
}
