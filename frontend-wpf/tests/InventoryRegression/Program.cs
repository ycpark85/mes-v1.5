using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.Inventories.Dtos;
using Mes.Wpf.Modules.Inventories.ViewModels;
using Mes.Wpf.Modules.Inventories.Views;

internal static class Program
{
    private static int _passed;
    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
        _passed++;
        Console.WriteLine("PASS: " + message);
    }
    private static void Wait(Task task)
    {
        if (!task.IsCompleted)
        {
            var frame = new DispatcherFrame();
            var dispatcher = Dispatcher.CurrentDispatcher;
            task.ContinueWith(_ => dispatcher.BeginInvoke(() => frame.Continue = false));
            Dispatcher.PushFrame(frame);
        }
        task.GetAwaiter().GetResult();
    }

    private static void WaitUntil(Func<bool> condition)
    {
        Wait(PollAsync());
        async Task PollAsync()
        {
            var elapsed = Stopwatch.StartNew();
            while (!condition())
            {
                if (elapsed.Elapsed > TimeSpan.FromSeconds(5)) throw new TimeoutException("Inventory state did not settle.");
                await Task.Delay(10);
            }
        }
    }

    private static void VerifyDebouncedSelection()
    {
        var api = DispatchProxy.Create<IApiClient, InventoryApi>();
        var fake = (InventoryApi)(object)api;
        var vm = new InventoryPageViewModel(api, new Messages());
        Wait(vm.InitializeAsync());
        var calls = fake.GetCalls;
        vm.SelectedItem = vm.Items[0];
        Check(fake.GetCalls == calls && vm.LotsLoading && vm.Lots.Count == 0,
            "product selection waits before sending a LOT request and exposes loading state");
        for (var i = 0; i < 20; i++) vm.SelectedItem = vm.Items[i % 2];
        Check(fake.GetCalls == calls, "rapid product selection does not send intermediate requests");
        WaitUntil(() => !vm.LotsLoading);
        Check(fake.GetCalls == calls + 1 && vm.Lots.Single().ProductId == 2,
            "twenty rapid selections send only the final product LOT request");
        calls = fake.GetCalls;
        vm.SelectedItem = vm.Items[1];
        Wait(Task.Delay(350));
        Check(fake.GetCalls == calls, "clicking the already selected product does not reload it");

        vm.SelectedLot = vm.Lots[0];
        vm.OpenHistoryCommand.Execute(null);
        calls = fake.GetCalls;
        vm.SelectedItem = vm.Items[0];
        Check(vm.Lots.Count == 0 && vm.Movements.Count == 0 && !vm.IsHistoryOpen
              && vm.LotsLoading && !vm.OpenHistoryCommand.CanExecute(null) && !vm.OpenAdjustmentCommand.CanExecute(null),
            "changing product immediately clears old stock and history throughout the delay");
        vm.SelectedItem = null;
        Wait(Task.Delay(350));
        Check(fake.GetCalls == calls && !vm.LotsLoading && vm.Lots.Count == 0,
            "clearing product selection cancels its pending lookup");
        vm.SelectedItem = vm.Items[0];
        vm.ResetCommand.Execute(null);
        Wait(Task.Delay(350));
        Check(fake.GetCalls == calls && vm.Items.Count == 0 && !vm.LotsLoading,
            "reset prevents a delayed request from reopening cleared results");

        Wait(vm.InitializeAsync());
        vm.SelectedItem = vm.Items[0];
        var lotCalls = fake.Routes.Count(x => x.Contains("/lots?"));
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(fake.Routes.Count(x => x.Contains("/lots?")) == lotCalls + 1 && vm.Lots.Count == 2,
            "explicit list refresh loads selected stock without waiting for the selection delay");
        Wait(Task.Delay(350));
        Check(fake.Routes.Count(x => x.Contains("/lots?")) == lotCalls + 1,
            "explicit refresh supersedes the delayed request without a duplicate lookup");

        fake.GetOverride = (type, route) => type == typeof(InventoryLotListDto)
            ? Task.FromResult(new ApiResult<InventoryLotListDto> { Success = false, Message = "조회 실패" }) : null;
        vm.SelectedItem = vm.Items[1];
        WaitUntil(() => !vm.LotsLoading);
        Check(vm.Lots.Count == 0 && vm.LotStatus == "조회 실패" && vm.LoadLotsCommand.CanExecute(null),
            "failed delayed lookup clears loading state and permits retry");
        fake.GetOverride = null;
        Wait(vm.LoadLotsCommand.ExecuteAsync());
        Check(vm.Lots.Single().ProductId == 2, "manual retry after delayed failure still loads the selected product");
    }

    private static void VerifyStockRefreshConsistency()
    {
        var api = DispatchProxy.Create<IApiClient, InventoryApi>();
        var fake = (InventoryApi)(object)api;
        var vm = new InventoryPageViewModel(api, new Messages());
        Wait(vm.InitializeAsync());
        vm.SelectedItem = vm.Items[0];
        WaitUntil(() => !vm.LotsLoading);
        vm.SelectedLot = vm.Lots[1];
        var changed = fake.History(1, 12);
        changed.CurrentQty = 120000;
        changed.StockSnapshot!.Items[1].CurrentQty = 120000;
        changed.StockSnapshot.ProductCurrentQty = 180000;
        changed.StockSnapshot.TotalQty = 160000;
        changed.StockSnapshot.Total = 51;
        // Totals intentionally exceed this page: never sum a partial page locally.
        fake.GetOverride = (type, _) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = changed }) : null;
        vm.OpenHistoryCommand.Execute(null);
        Check(vm.SelectedLot!.CurrentQty == 120000 && vm.SelectedItem!.CurrentQty == 180000
              && vm.LotSummaryText.Contains("160,000") && vm.LotNextCommand.CanExecute(null),
            "history refresh updates LOT, product and filtered all-page totals from one snapshot");
        Check(fake.LastRoute.Contains("stock_page=1") && fake.LastRoute.Contains("stock_size=50"),
            "history requests the current stock page in its snapshot");
        changed.StockSnapshot = null;
        changed.CurrentQty = 1;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.Movements.Count == 0 && vm.SelectedLot.CurrentQty == 120000
              && vm.SelectedItem.CurrentQty == 180000 && vm.HistoryStatus.Contains("서버 버전"),
            "an older server without stock snapshot cannot partially update displayed quantities");

        fake.GetOverride = null;
        Wait(vm.LoadLotsCommand.ExecuteAsync());
        var slowLots = new TaskCompletionSource<ApiResult<InventoryLotListDto>>();
        fake.GetOverride = (type, _) => type == typeof(InventoryLotListDto) ? slowLots.Task : null;
        var refresh = vm.LoadLotsCommand.ExecuteAsync();
        vm.SelectedLot = vm.Lots[0];
        slowLots.SetResult(new() { Success = true, Data = fake.Lots(1) });
        Wait(refresh);
        Check(vm.SelectedLot?.ProductInventoryLotId == 11 && !vm.IsHistoryOpen && vm.Movements.Count == 0,
            "a LOT chosen during refresh remains selected and does not reopen the previous detail");
        slowLots = new();
        refresh = vm.LoadLotsCommand.ExecuteAsync();
        vm.SelectedLot = null;
        slowLots.SetResult(new() { Success = true, Data = fake.Lots(1) });
        Wait(refresh);
        Check(vm.SelectedLot == null, "clearing selection during refresh is preserved");

        fake.GetOverride = null;
        vm.SelectedLot = vm.Lots[1];
        vm.OpenHistoryCommand.Execute(null);
        var slowHistory = new TaskCompletionSource<ApiResult<InventoryMovementListDto>>();
        var oldStock = fake.Lots(1);
        oldStock.StockWarning = "OLD PRODUCT WARNING";
        fake.GetOverride = (type, route) => type == typeof(InventoryMovementListDto) ? slowHistory.Task
            : type == typeof(InventoryLotListDto) && route.Contains("/1/lots")
                ? Task.FromResult(new ApiResult<InventoryLotListDto> { Success = true, Data = oldStock }) : null;
        refresh = vm.LoadLotsCommand.ExecuteAsync();
        Check(vm.HistoryLoading, "LOT refresh waits for active history refresh");
        vm.SelectedItem = vm.Items[1];
        WaitUntil(() => !vm.LotsLoading);
        var newStatus = vm.LotStatus;
        slowHistory.SetResult(new() { Success = true, Data = fake.History(1, 12) });
        Wait(refresh);
        Check(vm.SelectedItem.ProductId == 2 && vm.Lots.Single().ProductId == 2
              && vm.LotStatus == newStatus && !vm.LotStatus.Contains("OLD PRODUCT"),
            "finishing an old nested history request cannot overwrite the new product status");

        fake.GetOverride = null;
        vm.SelectedItem = vm.Items[0];
        WaitUntil(() => !vm.LotsLoading);
        vm.SelectedLot = vm.Lots[1];
        vm.OpenHistoryCommand.Execute(null);
        slowHistory = new();
        fake.GetOverride = (type, _) => type == typeof(InventoryMovementListDto) ? slowHistory.Task : null;
        var historyRefresh = vm.SearchHistoryCommand.ExecuteAsync();
        // A newer LOT query invalidates a pending history snapshot, even for the same LOT.
        fake.GetOverride = null;
        Wait(vm.LoadLotsCommand.ExecuteAsync());
        slowHistory.SetResult(new() { Success = true, Data = changed });
        Wait(historyRefresh);
        Check(vm.SelectedLot!.CurrentQty == 139500 && vm.SelectedItem.CurrentQty == 139500
              && vm.Movements.Count == 1 && !vm.HistoryStatus.Contains("서버 버전"),
            "a stale same-LOT history response cannot overwrite a newer stock refresh");

        vm.LotKeyword = "CT26H";
        vm.IncludeZeroStock = true;
        Wait(vm.LoadLotsCommand.ExecuteAsync());
        vm.LotKeyword = "UNAPPLIED SEARCH";
        vm.IncludeZeroStock = false;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(fake.LastRoute.Contains("stock_q=CT26H") && fake.LastRoute.Contains("stock_include_zero=true")
              && !fake.LastRoute.Contains("UNAPPLIED"),
            "history refresh uses the stock filters actually applied to the left list");
        var invalidSnapshot = fake.History(1, 12);
        invalidSnapshot.StockSnapshot!.Items[1].CurrentQty = 7;
        fake.GetOverride = (type, _) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = invalidSnapshot }) : null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.SelectedLot.CurrentQty == 139500 && vm.Movements.Count == 0
              && vm.HistoryStatus.Contains("서버 버전"),
            "conflicting LOT quantities in a bundled response are rejected before applying any values");
        var secondPage = fake.History(1, 12);
        secondPage.StockSnapshot!.Page = 2; secondPage.StockSnapshot.Total = 51;
        fake.GetOverride = (type, _) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = secondPage }) : null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(fake.LastRoute.Contains("stock_page=2") && vm.LotPreviousCommand.CanExecute(null),
            "history refresh carries forward a non-first stock page");

        var removed = fake.History(1, 12);
        removed.CurrentQty = 0;
        removed.StockSnapshot!.Items.Clear();
        removed.StockSnapshot.Total = 0; removed.StockSnapshot.TotalQty = 0;
        removed.StockSnapshot.ProductCurrentQty = 0;
        fake.GetOverride = (type, _) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = removed }) : null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.SelectedLot == null && vm.Lots.Count == 0 && !vm.IsHistoryOpen
              && vm.Movements.Count == 0 && vm.SelectedItem.CurrentQty == 0 && vm.LotSummaryText.Contains("0"),
            "a depleted LOT removed by stock filters clears its detail and refreshes totals");
    }

    [STAThread]
    private static void Main(string[] args)
    {
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext());
        var application = new Application();
        foreach (var path in new[] { "Tokens/Colors", "Tokens/Brushes", "Controls/Buttons", "Controls/Inputs", "Controls/DataGrid", "Controls/StatusBadges", "Layout/Shell", "Layout/CrudPage" })
            application.Resources.MergedDictionaries.Add(new ResourceDictionary { Source = new Uri($"/Mes.Wpf;component/Styles/{path}.xaml", UriKind.Relative) });
        VerifyDebouncedSelection();
        VerifyStockRefreshConsistency();
        var api = DispatchProxy.Create<IApiClient, InventoryApi>();
        var fake = (InventoryApi)(object)api;
        var messages = new Messages();
        var vm = new InventoryPageViewModel(api, messages);
        Check(!vm.OpenHistoryCommand.CanExecute(null) && !vm.OpenAdjustmentCommand.CanExecute(null), "no LOT selection cannot open history or adjustment");
        Wait(vm.InitializeAsync());
        vm.SelectedItem = vm.Items[0];
        WaitUntil(() => !vm.LotsLoading);
        Check(vm.Lots.Count == 2 && vm.Movements.Count == 0, "product selection loads LOT quantities without mixed product history");
        vm.SelectedLot = vm.Lots[1];
        Check(!vm.IsHistoryOpen && vm.Movements.Count == 0 && !vm.SearchHistoryCommand.CanExecute(null),
            "selecting a LOT waits for explicit detail before enabling history filters");
        vm.OpenHistoryCommand.Execute(null);
        Check(vm.IsHistoryOpen && vm.Lots.Count == 2 && vm.Movements.Single().ProductInventoryLotId == 12, "detail shows the selected LOT history alongside the stock list");
        vm.DateFrom = new DateTime(2026, 9, 1); vm.DateTo = new DateTime(2026, 9, 18); vm.SelectedMovementType = "출고";
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(fake.LastRoute.Contains("date_from=2026-09-01") && fake.LastRoute.Contains("date_to=2026-09-18") && fake.LastRoute.Contains("movement_type=SHIP_OUT"), "history sends date and movement filters");
        vm.OpenHistoryCommand.Execute(null);
        Check(vm.SelectedLot?.ProductInventoryLotId == 12 && vm.DateFrom.HasValue && vm.SelectedMovementType == "출고", "reopening detail preserves selection and filters");
        var calls = fake.GetCalls;
        vm.DateFrom = new DateTime(2026, 9, 19);
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(fake.GetCalls == calls && vm.Movements.Count == 0 && vm.HistoryStatus.Contains("시작일"), "invalid period clears stale rows without a request");
        Wait(vm.ClearHistoryPeriodCommand.ExecuteAsync());
        Check(vm.DateFrom == null && vm.DateTo == null && vm.Movements.Count == 1, "all-period lookup restores valid history");
        vm.IncludeZeroStock = true;
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(fake.Routes.Any(x => x.Contains("inventories?") && x.Contains("include_zero=true")) && fake.LastRoute.Contains("product_inventory_lot_id=12"), "zero-stock product refresh preserves active LOT history");
        vm.SelectedItem = vm.Items[1];
        Check(!vm.IsHistoryOpen && vm.SelectedLot == null && vm.Movements.Count == 0 && vm.DateFrom == null && vm.SelectedMovementType == "전체", "new product clears dependent history and filters");

        var slowLots = new TaskCompletionSource<ApiResult<InventoryLotListDto>>();
        fake.GetOverride = (type, route) => type == typeof(InventoryLotListDto) && route.Contains("/1/lots") ? slowLots.Task : null;
        calls = fake.GetCalls;
        vm.SelectedItem = vm.Items[0];
        WaitUntil(() => fake.GetCalls > calls);
        Check(vm.LotsLoading, "LOT request exposes loading state");
        vm.SelectedItem = vm.Items[1];
        slowLots.SetResult(new() { Success = true, Data = fake.Lots(1) });
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
        Check(vm.Lots.Count == 0 && vm.LotsLoading, "late response cannot repopulate stock while the new selection is waiting");
        WaitUntil(() => !vm.LotsLoading);
        Check(vm.Lots.Single().ProductId == 2 && !vm.LotsLoading, "late LOT response cannot replace a new product selection");
        fake.GetOverride = null;
        vm.SelectedItem = vm.Items[0];
        WaitUntil(() => !vm.LotsLoading);
        vm.SelectedLot = vm.Lots[0];
        var slowHistory = new TaskCompletionSource<ApiResult<InventoryMovementListDto>>();
        fake.GetOverride = (type, route) => type == typeof(InventoryMovementListDto) && route.Contains("lot_id=11&") ? slowHistory.Task : null;
        vm.OpenHistoryCommand.Execute(null);
        vm.SelectedLot = vm.Lots[1];
        slowHistory.SetResult(new() { Success = true, Data = fake.History(1, 11) });
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
        Check(!vm.IsHistoryOpen && vm.Movements.Count == 0 && !vm.HistoryLoading,
            "changing LOT clears right detail and a late previous response cannot reopen it");
        vm.OpenHistoryCommand.Execute(null);
        Check(vm.Movements.Single().ProductInventoryLotId == 12 && !vm.HistoryLoading, "late history cannot replace a newly selected LOT");
        fake.GetOverride = (type, route) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = fake.History(1, 11) }) : null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.Movements.Count == 0 && vm.HistoryStatus.Contains("서버 버전"), "old or mismatched server response never exposes another LOT history");
        fake.GetOverride = (type, route) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = false, Message = "연결 실패" }) : null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.Movements.Count == 0 && vm.HistoryStatus == "연결 실패" && !vm.HistoryLoading, "history failure clears old data and permits retry");
        fake.GetOverride = null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.Movements.Count == 1, "failed history can be retried");

        fake.GetOverride = (type, route) => type == typeof(InventoryMovementListDto)
            ? Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = fake.History(1, 12, total: 51, page: route.Contains("page=2") ? 2 : 1) }) : null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.HistoryNextCommand.CanExecute(null), "history enables next page when rows exceed page size");
        Wait(vm.HistoryNextCommand.ExecuteAsync());
        Check(fake.LastRoute.Contains("page=2") && vm.HistoryPreviousCommand.CanExecute(null) && !vm.HistoryNextCommand.CanExecute(null), "history page navigation retains LOT and correctly updates buttons");
        fake.GetOverride = null;
        Wait(vm.SearchHistoryCommand.ExecuteAsync());

        InventoryAdjustmentWindowViewModel? adjustment = null;
        vm.RequestOpenAdjustment += value => adjustment = value;
        vm.OpenAdjustmentCommand.Execute(null);
        Check(adjustment?.LotNo == "CT26H31E13", "adjustment captures selected LOT");
        var edit = adjustment!;
        edit.Qty = 5; edit.Memo = " ";
        Wait(edit.SaveCommand.ExecuteAsync());
        Check(fake.PostCalls == 0 && messages.Warnings > 0, "blank adjustment reason cannot be submitted");
        edit.Qty = 0; edit.Memo = "실사 차이";
        Wait(edit.SaveCommand.ExecuteAsync());
        Check(fake.PostCalls == 0, "zero adjustment quantity cannot be submitted");
        edit.Qty = 5; edit.Direction = "재고감소";
        var pendingSave = new TaskCompletionSource<ApiResult<InventoryMovementDto>>();
        fake.PostOverride = pendingSave.Task;
        var save = edit.SaveCommand.ExecuteAsync();
        Wait(edit.SaveCommand.ExecuteAsync());
        Check(fake.PostCalls == 1 && !edit.CanInput && !edit.CloseCommand.CanExecute(null), "in-flight adjustment prevents duplicate submissions and close");
        Check(fake.LastPostRoute.EndsWith("/1/lots/12/adjust?direction=OUT") && fake.Request?.Qty == 5 && fake.Request.Memo == "실사 차이", "adjustment uses exact-LOT route with required reason");
        pendingSave.SetResult(new() { Success = false, Message = "예약 재고 부족" });
        Wait(save);
        Check(edit.CanInput && messages.Errors.Last() == "예약 재고 부족", "reservation rejection keeps modal editable");
        var closed = false;
        edit.CloseRequested += saved => closed = saved;
        fake.PostOverride = null;
        Wait(edit.SaveCommand.ExecuteAsync());
        Check(closed && messages.Infos > 0, "successful adjustment closes and refreshes the inventory page");
        var corrected = new InventoryMovementDto { MovementType = "SHIP_OUT", Qty = 100, CreatedAt = DateTimeOffset.Parse("2026-09-17T15:00:00Z") };
        Check(corrected.OutQty == -100 && corrected.MovementLabel == "출고 정정" && corrected.LocalCreatedAt == new DateTime(2026, 9, 18), "outbound correction and Korean calendar date remain unambiguous");
        corrected.MovementType = "INSPECTION_IN"; corrected.Qty = -50;
        Check(corrected.InQty == -50 && corrected.OutQty == null && corrected.MovementLabel == "입고 정정", "negative inspection correction remains an inbound correction");
        var big = System.Text.Json.JsonSerializer.Deserialize<InventoryLotDto>("{\"product_inventory_lot_id\":1,\"current_qty\":3000000000}");
        Check(big?.CurrentQty == 3000000000L, "inventory quantities support database bigint values");
        var productData = System.Text.Json.JsonSerializer.Deserialize<InventoryDto>(
            "{\"product_id\":1,\"updated_at\":\"2026-09-17T15:00:00Z\"}")!;
        Check(productData.LocalUpdatedAt == new DateTime(2026, 9, 18),
            "inventory API converts update time to Korea");
        Check(new InventoryDto().LocalUpdatedAt == null && new InventoryLotDto().LocalUpdatedAt == null,
            "unknown update time remains empty rather than inventing values");
        fake.ProductUpdatedAt = DateTimeOffset.Parse("2026-09-18T03:45:00Z");
        Wait(vm.LoadLotsCommand.ExecuteAsync());
        Check(vm.SelectedItem!.LocalUpdatedAt == new DateTime(2026, 9, 18, 12, 45, 0),
            "LOT refresh updates the product timestamp together with the quantity");
        fake.ProductUpdatedAt = DateTimeOffset.Parse("2026-09-18T04:00:00Z");
        Wait(vm.SearchHistoryCommand.ExecuteAsync());
        Check(vm.SelectedLot!.LocalUpdatedAt == new DateTime(2026, 9, 18, 13, 0, 0),
            "history refresh keeps the selected LOT timestamp consistent with its current quantity");

        if (args.Length == 1)
        {
            Directory.CreateDirectory(args[0]);
            var errors = new BindingErrors();
            PresentationTraceSources.DataBindingSource.Listeners.Add(errors);
            PresentationTraceSources.DataBindingSource.Switch.Level = SourceLevels.Error;
            vm.SelectedItem = vm.Items[0];
            vm.SelectedLot = vm.Lots[0];
            vm.SelectedLot = vm.Lots[1];
            var page = new InventoryPage { DataContext = vm, Width = 1120, Height = 780, Background = Brushes.White };
            Render(page, Path.Combine(args[0], "inventory-current.png"));
            vm.OpenHistoryCommand.Execute(null);
            Render(page, Path.Combine(args[0], "inventory-history.png"));
            page.Width = 1440;
            Render(page, Path.Combine(args[0], "inventory-history-wide.png"), 1440, 780);
            var dialog = new InventoryAdjustmentWindow(new InventoryAdjustmentWindowViewModel(api, messages, vm.SelectedItem!, vm.SelectedLot!));
            ((System.Windows.Controls.Panel)dialog.Content).Background = Brushes.White;
            Render((FrameworkElement)dialog.Content, Path.Combine(args[0], "inventory-adjustment.png"), 520, 440);
            Check(errors.Errors.Count == 0, "real WPF controls render without binding errors: " + string.Join("; ", errors.Errors));
        }
        Console.WriteLine($"Inventory regression checks: {_passed} passed");
    }

    private static void Render(FrameworkElement element, string path, int width = 1120, int height = 780)
    {
        element.Measure(new Size(width, height));
        element.Arrange(new Rect(0, 0, width, height));
        element.UpdateLayout();
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(element);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = File.Create(path);
        encoder.Save(output);
    }
}

public class InventoryApi : DispatchProxy
{
    public DateTimeOffset ProductUpdatedAt = DateTimeOffset.Parse("2026-09-18T02:30:00Z");
    public List<string> Routes { get; } = new();
    public string LastRoute { get; private set; } = "";
    public string LastPostRoute { get; private set; } = "";
    public int GetCalls, PostCalls;
    public InventoryAdjustmentRequest? Request;
    public Func<Type, string, object?>? GetOverride;
    public Task<ApiResult<InventoryMovementDto>>? PostOverride;
    public InventoryLotListDto Lots(long product) => new()
    {
        ProductId = product, ProductCurrentQty = product == 1 ? 139500 : 0, TotalQty = product == 1 ? 139500 : 0,
        ProductUpdatedAt = ProductUpdatedAt,
        Total = product == 1 ? 2 : 1, Page = 1, Size = 50,
        Items = product == 1 ? new() {
            new() { ProductId = 1, ProductInventoryLotId = 11, LotNo = "CT26G29E08", CurrentQty = 0, UpdatedAt = DateTimeOffset.Parse("2026-09-14T08:00:00Z") },
            new() { ProductId = 1, ProductInventoryLotId = 12, LotNo = "CT26H31E13", CurrentQty = 139500, UpdatedAt = ProductUpdatedAt }
        } : new() { new() { ProductId = 2, ProductInventoryLotId = 21, LotNo = "ZERO-STOCK", CurrentQty = 0 } }
    };
    public InventoryMovementListDto History(long product, long lot, int total = 1, int page = 1) => new()
    {
        ProductInventoryLotId = lot, CurrentQty = lot == 12 ? 139500 : 0, StockLotNo = lot == 12 ? "CT26H31E13" : "CT26G29E08",
        LotUpdatedAt = ProductUpdatedAt,
        StockSnapshot = Lots(product),
        Total = total, Page = page, Size = 50,
        Items = new() { new() { ProductId = product, ProductInventoryLotId = lot, MovementType = "INSPECTION_IN", Qty = 139500,
            LotBalanceAfter = 139500, BalanceAfter = 139500, CreatedAt = DateTimeOffset.Parse("2026-09-14T08:00:00Z"), InspectionResultId = 1, Memo = "검수 후 잔여수량 재고편입" } }
    };
    protected override object? Invoke(MethodInfo? method, object?[]? args)
    {
        var route = (string)args![0]!;
        if (method!.Name == "GetAsync")
        {
            LastRoute = route; Routes.Add(route); GetCalls++;
            var type = method.GetGenericArguments()[0];
            var custom = GetOverride?.Invoke(type, route);
            if (custom != null) return custom;
            if (type == typeof(InventoryListDto)) return Task.FromResult(new ApiResult<InventoryListDto> { Success = true, Data = new()
            {
                Total = 2, Page = 1, Size = 100, Items = new() {
                    new() { ProductId = 1, ProductCode = "P-001", ProductName = "TYVEK 픽스처용", Uom = "장", CurrentQty = 139500, UpdatedAt = ProductUpdatedAt },
                    new() { ProductId = 2, ProductCode = "P-002", ProductName = "재고 소진 품목", Uom = "장", CurrentQty = 0 }
                }
            } });
            if (type == typeof(InventoryLotListDto)) return Task.FromResult(new ApiResult<InventoryLotListDto> { Success = true, Data = Lots(route.Contains("/1/lots") ? 1 : 2) });
            if (type == typeof(InventoryMovementListDto))
            {
                var lot = route.Contains("lot_id=12&") ? 12 : route.Contains("lot_id=11&") ? 11 : 21;
                return Task.FromResult(new ApiResult<InventoryMovementListDto> { Success = true, Data = History(lot == 21 ? 2 : 1, lot) });
            }
        }
        if (method.Name == "PostAsync")
        {
            PostCalls++; LastPostRoute = route; Request = (InventoryAdjustmentRequest)args[1]!;
            return PostOverride ?? Task.FromResult(new ApiResult<InventoryMovementDto> { Success = true, Data = new() });
        }
        throw new InvalidOperationException(method.Name + ": " + route);
    }
}

internal sealed class Messages : IMessageService
{
    public int Warnings, Infos;
    public List<string> Errors { get; } = new();
    public bool Confirm(string message, string title = "") => true;
    public void ShowError(string message, string title = "") => Errors.Add(message);
    public void ShowInfo(string message, string title = "") => Infos++;
    public void ShowWarning(string message, string title = "") => Warnings++;
}
internal sealed class BindingErrors : TraceListener
{
    public List<string> Errors { get; } = new();
    public override void Write(string? message) { if (!string.IsNullOrEmpty(message)) Errors.Add(message); }
    public override void WriteLine(string? message) => Write(message);
}
