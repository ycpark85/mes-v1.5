using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Net.Http;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;
using Mes.Wpf.Modules.InspectionSchedules.ViewModels;
using Mes.Wpf.Modules.InspectionSchedules.Services;
using Mes.Wpf.Infrastructure.Diagnostics;

var passed = 0;
void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
    passed++;
    Console.WriteLine("PASS: " + message);
}
static Task Save(InspectionResultWindowViewModel vm) =>
    (Task)typeof(InspectionResultWindowViewModel).GetMethod("SaveAsync", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(vm, null)!;

var api = DispatchProxy.Create<IApiClient, RegressionApi>();
var handler = (RegressionApi)(object)api;
var messages = new RegressionMessages();
var operationErrors = new List<Exception>();
async Task<InspectionResultWindowViewModel> Load(int plan = 535000, bool canEdit = true)
{
    var vm = new InspectionResultWindowViewModel(api, messages, canEdit: canEdit, reportError: operationErrors.Add);
    await vm.InitializeAsync(1, "LOT-TEST", "Product", "Customer",
        new DateTime(2026, 9, 9), plan, new DateTime(2026, 9, 10), 600000);
    return vm;
}
var vm = await Load();
Check(vm.StockShipQty == 0 && vm.ResultShipQty == 0,
    "new result starts with zero shipment even when the server suggests planned stock usage");
vm.GoodQty = 432000;
Check(vm.StockShipQty == 0 && vm.ResultShipQty == 0 && vm.StockInQty == 432000,
    "good quantity goes to stock until the operator enters a shipment");
vm.StockShipQty = 65000;
vm.ResultShipQty = 432000;
vm.IsPartial = true;
vm.DefectQty = 10456;
vm.Defects.Add(new() { DefectTypeId = 13, DefectCode = "A000", DefectQty = 0, Disposition = "NOT_SHIPPABLE" });
vm.NextInspectionDate = new DateTime(2026, 9, 10);
vm.PartialReason = "next round";
await Save(vm);
Check(handler.Request?.QuantityRuleVersion == 2 && handler.Request.StockShipQty + handler.Request.ResultShipQty == 497000,
    "split save posts the visible allocation and contract version");
Check(handler.Request is { IsPartial: true, GoodQty: 432000, DefectQty: 10456,
        StockShipQty: 65000, ResultShipQty: 432000, StockInQty: 0, DiscardQty: 0, UninspectedQty: 0 }
    && handler.Request.NextInspectionDate == new DateTime(2026, 9, 10)
    && handler.Request.PartialReason == "next round" && handler.Request.ShortageReason == null,
    "screenshot quantities survive selecting partial and saving the current round");
if (args.Length == 1)
    File.WriteAllText(args[0], JsonSerializer.Serialize(handler.Request, new JsonSerializerOptions { WriteIndented = true }));
vm.IsPartial = false;
vm.IsPartial = true;
Check(vm.IsShipmentInputEnabled && vm.StockShipQty == 65000 && vm.ResultShipQty == 432000 && vm.StockInQty == 0,
    "toggling partial off and on preserves shipment allocation");
var partialFirst = await Load();
partialFirst.IsPartial = true;
partialFirst.GoodQty = 432000;
partialFirst.NextInspectionDate = new DateTime(2026, 9, 10);
partialFirst.PartialReason = "next round";
handler.Request = null;
await Save(partialFirst);
Check(handler.Request is { IsPartial: true, StockShipQty: 0, ResultShipQty: 0, StockInQty: 432000 },
    "partial inspection can save all good quantity as stock without shipment");
vm.ResultShipQty = 400000;
vm.DiscardQty = 1000;
vm.GoodQty = 500000;
Check(vm.StockShipQty == 65000 && vm.ResultShipQty == 400000 && vm.DiscardQty == 1000 && vm.StockInQty == 99000,
    "manual shipment and disposal survive good quantity changes");
vm.GoodQty = 300000;
Check(vm.ResultShipQty == 400000 && vm.StockInQty == -101000,
    "invalid manual allocation stays visible instead of being silently clamped");
handler.Request = null;
await Save(vm);
Check(handler.Request == null, "negative residual is rejected before sending");

vm = await Load();
vm.GoodQty = 432000;
handler.Request = null;
var warningCountBeforeShortage = messages.Warnings.Count;
await Save(vm);
Check(handler.Request is { IsPartial: false, GoodQty: 432000, StockInQty: 432000,
        DefectQty: 0, UninspectedQty: 0, ShortageReason: null }
    && messages.Warnings.Count == warningCountBeforeShortage,
    "final inspection below the LOT plan saves actual quantities without a shortage reason or warning");
vm.GoodQty = 0;
handler.Request = null;
await Save(vm);
Check(handler.Request is null, "removing the LOT plan restriction still rejects zero processed quantity");

handler.Response.Result = new() { InspectionResultId = 641, GoodQty = 50000,
    UpdatedAt = DateTimeOffset.UtcNow, ShortageReason = "historical reason" };
handler.Response.Inventory = new() { CurrentStockQty = 0, PhysicalStockQty = 39500,
    ShipTargetQty = 51000, RemainingBeforeCurrentResultQty = 51000,
    PriorUnsettledSellableQty = 39500, CurrentResultResultShipQty = 50000, CurrentResultStockInQty = 39500 };
vm = await Load(51000);
Check(vm.StockInQty == 39500 && vm.ResultShipQty == 50000,
    "612: initialization preserves saved shipment and owned carry");
vm.GoodQty = 55000;
Check(vm.StockInQty == 44500 && vm.ResultShipQty == 50000, "612: edit adds only the changed quantity");
await Save(vm);
Check(handler.Request?.ExpectedUpdatedAt.HasValue == true, "edit submits concurrency version");
Check(handler.Request?.ShortageReason == "historical reason", "editing preserves a previously recorded shortage reason");

handler.Response = new()
{
    Result = new() { InspectionResultId = 642, GoodQty = 100000, UpdatedAt = DateTimeOffset.UtcNow },
    Inventory = new() { CurrentStockQty = 65000, ShipTargetQty = 150000,
        RemainingBeforeCurrentResultQty = 150000, CurrentResultStockShipQty = 20000,
        CurrentResultResultShipQty = 60000, CurrentResultStockInQty = 40000 }
};
vm = await Load(100000);
handler.Request = null;
await Save(vm);
Check(handler.Request is { StockShipQty: 20000, ResultShipQty: 60000, StockInQty: 40000 },
    "editing an existing result preserves both saved shipment quantities");

handler.Response = new()
{
    Inventory = new() { ShipTargetQty = 150000, RemainingBeforeCurrentResultQty = 150000 }
};
vm = await Load(150000);
vm.IsPartial = true;
vm.GoodQty = 100000;
vm.NextInspectionDate = new DateTime(2026, 9, 11);
vm.PartialReason = "inspect the remainder tomorrow";
handler.Request = null;
await Save(vm);
Check(handler.Request is { StockShipQty: 0, ResultShipQty: 0, StockInQty: 100000 },
    "round one saves 100000 good pieces to inventory without shipment");
handler.StockLotNo = "LOT-TEST";
handler.Response = new()
{
    Accumulated = new() { GoodQty = 100000, InspectedQty = 100000 },
    Inventory = new() { CurrentStockQty = 100000, PhysicalStockQty = 100000,
        ShipTargetQty = 150000, RemainingBeforeCurrentResultQty = 150000 }
};
vm = await Load(150000);
Check(vm.StockLots.Single().LotNo == "LOT-TEST" && vm.StockLots.Single().StockQty == 100000
    && vm.StockShipQty == 0 && vm.ResultShipQty == 0,
    "round two shows prior-round inventory without pre-filling shipment");
vm.GoodQty = 50000;
vm.StockShipQty = 100000;
vm.ResultShipQty = 50000;
handler.Request = null;
await Save(vm);
Check(handler.Request is { GoodQty: 50000, StockShipQty: 100000, ResultShipQty: 50000, StockInQty: 0 },
    "round two manually ships prior stock and new production without counting stock as new good quantity");
vm.ResultShipQty = 50001;
handler.Request = null;
await Save(vm);
Check(handler.Request == null, "production shipment exceeding the sellable balance cannot save");
vm.ResultShipQty = 0;
vm.StockShipQty = 100001;
await Save(vm);
Check(handler.Request == null, "manual stock shipment exceeding available stock cannot save");
vm.StockShipQty = 100000;
vm.ResultShipQty = 50000;
vm.RemainingBeforeCurrentResultQty = 140000;
var warningsBeforeOverShipment = messages.Warnings.Count;
await Save(vm);
Check(handler.Request is { StockShipQty: 100000, ResultShipQty: 50000, StockInQty: 0 }
    && messages.Warnings.Count == warningsBeforeOverShipment && vm.RemainingAfterCurrentQty == 0,
    "balanced stock and production shipments above the remaining target save without warnings");
vm.IsPartial = true;
vm.NextInspectionDate = new DateTime(2026, 9, 12);
vm.PartialReason = "remaining production";
handler.Request = null;
await Save(vm);
Check(handler.Request is { IsPartial: true, StockShipQty: 100000, ResultShipQty: 50000 },
    "partial inspection also accepts balanced shipments above the target");

handler.Response = new() { Inventory = new() { ShipTargetQty = 100, RemainingBeforeCurrentResultQty = 100 } };
vm = await Load(100);
vm.GoodQty = 120;
vm.ResultShipQty = 120;
handler.Request = null;
await Save(vm);
Check(handler.Request is { GoodQty: 120, ResultShipQty: 120, StockInQty: 0 }
    && vm.ShipTargetQty == 100 && vm.CurrentRoundShipQty == 120 && vm.RemainingAfterCurrentQty == 0,
    "all production can ship above the target without changing the target or hiding actual shipment");
handler.Response.Result = new() { InspectionResultId = 643, GoodQty = 120, UpdatedAt = DateTimeOffset.UtcNow };
handler.Response.Inventory = new() { ShipTargetQty = 100, RemainingBeforeCurrentResultQty = 0,
    CurrentResultResultShipQty = 120, CurrentResultStockInQty = 0 };
vm = await Load(100);
vm.GoodQty = 130;
vm.ResultShipQty = 130;
handler.Request = null;
await Save(vm);
Check(handler.Request is { GoodQty: 130, ResultShipQty: 130, StockInQty: 0, ExpectedUpdatedAt: not null },
    "an existing inspection can increase shipment even when the remaining target is zero");

handler.Response.Accumulated = null;
handler.Response.Result = null;
handler.Response.Inventory = new() { CurrentStockQty = 65000, PhysicalStockQty = 65000,
    ShipTargetQty = 0, RemainingBeforeCurrentResultQty = 0, CurrentResultStockShipQty = 0 };
vm = await Load();
vm.GoodQty = 600000;
Check(vm.StockShipQty == 0 && vm.ResultShipQty == 0 && vm.StockInQty == 600000,
    "stock replenishment keeps both shipment quantities at zero");
handler.OmitStockSnapshot = true;
vm = await Load();
vm.GoodQty = 600000;
handler.Request = null;
await Save(vm);
Check(handler.Request == null && !string.IsNullOrWhiteSpace(vm.StockError),
    "missing bundled stock from an old server is visible and prevents saving");

handler.OmitStockSnapshot = false;
handler.Response = new() { ScheduleStatus = "IN_PROGRESS", Inventory = new() { ShipTargetQty = 100, RemainingBeforeCurrentResultQty = 100 } };
vm = await Load(80);
vm.GoodQty = 80;
handler.PendingSave = new(TaskCreationOptions.RunContinuationsAsynchronously);
var saveCommand = (AsyncRelayCommand)vm.SaveCommand;
var countBefore = handler.PutCount;
var pending = saveCommand.ExecuteAsync();
await saveCommand.ExecuteAsync();
Check(vm.IsLoading && handler.PutCount == countBefore + 1, "save command prevents duplicate execution while pending");
handler.PendingSave.SetException(new IOException("PRIVATE simulated write failure"));
await pending;
Check(operationErrors.Count == 1 && !vm.IsLoading && saveCommand.CanExecute(null) && vm.GoodQty == 80,
    "unexpected save failure is reported and preserves editable quantities");
handler.PendingSave = null;
await saveCommand.ExecuteAsync();
Check(handler.PutCount == countBefore + 2 && !vm.IsLoading, "save can be retried after a failed operation");

handler.ThrowOnGet = true;
vm = await Load(80);
vm.GoodQty = 80;
handler.Request = null;
await ((AsyncRelayCommand)vm.SaveCommand).ExecuteAsync();
Check(handler.Request == null && operationErrors.Count == 2 && !vm.IsLoading,
    "unexpected load failure blocks saving a partial screen state");
handler.ThrowOnGet = false;
await vm.RefreshAsync();
vm.GoodQty = 80;
await ((AsyncRelayCommand)vm.SaveCommand).ExecuteAsync();
Check(handler.Request?.GoodQty == 80, "refresh after load failure restores normal saving");

var genericGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
var genericCount = 0;
var genericErrors = 0;
var generic = new AsyncRelayCommand<string>(async value => { genericCount++; await genericGate.Task; },
    value => value == "photo", _ => genericErrors++);
Check(!generic.CanExecute(42) && !generic.CanExecute(null), "typed asynchronous command rejects invalid parameters");
var genericPending = generic.ExecuteAsync("photo");
await generic.ExecuteAsync("photo");
genericGate.SetException(new IOException("PRIVATE file failure"));
await genericPending;
Check(genericCount == 1 && genericErrors == 1 && generic.CanExecute("photo"),
    "typed photo command reports failure and restores execution state");
var previousErrorHandler = AsyncCommandErrors.Handler;
try
{
    var routed = 0;
    AsyncCommandErrors.Handler = _ => routed++;
    await new AsyncRelayCommand(() => throw new IOException("PRIVATE default handler")).ExecuteAsync();
    Check(routed == 1, "commands without a local handler reach the application error boundary");
}
finally { AsyncCommandErrors.Handler = previousErrorHandler; }
var logEntry = UiErrorReporter.Describe(new IOException("PRIVATE user input and path"), "test-error-id");
Check(logEntry.Contains("test-error-id") && logEntry.Contains("IOException") && !logEntry.Contains("PRIVATE"),
    "diagnostic record contains identity and exception type but no raw exception message");

using (var cases = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "inspection_quantity_cases.json"))))
{
    foreach (var item in cases.RootElement.EnumerateArray())
    {
        int Q(string name) => item.GetProperty(name).GetInt32();
        var quantities = new InspectionQuantities(Q("good"), Q("defect_ship"), Q("defect"), Q("uninspected"),
            Q("stock_ship"), Q("production_ship"), Q("stock_in"), Q("discard"), Q("carry"));
        var draft = new InspectionResultDraft { Quantities = quantities, IsPartial = item.GetProperty("partial").GetBoolean(),
            NextInspectionDate = new DateTime(2026, 9, 15), PartialReason = "remaining", ShortageReason = "actual",
            Defects = Q("defect") > 0 ? new[] { new InspectionResultDefectEditModel { DefectTypeId = 1, DefectQty = Q("defect") } } : Array.Empty<InspectionResultDefectEditModel>() };
        var error = InspectionResultFormPolicy.Validate(draft, new() { AvailableStock = 1000000 });
        Check((error is null) == item.GetProperty("valid").GetBoolean(), "shared backend/WPF quantity case: " + item.GetProperty("name").GetString());
    }
}
var defectDraft = new InspectionResultDefectEditModel { DefectTypeId = 7, DefectQty = 2, Disposition = "", Memo = " note " };
defectDraft.Attachments.Add(new() { FileUri = "fixture.png", FileName = "", MimeType = "image/png", Memo = " photo " });
var mapped = InspectionResultFormPolicy.BuildRequest(new() { Quantities = new(10, 0, 2, 0, 0, 0, 10, 0, 0),
    IsPartial = true, NextInspectionDate = new DateTime(2026, 9, 15, 18, 0, 0), PartialReason = " next ",
    ShortageReason = "unused", Memo = " result ", ExpectedUpdatedAt = DateTimeOffset.Parse("2026-09-14T10:00:00+09:00"),
    Defects = new[] { defectDraft } });
defectDraft.Attachments[0].Memo = "changed after request";
Check(mapped.PartialReason == "next" && mapped.ShortageReason is null && mapped.Memo == "result"
    && mapped.NextInspectionDate == new DateTime(2026, 9, 15) && mapped.ExpectedUpdatedAt.HasValue
    && mapped.Defects[0].Disposition == "NOT_SHIPPABLE" && mapped.Defects[0].Attachments[0].Memo == "photo",
    "request builder preserves contract fields and snapshots nested attachment values");

handler.DefectType = new() { DefectTypeId = 7, DefectCode = "D007", Category1Name = "분류",
    Category2Name = "유형", Memo = "MASTER_DEFAULT_NOTE", IsActive = true };
foreach (var savedMemo in new string?[] { "OPERATOR_SAVED_NOTE", "", null })
{
    foreach (var editable in new[] { true, false })
    {
        handler.Response = new() { ScheduleStatus = "DONE", Result = new() {
            InspectionResultId = 1, GoodQty = 80, UpdatedAt = DateTimeOffset.UtcNow,
            Defects = new() { new() { DefectTypeId = 7, Memo = savedMemo, Disposition = "NOT_SHIPPABLE" } } },
            Inventory = new() { ViewMode = editable ? "edit" : "saved", ShipTargetQty = 80,
                RemainingBeforeCurrentResultQty = 80, CurrentResultStockInQty = 80 } };
        vm = await Load(80, canEdit: editable);
        Check(vm.Defects.Single().Memo == (savedMemo ?? "") && vm.Defects[0].DefectCode == "D007",
            $"saved defect memo survives master lookup (editable={editable}, empty={string.IsNullOrEmpty(savedMemo)})");
        if (editable)
        {
            handler.Request = null;
            await Save(vm);
            Check(handler.Request != null && handler.Request.Defects.Single().Memo == (string.IsNullOrEmpty(savedMemo) ? null : savedMemo),
                "unchanged inspection save preserves the original defect memo");
        }
    }
}
var selectedDefect = new InspectionResultDefectEditModel();
var editableMemoVm = await Load(80);
editableMemoVm.ApplySelectedDefectType(selectedDefect, handler.DefectType);
Check(selectedDefect.Memo == "MASTER_DEFAULT_NOTE", "explicit new defect selection still applies the master default memo");
handler.DefectType = null;

handler.Response = new() { ScheduleStatus = "IN_PROGRESS", Inventory = new() {
    CurrentStockQty = 65, PhysicalStockQty = 80, ShipTargetQty = 100, RemainingBeforeCurrentResultQty = 100 } };
handler.GetRoutes.Clear();
vm = await Load(80);
Check(handler.GetRoutes.SequenceEqual(new[] { "api/v1/inspection-schedules/1/result" }),
    "inspection and stock load in one request without a separate stock-lots lookup");
Check(vm.StockLots.Single().PhysicalQty == 80 && vm.StockLots.Single().StockQty == 65,
    "physical quantity stays visible while reservation-adjusted availability governs shipment");
handler.UseExplicitStockSnapshot = true;
handler.Response.Inventory.StockLots = new() { new() { ProductInventoryLotId = 1, StockQty = 64 } };
vm = await Load(80);
vm.GoodQty = 80;
handler.Request = null;
await Save(vm);
Check(handler.Request is null && !string.IsNullOrEmpty(vm.StockError),
    "an inconsistent bundled stock total blocks saving");
handler.Response.Inventory.StockLots = new() {
    new() { ProductInventoryLotId = 1, StockQty = 30 }, new() { ProductInventoryLotId = 1, StockQty = 35 } };
vm = await Load(80);
vm.GoodQty = 80;
await Save(vm);
Check(handler.Request is null && !string.IsNullOrEmpty(vm.StockError),
    "duplicate inventory LOT IDs cannot silently represent separate stock");
handler.Response.Inventory.StockLots = new() { new() { StockQty = 65 } };
vm = await Load(80);
vm.GoodQty = 80;
await Save(vm);
Check(handler.Request is null && !string.IsNullOrEmpty(vm.StockError),
    "a missing inventory LOT ID blocks saving");
handler.Response = JsonSerializer.Deserialize<InspectionResultResponse>("""
    {"schedule_status":"IN_PROGRESS","inventory":{"current_stock_qty":65,"physical_stock_qty":80,
     "ship_target_qty":100,"remaining_before_current_result_qty":100,"stock_lots":[
     {"lot_id":7,"product_inventory_lot_id":4000000001,"production_lot_id":null,"lot_no":"STOCK-ONLY","stock_qty":35,"physical_qty":50},
     {"lot_id":7,"product_inventory_lot_id":4000000002,"production_lot_id":5000000002,"lot_no":"PRODUCED","stock_qty":30,"physical_qty":30}]}}
    """)!;
await vm.InitializeAsync(1, "LOT-TEST", "Product", "Customer", new(2026, 9, 9), 80, new(2026, 9, 10), 100);
vm.GoodQty = 80;
vm.StockShipQty = 40;
await Save(vm);
Check(handler.Request is { StockShipQty: 40, ResultShipQty: 0, StockInQty: 80 } && string.IsNullOrEmpty(vm.StockError),
    "a successful reload clears stock-load failure and preserves manual shipment rules");
Check(vm.StockLots.Select(row => row.StockQty).SequenceEqual(new[] { 35, 30 })
    && vm.StockLots.All(row => row.AllocatedShipQty == 0)
    && vm.StockLots[0].ProductionLotId is null && vm.StockLots[1].ProductionLotId == 5000000002L
    && vm.StockLots[0].ProductInventoryLotId == 4000000001L,
    "explicit 64-bit LOT IDs and server row order survive manual shipment without client allocation");
handler.Response = new() { ScheduleStatus = "IN_PROGRESS", Inventory = new() {
    StockLots = new(), ShipTargetQty = 100, RemainingBeforeCurrentResultQty = 100 } };
vm = await Load(80);
vm.GoodQty = 80;
handler.Request = null;
await Save(vm);
Check(vm.StockLots.Count == 0 && handler.Request is { StockInQty: 80 },
    "an explicitly empty stock snapshot is valid and differs from a missing snapshot");
handler.UseExplicitStockSnapshot = false;
handler.Response = new() { ScheduleStatus = "DONE",
    Result = new() { GoodQty = 80, UpdatedAt = DateTimeOffset.UtcNow },
    Inventory = new() { StockError = "historical stock discrepancy", PhysicalStockQty = 30,
        ShipTargetQty = 100, RemainingBeforeCurrentResultQty = 100, CurrentResultStockInQty = 80 } };
vm = await Load(80);
handler.Request = null;
await Save(vm);
Check(handler.Request is { GoodQty: 80, StockInQty: 80 } && vm.StockError == "historical stock discrepancy",
    "a valid snapshot preserves stock-error display and the existing equal-value edit path");
vm.GoodQty = 81;
handler.Request = null;
await Save(vm);
Check(handler.Request is null, "a stock discrepancy still blocks quantity-changing edits");
handler.UseExplicitStockSnapshot = true;
handler.GetRoutes.Clear();
handler.Response = new() { ScheduleStatus = "PARTIAL_DONE",
    Result = new() { GoodQty = 100000, IsPartial = true, UpdatedAt = DateTimeOffset.UtcNow },
    Inventory = new() { ViewMode = "saved", CurrentStockQty = 139500, PhysicalStockQty = 139500,
        ShipTargetQty = 300000, RemainingBeforeCurrentResultQty = 300000, CurrentResultStockInQty = 100000,
        StockLots = new() {
            new() { ProductInventoryLotId = 1, LotNo = "OLD", StockQty = 39500, PhysicalQty = 39500 },
            new() { ProductInventoryLotId = 2, LotNo = "LOT-TEST", StockQty = 100000, PhysicalQty = 100000 } } } };
vm = await Load(260500, canEdit: false);
Check(handler.GetRoutes.SequenceEqual(new[] { "api/v1/inspection-schedules/1/result?view_mode=saved" })
    && vm.InventorySummaryAvailable && vm.StockQuantityLabel == "저장 후 재고",
    "read-only detail explicitly requests saved inventory and labels its time basis");
Check(vm.StockLots.Select(row => row.PhysicalQty).SequenceEqual(new[] { 39500, 100000 })
    && vm.StockInQty == 100000 && vm.CurrentStockQty == 139500
    && vm.PriorShippedQty == 0 && vm.TotalShippedQty == 0 && vm.RemainingAfterCurrentQty == 300000,
    "first round displays the original stock LOT separately from its own 100000-piece receipt");
handler.Request = null;
await Save(vm);
Check(handler.Request is null, "historical inventory can never be submitted as an editable stock basis");
handler.Response.ScheduleStatus = "DONE";
handler.Response.Result = new() { GoodQty = 300000, UpdatedAt = DateTimeOffset.UtcNow };
handler.Response.Accumulated = new() { GoodQty = 100000, InspectedQty = 100000 };
handler.Response.Inventory.CurrentResultStockShipQty = 139500;
handler.Response.Inventory.CurrentResultResultShipQty = 160500;
handler.Response.Inventory.CurrentResultStockInQty = 139500;
handler.Response.Inventory.StockLots = new() {
    new() { ProductInventoryLotId = 1, LotNo = "OLD", StockQty = 0, PhysicalQty = 0, AllocatedShipQty = 39500 },
    new() { ProductInventoryLotId = 2, LotNo = "LOT-TEST", StockQty = 139500, PhysicalQty = 139500, AllocatedShipQty = 100000 } };
vm = await Load(260500, canEdit: false);
Check(vm.StockLots.Select(row => row.PhysicalQty).SequenceEqual(new[] { 0, 139500 })
    && vm.StockLots.Select(row => row.AllocatedShipQty).SequenceEqual(new[] { 39500, 100000 })
    && vm.StockInQty == 139500 && vm.AccumulatedGoodQty == 400000
    && vm.TotalShippedQty == 300000 && vm.RemainingAfterCurrentQty == 0,
    "second-round saved quantities stay intact without running a new FIFO allocation");
handler.Response.Inventory.CurrentResultStockInQty = 0;
vm = await Load(260500, canEdit: false);
Check(vm.StockInQty == 0, "read-only detail preserves posted stock-in even for legacy unsettled results");
handler.Response.Inventory.StockError = "저장 당시 재고 확인 불가";
handler.Response.Inventory.StockLots = new();
handler.Response.Inventory.CurrentStockQty = 0;
vm = await Load(260500, canEdit: false);
Check(!vm.InventorySummaryAvailable && vm.StockError.Length > 0 && vm.GoodQty == 300000,
    "unrecoverable history keeps the inspection visible and hides misleading summary zeros");
handler.Response.Inventory.ViewMode = null;
vm = await Load(260500, canEdit: false);
Check(!vm.InventorySummaryAvailable && vm.StockLots.Count == 0 && vm.StockError.Contains("업데이트"),
    "an old server cannot silently fill a historical detail with current inventory");
handler.Response.Inventory.ViewMode = "saved";
vm = await Load(260500);
handler.Request = null;
await Save(vm);
Check(handler.Request is null && !vm.InventorySummaryAvailable,
    "an edit rejects a historical response rather than validating shipment against past stock");
handler.UseExplicitStockSnapshot = false;
await PhotoChecks.Run(Check);
Console.WriteLine($"Inspection regression: {passed} checks passed");

public class RegressionApi : DispatchProxy
{
    public InspectionResultDefectTypeLookupDto? DefectType;
    public bool OmitStockSnapshot;
    public bool UseExplicitStockSnapshot;
    public List<string> GetRoutes { get; } = new();
    public bool ThrowOnGet;
    public int PutCount;
    public TaskCompletionSource<ApiResult<InspectionResultUpsertResponse>>? PendingSave;
    public Func<MultipartFormDataContent, Task<ApiResult<DefectAttachmentUploadResponse>>>? Upload;
    public Func<string, string, Task<ApiResult<bool>>>? Download;
    public string StockLotNo = "OLD";
    public InspectionResultUpsertRequest? Request;
    public InspectionResultResponse Response = new()
    {
        ScheduleStatus = "IN_PROGRESS",
        Inventory = new() { CurrentStockQty = 65000, PhysicalStockQty = 65000,
            ShipTargetQty = 600000, RemainingBeforeCurrentResultQty = 600000, CurrentResultStockShipQty = 65000 }
    };
    protected override object? Invoke(MethodInfo? method, object?[]? args)
    {
        if (method?.Name == "PostMultipartAsync") return Upload!((MultipartFormDataContent)args![1]!);
        if (method?.Name == "DownloadFileAsync") return Download!((string)args![0]!, (string)args[1]!);
        if (method?.Name == "PutAsync")
        {
            PutCount++;
            Request = (InspectionResultUpsertRequest)args![1]!;
            if (PendingSave != null) return PendingSave.Task;
            return Task.FromResult(new ApiResult<InspectionResultUpsertResponse> { Success = true, Data = new() });
        }
        if (method?.Name != "GetAsync") throw new NotSupportedException(method?.Name);
        GetRoutes.Add((string)args![0]!);
        if (ThrowOnGet) throw new IOException("PRIVATE simulated read failure");
        var type = method.GetGenericArguments()[0];
        if (Response.Inventory is not null && !UseExplicitStockSnapshot)
            Response.Inventory.StockLots = OmitStockSnapshot ? null : new() { new() {
                ProductInventoryLotId = 1, ProductionLotId = 2, LotNo = StockLotNo,
                StockQty = Response.Inventory.CurrentStockQty, PhysicalQty = Response.Inventory.PhysicalStockQty } };
        object? data = type == typeof(InspectionResultResponse) ? Response
            : type == typeof(InspectionResultDefectTypeLookupDto) ? DefectType : null;
        var resultType = typeof(ApiResult<>).MakeGenericType(type);
        var result = Activator.CreateInstance(resultType)!;
        resultType.GetProperty("Success")!.SetValue(result, true);
        resultType.GetProperty("Data")!.SetValue(result, data);
        return typeof(Task).GetMethod("FromResult")!.MakeGenericMethod(resultType).Invoke(null, new[] { result });
    }
}
public class RegressionMessages : IMessageService
{
    public void ShowInfo(string message, string title = "") { }
    public List<string> Warnings { get; } = new();
    public List<string> Errors { get; } = new();
    public void ShowWarning(string message, string title = "") => Warnings.Add(message);
    public void ShowError(string message, string title = "") => Errors.Add(message);
    public bool Confirm(string message, string title = "") => true;
}
