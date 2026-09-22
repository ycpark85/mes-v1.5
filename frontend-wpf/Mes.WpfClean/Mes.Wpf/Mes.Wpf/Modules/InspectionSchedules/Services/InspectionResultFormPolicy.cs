using System.Collections.ObjectModel;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;

namespace Mes.Wpf.Modules.InspectionSchedules.Services;

public readonly record struct InspectionQuantities(
    int Good, int DefectShip, int Defect, int Uninspected,
    int StockShip, int ProductionShip, int StockIn, int Discard, int PriorSellable)
{
    public int Inspected => Good + DefectShip + Defect;
    public int Received => Inspected + Uninspected;
    public int Sellable => PriorSellable + Good + DefectShip;
    public int Disposal => Discard + Uninspected;
    public int Shipment => Math.Max(StockShip, 0) + Math.Max(ProductionShip, 0);
    public int ResidualStockIn => Sellable - ProductionShip - Discard;
    public bool HasNegative => new[] { Good, DefectShip, Defect, Uninspected, StockShip, ProductionShip, StockIn, Discard }.Any(q => q < 0);
}

public sealed record InspectionResultDraft
{
    public InspectionQuantities Quantities { get; init; }
    public bool IsPartial { get; init; }
    public DateTime? NextInspectionDate { get; init; }
    public string PartialReason { get; init; } = "";
    public string ShortageReason { get; init; } = "";
    public string Memo { get; init; } = "";
    public DateTimeOffset? ExpectedUpdatedAt { get; init; }
    public IReadOnlyList<InspectionResultDefectEditModel> Defects { get; init; } = Array.Empty<InspectionResultDefectEditModel>();
}

public sealed record InspectionSaveContext
{
    public bool LoadFailed { get; init; }
    public string SettlementError { get; init; } = "";
    public string StockError { get; init; } = "";
    public int AvailableStock { get; init; }
    public int OriginalOwnInventoryIn { get; init; }
    public int OriginalStockShip { get; init; }
    public int OriginalProductionShip { get; init; }
}

public static class InspectionResultFormPolicy
{
    public static string? Validate(InspectionResultDraft draft, InspectionSaveContext context)
    {
        var q = draft.Quantities;
        var inventoryChanges = !draft.ExpectedUpdatedAt.HasValue
            || q.Good + q.DefectShip - q.Discard != context.OriginalOwnInventoryIn
            || q.StockShip != context.OriginalStockShip || q.ProductionShip != context.OriginalProductionShip;
        if (context.LoadFailed || !string.IsNullOrWhiteSpace(context.SettlementError))
            return context.LoadFailed ? "조회에 실패했습니다. 창을 다시 열어주세요." : context.SettlementError;
        if (inventoryChanges && !string.IsNullOrWhiteSpace(context.StockError))
            return "재고 정합성 확인 필요: " + context.StockError;
        if (q.HasNegative)
            return "수량은 0 이상이어야 합니다. 출고·재고편입·폐기 배분을 확인해주세요.";
        if (q.Received <= 0)
            return "검수수량 또는 미검수수량을 입력해주세요.";
        if (q.ProductionShip + q.StockIn + q.Discard != q.Sellable)
            return "생산 출고수량 + 판매가능폐기 + 재고편입수량은 판매가능수량과 같아야 합니다.";
        if (inventoryChanges && q.StockShip > context.AvailableStock)
            return "재고 출고수량이 현재 재고수량을 초과할 수 없습니다.";
        if (draft.IsPartial && !draft.NextInspectionDate.HasValue)
            return "분할검수일 경우 다음 검수일자를 입력해주세요.";
        if (draft.IsPartial && string.IsNullOrWhiteSpace(draft.PartialReason))
            return "분할검수일 경우 사유/메모를 입력해주세요.";
        if (q.Defect > 0 && draft.Defects.Count == 0)
            return "불량수량이 있으면 불량내역을 등록해주세요.";
        if (draft.Defects.Any(x => !x.DefectTypeId.HasValue))
            return "불량유형을 입력해주세요.";
        return null;
    }

    public static InspectionResultUpsertRequest BuildRequest(InspectionResultDraft draft)
    {
        var q = draft.Quantities;
        return new InspectionResultUpsertRequest
        {
            GoodQty = q.Good, DefectShipQty = q.DefectShip, DefectQty = q.Defect,
            UninspectedQty = draft.IsPartial ? 0 : q.Uninspected,
            StockShipQty = q.StockShip, ResultShipQty = q.ProductionShip,
            StockInQty = q.StockIn, DiscardQty = q.Discard, IsPartial = draft.IsPartial,
            NextInspectionDate = draft.IsPartial ? draft.NextInspectionDate?.Date : null,
            PartialReason = draft.IsPartial ? draft.PartialReason.Trim() : null,
            ShortageReason = draft.IsPartial || string.IsNullOrWhiteSpace(draft.ShortageReason) ? null : draft.ShortageReason.Trim(),
            Memo = string.IsNullOrWhiteSpace(draft.Memo) ? null : draft.Memo.Trim(),
            ExpectedUpdatedAt = draft.ExpectedUpdatedAt,
            Defects = new ObservableCollection<InspectionResultDefectRequest>(draft.Defects.Select(defect => new InspectionResultDefectRequest
            {
                DefectTypeId = defect.DefectTypeId ?? 0, DefectQty = defect.DefectQty,
                Disposition = string.IsNullOrWhiteSpace(defect.Disposition) ? "NOT_SHIPPABLE" : defect.Disposition,
                Memo = string.IsNullOrWhiteSpace(defect.Memo) ? null : defect.Memo.Trim(),
                Attachments = new ObservableCollection<DefectAttachmentRequest>(defect.Attachments.Select(a => new DefectAttachmentRequest
                {
                    FileUri = a.FileUri, FileName = string.IsNullOrWhiteSpace(a.FileName) ? null : a.FileName,
                    MimeType = string.IsNullOrWhiteSpace(a.MimeType) ? null : a.MimeType,
                    Memo = string.IsNullOrWhiteSpace(a.Memo) ? null : a.Memo.Trim()
                }))
            }))
        };
    }

}
