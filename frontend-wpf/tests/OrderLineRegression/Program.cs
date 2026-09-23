using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.OrderLineList.Dtos;
using Mes.Wpf.Modules.OrderLineList.ViewModels;
using Mes.Wpf.Modules.OrderLineList.Views;

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

    [STAThread]
    private static void Main(string[] args)
    {
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext());
        var api = DispatchProxy.Create<IApiClient, OrdersApi>();
        var fake = (OrdersApi)(object)api;
        var messages = new Messages();
        var vm = new OrderLineListPageViewModel(api, messages, openLotCreateAsync: item =>
        {
            fake.Rows.Single(x => x.OrderLineId == item.OrderLineId).WorkQueue = null;
            return Task.CompletedTask;
        });
        Wait(vm.InitializeAsync());
        Check(vm.LotCreationButtonText.Contains("25") && vm.CloseDecisionButtonText.Contains("23"), "queue counts cover all pages");
        Wait(vm.ShowCloseDecisionQueueCommand.ExecuteAsync());
        Check(vm.IsCloseDecisionQueue && fake.LastGet.Contains("work_queue=CLOSE_DECISION") && vm.Items.Count == 20, "close queue is server-filtered before paging");
        Wait(vm.NextPageCommand.ExecuteAsync());
        Check(vm.Page == 2 && vm.Items.Count == 3, "queue supports second page");
        var survivor = vm.Items[1];
        var item = vm.Items[0];
        vm.SelectedItem = item;
        Check(vm.CanShortClose && !vm.CanReopen, "only eligible production rows enable completion");
        messages.ConfirmResult = false;
        Wait(vm.ShortCloseCommand.ExecuteAsync());
        Check(fake.PatchCalls == 0 && vm.Items.Contains(item), "canceling the one confirmation changes nothing");
        messages.ConfirmResult = true;
        fake.FailWrite = true;
        Wait(vm.ShortCloseCommand.ExecuteAsync());
        Check(vm.Items.Contains(item) && vm.SelectedItem == item && vm.Page == 2, "failed write keeps row, selection, and page");
        fake.FailWrite = false;
        fake.Pending = new TaskCompletionSource<ApiResult<OrderLineListItemDto>>();
        var saving = vm.ShortCloseCommand.ExecuteAsync();
        var count = fake.PatchCalls;
        Wait(vm.ReopenCommand.ExecuteAsync());
        Wait(vm.ShowCompletedCommand.ExecuteAsync());
        Check(!vm.IsInteractionEnabled && vm.IsInProgressTab && fake.PatchCalls == count, "pending write blocks other actions and tab changes");
        fake.Pending.SetResult(new ApiResult<OrderLineListItemDto> { Success = true, Data = item });
        Wait(saving);
        fake.Pending = null;
        Check(vm.IsInteractionEnabled && vm.IsCloseDecisionQueue && vm.Page == 2 && vm.Items.Count == 2, "successful completion preserves queue and page");
        Check(!vm.Items.Any(x => x.OrderLineId == item.OrderLineId) && vm.Items.Contains(survivor), "only processed row leaves; unchanged row identity survives");
        Check(vm.CloseDecisionButtonText.Contains("22") && vm.SelectedItem == survivor, "count refreshes and next surviving row is selected");
        Check(fake.LastRequest?.ExpectedShipTargetQty == 100 && fake.LastRequest.ExpectedShippedQty == 80 && fake.LastRequest.Memo == null, "completion sends observed quantities without reason");
        Check(messages.Confirmations.Last().Contains("미출고 20"), "confirmation shows target, actual shipment and shortfall");

        Wait(vm.ShowCompletedCommand.ExecuteAsync());
        vm.SelectedItem = vm.Items.First(x => x.OrderLineId == item.OrderLineId);
        Check(vm.CanReopen && vm.SelectedItem.StatusDisplay == "완료(수동)", "manual completion has distinct completed-tab status");
        Wait(vm.ReopenCommand.ExecuteAsync());
        Check(fake.LastPatch.EndsWith("/manual-reopen") && !vm.Items.Any(x => x.OrderLineId == item.OrderLineId), "reopen removes the order from completed list");
        Wait(vm.ShowInProgressCommand.ExecuteAsync());
        Wait(vm.ShowCloseDecisionQueueCommand.ExecuteAsync());
        vm.SelectedItem = vm.Items[0];
        var reworked = vm.SelectedItem.OrderLineId;
        Wait(vm.OpenLotActionCommand.ExecuteAsync());
        Check(vm.IsCloseDecisionQueue && !vm.Items.Any(x => x.OrderLineId == reworked), "rework modal refresh retains current page instance and removes resolved row");
        Wait(vm.ShowCloseDecisionQueueCommand.ExecuteAsync());
        Check(!vm.IsCloseDecisionQueue && !fake.LastGet.Contains("work_queue="), "clicking selected queue returns to production list");

        Wait(vm.ShowLotCreationQueueCommand.ExecuteAsync());
        vm.SelectedItem = vm.Items[0];
        Check(vm.IsPlanDecisionVisible && vm.PlanOptions.Single().Value == "전량 생산", "depleted stock has an explicit existing all-production option");
        Wait(vm.ConfirmPlanCommand.ExecuteAsync());
        Check(vm.CanCreateBaseLot && vm.IsLotCreationQueue, "confirmed plan remains in LOT waiting queue");
        Wait(vm.CreateBaseLotCommand.ExecuteAsync());
        Check(vm.LotCreationButtonText.Contains("24") && vm.IsLotCreationQueue, "creating primary LOT updates queue count without changing filter");

        Wait(vm.ShowCloseDecisionQueueCommand.ExecuteAsync());
        vm.SelectedItem = vm.Items[0];
        var stale = vm.SelectedItem;
        fake.FailNextRefresh = true;
        Wait(vm.ShortCloseCommand.ExecuteAsync());
        Check(vm.Items.Contains(stale) && vm.SelectedItem == stale && messages.Errors.Last().Contains("갱신"), "refresh failure preserves existing list and reports retry by reading");
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
        Check(!vm.Items.Any(x => x.OrderLineId == stale.OrderLineId), "explicit lookup reconciles successful write after refresh failure");

        // A one-row final page moves back only when its last row is resolved.
        fake.Rows.RemoveAll(x => x.WorkQueue == "CLOSE_DECISION" && x.OrderLineId > 121);
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
        vm.Size = 1;
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
        vm.Page = vm.Total;
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync()); // Search explicitly resets page; next use page navigation.
        while (vm.CanGoNextPage) Wait(vm.NextPageCommand.ExecuteAsync());
        var finalPage = vm.Page;
        vm.SelectedItem = vm.Items.Single();
        Wait(vm.ShortCloseCommand.ExecuteAsync());
        Check(vm.Page == Math.Max(1, finalPage - 1), "resolving the final page clamps to the last surviving page");

        if (args.Length > 0)
        {
            Directory.CreateDirectory(args[0]);
            var errors = new BindingErrors();
            PresentationTraceSources.DataBindingSource.Listeners.Add(errors);
            PresentationTraceSources.DataBindingSource.Switch.Level = SourceLevels.Error;
            vm.Size = 20;
            Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
            vm.SelectedItem = vm.Items.FirstOrDefault();
            var page = new OrderLineListPage { DataContext = vm, Width = 1440, Height = 900, Background = Brushes.White };
            Render(page, Path.Combine(args[0], "order-close-queue.png"));
            var scroll = (ScrollViewer)page.FindName("PageScroll");
            scroll.ScrollToVerticalOffset(70);
            page.UpdateLayout();
            var offset = scroll.VerticalOffset;
            vm.SelectedItem = vm.Items.FirstOrDefault();
            Wait(vm.ShortCloseCommand.ExecuteAsync());
            Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            Check(Math.Abs(scroll.VerticalOffset - offset) < 1, "actual WPF page preserves scroll after completion");
            Wait(vm.ShowLotCreationQueueCommand.ExecuteAsync());
            vm.SelectedItem = vm.Items.First();
            scroll.ScrollToTop();
            Render(page, Path.Combine(args[0], "order-lot-queue.png"));
            Wait(vm.ShowCompletedCommand.ExecuteAsync());
            vm.SelectedItem = vm.Items.FirstOrDefault();
            scroll.ScrollToTop();
            Render(page, Path.Combine(args[0], "order-completed.png"));
            Check(errors.Errors.Count == 0, "actual WPF controls render without binding errors: " + string.Join("; ", errors.Errors));
        }
        CheckQueueCountRefresh();
        Console.WriteLine($"Order-line regression checks: {_passed} passed");
    }

    private static void CheckQueueCountRefresh()
    {
        var api = DispatchProxy.Create<IApiClient, OrdersApi>();
        var fake = (OrdersApi)(object)api;
        var vm = new OrderLineListPageViewModel(api, new Messages());
        Check(vm.LotCreationButtonText.Contains("미조회"), "unread count is not displayed as zero");
        Wait(vm.InitializeAsync());
        Wait(vm.ShowCompletedCommand.ExecuteAsync());
        Check(vm.LotCreationButtonText.Contains("미조회") && vm.CloseDecisionButtonText.Contains("미조회"), "completed response can omit both counts");
        fake.Rows[0].WorkQueue = null; // Another operator resolves a deferred order.
        fake.PendingRead = new TaskCompletionSource<bool>();
        var returning = vm.ShowInProgressCommand.ExecuteAsync();
        Check(!vm.IsInteractionEnabled && vm.LotCreationButtonText.Contains("미조회"), "returning tab does not show stale or false-zero counts while loading");
        fake.PendingRead.SetResult(true);
        Wait(returning);
        fake.PendingRead = null;
        Check(vm.LotCreationButtonText.Contains("24") && vm.CloseDecisionButtonText.Contains("23"), "returning to production fetches current global counts");
        Wait(vm.ShowCompletedCommand.ExecuteAsync());
        fake.FailNextRefresh = true;
        Wait(vm.ShowInProgressCommand.ExecuteAsync());
        Check(vm.LotCreationButtonText.Contains("미조회"), "failed return read does not turn unknown into zero");
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
        Check(vm.LotCreationButtonText.Contains("24"), "retry restores fresh counts after failed return");
        fake.OmitCounts = true;
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
        Check(vm.LotCreationButtonText.Contains("미조회"), "missing counts in a successful response remain unknown");
        fake.OmitCounts = false;
        fake.Rows.Clear();
        Wait(vm.SearchOrderLinesCommand.ExecuteAsync());
        Check(vm.LotCreationButtonText.Contains("(0)") && vm.CloseDecisionButtonText.Contains("(0)") && vm.Total == 0,
            "evaluated empty queues display real zero counts");
    }

    private static void Render(FrameworkElement element, string path)
    {
        element.Measure(new Size(1440, 900));
        element.Arrange(new Rect(0, 0, 1440, 900));
        element.UpdateLayout();
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
        var image = new RenderTargetBitmap(1440, 900, 96, 96, PixelFormats.Pbgra32);
        image.Render(element);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(image));
        using var file = File.Create(path);
        encoder.Save(file);
    }
}

public class OrdersApi : DispatchProxy
{
    public List<OrderLineListItemDto> Rows = Enumerable.Range(1, 25).Concat(Enumerable.Range(101, 23)).Select(id => new OrderLineListItemDto
    {
        OrderLineId = id, OrderNo = $"SO-20260922-{id:000}", LineNo = 1, ProductName = "인쇄 제품", ProductCode = "P-001", PartnerName = "덴티움",
        Status = id < 100 ? "OPEN" : "CLOSED", WorkQueue = id < 100 ? "LOT_CREATION" : "CLOSE_DECISION",
        HasLot = id >= 100, DecisionMade = id >= 100, NeedsShortageAction = id >= 100, OrderQty = 100,
        ShipTargetQty = 100, AlreadyShippedQty = id < 100 ? 0 : 80, RemainingShipQty = id < 100 ? 100 : 20,
        PlannedProductionQty = 100, DecisionRequired = id < 100, AllowedPlanTypes = id < 100 ? new() { "AUTO_PRODUCTION" } : new(),
        UpdatedAt = DateTimeOffset.Parse("2026-09-22T03:00:00Z")
    }).ToList();
    public string LastGet = "", LastPatch = "";
    public int PatchCalls;
    public bool FailWrite, FailNextRefresh;
    public bool OmitCounts;
    public TaskCompletionSource<bool>? PendingRead;
    public OrderLineShortCloseRequest? LastRequest;
    public TaskCompletionSource<ApiResult<OrderLineListItemDto>>? Pending;
    protected override object? Invoke(MethodInfo? method, object?[]? args)
    {
        var route = (string)args![0]!;
        if (method!.Name == "GetAsync")
        {
            LastGet = route;
            if (FailNextRefresh)
            {
                FailNextRefresh = false;
                return Task.FromResult(new ApiResult<OrderLineListResponse> { Success = false, Message = "목록 갱신 실패" });
            }
            var query = route.Split('?')[1].Split('&').Select(x => x.Split('=')).ToDictionary(x => x[0], x => x[1]);
            var page = int.Parse(query["page"]); var size = int.Parse(query["size"]);
            var rows = Rows.Where(x => query["status_group"] == "COMPLETED" ? x.Status == "DONE" : x.Status != "DONE");
            if (query.TryGetValue("work_queue", out var queue)) rows = rows.Where(x => x.WorkQueue == queue);
            var response = new ApiResult<OrderLineListResponse> { Success = true, Data = new()
            {
                Items = JsonSerializer.Deserialize<List<OrderLineListItemDto>>(JsonSerializer.Serialize(rows.Skip((page - 1) * size).Take(size)))!,
                Meta = new() { Page = page, Size = size, Total = rows.Count() },
                QueueCounts = query["status_group"] == "COMPLETED" || OmitCounts ? null : new()
                    { ["lot_creation"] = Rows.Count(x => x.WorkQueue == "LOT_CREATION"), ["close_decision"] = Rows.Count(x => x.WorkQueue == "CLOSE_DECISION") }
            } };
            return CompleteRead();
            async Task<ApiResult<OrderLineListResponse>> CompleteRead()
            {
                if (PendingRead != null) await PendingRead.Task;
                return response;
            }
        }
        var id = long.Parse(route.Split('?')[0].Split('/').First(x => long.TryParse(x, out _)));
        var row = Rows.Single(x => x.OrderLineId == id);
        if (method.Name == "PatchAsync")
        {
            PatchCalls++; LastPatch = route; LastRequest = (OrderLineShortCloseRequest)args[1]!;
            return Save();
            async Task<ApiResult<OrderLineListItemDto>> Save()
            {
                if (FailWrite) return new() { Success = false, Message = "출고 현황이 변경되었습니다." };
                if (Pending != null) await Pending.Task;
                row.ManualClosed = route.EndsWith("/manual-close");
                row.Status = row.ManualClosed ? "DONE" : "CLOSED";
                row.WorkQueue = row.ManualClosed ? null : "CLOSE_DECISION";
                return new() { Success = true, Data = row };
            }
        }
        if (method.Name == "PostAsync")
        {
            if (route.EndsWith("/base-lot"))
            {
                row.HasLot = true; row.Status = "CLOSED"; row.WorkQueue = null;
                return Task.FromResult(new ApiResult<object> { Success = true, Data = new() });
            }
            row.DecisionMade = true; row.DecisionRequired = false; row.AllowedPlanTypes.Clear();
            return Task.FromResult(new ApiResult<OrderLineListItemDto> { Success = true, Data = row });
        }
        throw new InvalidOperationException(method.Name + " " + route);
    }
}
internal sealed class Messages : IMessageService
{
    public bool ConfirmResult = true;
    public List<string> Confirmations = new(), Errors = new();
    public bool Confirm(string message, string title = "") { Confirmations.Add(message); return ConfirmResult; }
    public void ShowError(string message, string title = "") => Errors.Add(message);
    public void ShowInfo(string message, string title = "") { }
    public void ShowWarning(string message, string title = "") { }
}
internal sealed class BindingErrors : TraceListener
{
    public List<string> Errors = new();
    public override void Write(string? message) { if (!string.IsNullOrEmpty(message)) Errors.Add(message); }
    public override void WriteLine(string? message) => Write(message);
}
