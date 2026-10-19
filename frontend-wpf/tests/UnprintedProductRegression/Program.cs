using System.Collections.ObjectModel;
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
using Mes.Wpf.Modules.Drawings.Dtos;
using Mes.Wpf.Modules.Products.Dtos;
using Mes.Wpf.Modules.Products.ViewModels;
using Mes.Wpf.Modules.Products.Views;
using Mes.Wpf.Modules.OrderLines.Dtos;
using Mes.Wpf.Modules.OrderLines.ViewModels;
using Mes.Wpf.Modules.OrderLines.Views;

internal static class Program
{
    private static int _checks;
    private static void Check(bool success, string message)
    {
        if (!success) throw new Exception(message);
        _checks++;
        Console.WriteLine("PASS: " + message);
    }
    internal static void Wait(Task task)
    {
        if (!task.IsCompleted)
        {
            var dispatcher = Dispatcher.CurrentDispatcher;
            var frame = new DispatcherFrame();
            task.ContinueWith(_ => dispatcher.BeginInvoke(() => frame.Continue = false));
            Dispatcher.PushFrame(frame);
        }
        task.GetAwaiter().GetResult();
    }
    [STAThread]
    private static void Main(string[] args)
    {
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext());
        if (args.Length == 2 && args[0] == "--walkthrough")
        {
            SharedCodeWalkthrough.Run(args[1]);
            return;
        }
        var api = DispatchProxy.Create<IApiClient, ProductsApi>();
        var fake = (ProductsApi)(object)api;
        var messages = new Messages();
        var vm = new ProductPageViewModel(api, messages, new DrawingViewer());
        Wait(vm.InitializeAsync());
        Check(vm.CanEnterProductCode && !vm.EditModel.IsUnprintedManaged, "existing registration remains the default");
        vm.EditModel.IsUnprintedManaged = true;
        vm.EditModel.ProductName = "공통 무지 상자";
        vm.SelectDrawing(new DrawingDto { DrawingId = 2, DrawingNo = "D-002", IsActive = true });
        vm.EditModel.RoutingTemplateId = 1;
        Check(!vm.CanEnterProductCode, "unprinted internal code is not manually entered");
        Wait(vm.SaveCommand.ExecuteAsync());
        Check(fake.LastProduct?.IsUnprintedManaged == true && fake.LastProduct.ProductCode == "", "managed registration sends automatic-code mode");
        Check(vm.SelectedItem?.ProductCode == "MES-U000001" && vm.CanManagePartnerMappings, "save selects server-issued product and enables partner linking");
        vm.EditCommand.Execute(null);
        Check(!vm.CanChangeDrawing && !vm.CanChangeManagement, "managed drawing and management mode cannot be replaced");
        vm.SelectedItem = fake.Printed;
        vm.EditCommand.Execute(null);
        vm.EditModel.IsUnprintedManaged = true;
        messages.ConfirmResult = false;
        Wait(vm.SaveCommand.ExecuteAsync());
        Check(fake.PatchCount == 0, "canceling explicit legacy conversion sends no write");
        messages.ConfirmResult = true;
        Wait(vm.SaveCommand.ExecuteAsync());
        Check(fake.PatchCount == 1 && vm.EditModel.ProductCode == "PRINT-001", "legacy conversion retains its existing code");
        fake.Printed.IsUnprintedManaged = false; // Restore the example printed row after the conversion scenario.
        CheckManagementFilters(vm, fake);

        var managed = fake.Products.Single(x => x.ProductId == 2);
        vm.SelectedItem = managed;
        var mappings = new PartnerProductMappingViewModel(api, messages, managed);
        Wait(mappings.RefreshAsync());
        Check(mappings.Items.Count == 0 && mappings.StatusText.Contains("없습니다"), "empty mappings have actionable guidance");
        mappings.SelectPartner(new OrderLinePartnerLookupDto { PartnerId = 1, Name = "A업체", PartnerType = "CUSTOMER" });
        mappings.ErpCode = " muji-100 ";
        mappings.CustomerName = "A용 무지";
        mappings.CustomerSpec = "100×200";
        fake.FailWrite = true;
        Wait(mappings.AddCommand.ExecuteAsync());
        Check(mappings.ErpCode == " muji-100 " && mappings.Items.Count == 0, "failed mapping preserves entered fields");
        fake.FailWrite = false;
        fake.PendingMapping = new TaskCompletionSource<ApiResult<PartnerProductMappingDto>>();
        var pending = mappings.AddCommand.ExecuteAsync();
        var writes = fake.MappingWrites;
        Wait(mappings.AddCommand.ExecuteAsync());
        Check(mappings.IsBusy && !mappings.CanEdit && fake.MappingWrites == writes, "pending mapping blocks duplicate submission");
        fake.PendingMapping.SetResult(new ApiResult<PartnerProductMappingDto> { Success = true, Data = fake.Mappings.Last() });
        Wait(pending);
        fake.PendingMapping = null;
        Check(fake.Mappings.Single().ErpProductCode == "MUJI-100" && mappings.Items.Count == 1, "partner ERP code is normalized and refreshed");
        Check(fake.LastGet.Contains("include_inactive=true"), "mapping list requests retained history with valid query parameters");
        mappings.SelectedMapping = mappings.Items[0];
        Wait(mappings.DeactivateCommand.ExecuteAsync());
        Check(!mappings.Items[0].IsActive && !mappings.DeactivateCommand.CanExecute(null), "deactivation retains visible history and disables repeated removal");
        for (int i = 2; i <= 43; i++) fake.Mappings.Add(new PartnerProductMappingDto { MappingId = i, PartnerId = i, PartnerName = $"거래처 {i}", ProductId = 2, ErpProductCode = "MUJI-100", CustomerProductName = "공용 무지", IsActive = true });
        Wait(mappings.RefreshAsync());
        Wait(mappings.NextCommand.ExecuteAsync());
        Check(mappings.Items.Count == 20 && mappings.PageText.StartsWith("2 / 3"), "mapping history supports pagination");
        Wait(mappings.PreviousCommand.ExecuteAsync());

        var bulk = new OrderLineBulkImportPageViewModel(api, messages);
        bulk.SourceRows.Add(new OrderLineBulkImportRowDto { RowNumber = 1, ErpOrderNo = "2026/10/19-1", PartnerName = "A업체", ProductCode = "MUJI-100", ErpProductDisplayName = "A용 무지 [100×200]", OrderQtyText = "100", DueDateText = "2026-10-31" });
        Wait(bulk.ValidateCommand.ExecuteAsync());
        Check(bulk.FlatRows.Single().MesProductCode == "MES-U000001" && bulk.FlatRows.Single().DrawingNo == "D-002", "bulk preview displays resolved internal code and drawing");
        Check(!bulk.FlatRows.Single().CanApplyProductNameChange && bulk.CanCommit, "different customer name is accepted without master-name overwrite");

        if (args.Length > 0)
        {
            fake.Mappings.Clear();
            fake.Mappings.Add(new PartnerProductMappingDto { MappingId = 100, ProductId = 2, PartnerId = 1, PartnerName = "A업체", ErpProductCode = "MUJI-100", CustomerProductName = "A용 무지 상자", CustomerProductSpec = "100×200", IsActive = true });
            fake.Mappings.Add(new PartnerProductMappingDto { MappingId = 101, ProductId = 2, PartnerId = 2, PartnerName = "B업체", ErpProductCode = "MUJI-100", CustomerProductName = "B용 포장재", CustomerProductSpec = "100×200", IsActive = true });
            Wait(mappings.RefreshAsync());
            Directory.CreateDirectory(args[0]);
            var errors = new BindingErrors();
            PresentationTraceSources.DataBindingSource.Listeners.Add(errors);
            PresentationTraceSources.DataBindingSource.Switch.Level = SourceLevels.Error;
            Render(new ProductPage { DataContext = vm }, Path.Combine(args[0], "product-registration.png"), 1440, 1000);
            var window = new PartnerProductMappingWindow(mappings);
            var content = (FrameworkElement)window.Content;
            window.Content = null;
            content.DataContext = mappings;
            content.Resources = window.Resources;
            Render(content, Path.Combine(args[0], "partner-mappings.png"), 1000, 680);
            Render(new OrderLineBulkImportPage { DataContext = bulk }, Path.Combine(args[0], "order-auto-match.png"), 1600, 700);
            Check(errors.Errors.Count == 0, "actual WPF controls render without binding errors: " + string.Join("; ", errors.Errors));
        }
        Wait(bulk.CommitCommand.ExecuteAsync());
        Check(fake.LastBulk?.RowChoices.Single().ExpectedProductId == 2 && fake.LastBulk.RowChoices.Single().ExpectedMappingId == 100, "bulk commit sends the reviewed product and mapping even when rename is disabled");
        Check(JsonSerializer.Serialize(fake.LastBulk).Contains("expected_mapping_id"), "wire contract includes mapping freshness check");
        Console.WriteLine($"Unprinted product regression checks: {_checks} passed");
    }
    private static void CheckManagementFilters(ProductPageViewModel vm, ProductsApi fake)
    {
        Check(vm.SelectedManagementMode == "전체" && !fake.LastProductListRoute.Contains("is_unprinted_managed="), "default management filter preserves the existing list contract");
        fake.Products.Add(new ProductDto { ProductId = 3, ProductCode = "BA0670187004", ProductName = "기존 코드 무지", IsUnprintedManaged = true, IsActive = true });
        fake.Products.Add(new ProductDto { ProductId = 4, ProductCode = "MES-U000004", ProductName = "공통 & 무지", IsUnprintedManaged = true, IsActive = false });
        vm.SelectedManagementMode = "무지 별도관리";
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(fake.LastProductListRoute.Contains("is_unprinted_managed=true") && vm.Items.Select(x => x.ProductId).SequenceEqual(new long[] { 3, 2 }), "managed filter includes converted legacy codes and excludes printed and inactive products");
        vm.SelectedItem = vm.Items[0];
        Check(vm.CanManagePartnerMappings, "filtered managed product still enables the existing partner and history window");

        vm.SelectedUseYn = "미사용";
        vm.SearchKeyword = "공통 & 무지";
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(vm.Items.Single().ProductId == 4 && vm.ListTotalCount == 1 && fake.LastProductListRoute.Contains("q=" + Uri.EscapeDataString(vm.SearchKeyword)), "management filter combines with inactive status and escaped search text");
        vm.SearchKeyword = "없는 품목";
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(vm.Items.Count == 0 && vm.ListTotalCount == 0 && !vm.ListHasNextPage, "empty filtered results clear the previous rows and count");

        vm.SearchKeyword = "";
        vm.SelectedUseYn = "사용";
        for (int id = 10; id < 110; id++)
            fake.Products.Add(new ProductDto { ProductId = id, ProductCode = $"MES-U{id:D6}", ProductName = "추가 무지", IsUnprintedManaged = true, IsActive = true });
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(vm.ListTotalCount == 102 && vm.Items.Count == 100 && vm.ListHasNextPage, "filtered total drives product pagination");
        Wait(vm.ListNextPageCommand.ExecuteAsync());
        Check(vm.ListPage == 2 && vm.Items.Select(x => x.ProductId).SequenceEqual(new long[] { 3, 2 }) && fake.LastProductListRoute.Contains("is_unprinted_managed=true"), "next page retains the management filter");
        vm.SelectedManagementMode = "기존 방식";
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(vm.ListPage == 1 && vm.Items.Single().ProductId == 1 && fake.LastProductListRoute.Contains("is_unprinted_managed=false"), "searching existing mode starts at page one and excludes managed items");
        vm.NewCommand.Execute(null);
        Check(vm.SelectedManagementMode == "기존 방식", "new product action preserves search filters");
        vm.ResetCommand.Execute(null);
        Check(vm.SelectedManagementMode == "전체" && vm.SelectedUseYn == "사용" && vm.SearchKeyword == "", "reset restores management and existing search defaults");
        Wait(vm.SearchCommand.ExecuteAsync());
        Check(vm.ListTotalCount == 103 && !fake.LastProductListRoute.Contains("is_unprinted_managed="), "all management modes removes only the management restriction");

        fake.Products.RemoveAll(x => x.ProductId >= 3);
        Wait(vm.SearchCommand.ExecuteAsync());
    }

    internal static void Render(FrameworkElement view, string path, double width, double height)
    {
        var host = new Border { Background = Brushes.White, Width = width, Height = height, Child = view };
        System.Windows.Documents.TextElement.SetFontFamily(host, new FontFamily("Malgun Gothic"));
        host.Measure(new Size(width, height)); host.Arrange(new Rect(0, 0, width, height)); host.UpdateLayout();
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
        var image = new RenderTargetBitmap((int)width, (int)height, 96, 96, PixelFormats.Pbgra32);
        image.Render(host);
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
        using var stream = File.Create(path); encoder.Save(stream);
    }
}

public class ProductsApi : DispatchProxy
{
    public ProductDto Printed = new() { ProductId = 1, ProductCode = "PRINT-001", ProductName = "기존 인쇄", DrawingId = 1, DrawingNo = "D-001", RoutingTemplateId = 1, Uom = "EA", IsActive = true };
    public List<ProductDto> Products = new();
    public List<PartnerProductMappingDto> Mappings = new();
    public ProductCreateRequest? LastProduct;
    public OrderLineBulkCommitRequest? LastBulk;
    public string LastGet = "";
    public string LastProductListRoute = "";
    public int PatchCount, MappingWrites;
    public bool FailWrite;
    public TaskCompletionSource<ApiResult<PartnerProductMappingDto>>? PendingMapping;
    protected override object? Invoke(MethodInfo? method, object?[]? args)
    {
        var name = method!.Name;
        var route = (string)args![0]!;
        var response = name == "DeleteAsync" ? typeof(bool) : method.GetGenericArguments().Last();
        object? data = null;
        bool success = true;
        if (name == "GetAsync")
        {
            LastGet = route;
            if (route.Contains("partner-mappings"))
            {
                int page = int.Parse(route.Split("page=")[1].Split('&')[0]);
                data = new PagedResult<PartnerProductMappingDto> { Items = Mappings.Skip((page - 1) * 20).Take(20).ToList(), Total = Mappings.Count, Page = page, Size = 20 };
            }
            else if (response == typeof(ProductListResponse))
            {
                LastProductListRoute = route;
                var query = route.Split('?')[1].Split('&').Select(part => part.Split('=', 2))
                    .ToDictionary(part => part[0], part => Uri.UnescapeDataString(part[1]));
                IEnumerable<ProductDto> rows = Products.Prepend(Printed);
                if (query.TryGetValue("is_active", out var active)) rows = rows.Where(x => x.IsActive == bool.Parse(active));
                if (query.TryGetValue("is_unprinted_managed", out var managed)) rows = rows.Where(x => x.IsUnprintedManaged == bool.Parse(managed));
                if (query.TryGetValue("q", out var keyword)) rows = rows.Where(x => x.ProductCode.Contains(keyword, StringComparison.OrdinalIgnoreCase) || x.ProductName.Contains(keyword, StringComparison.OrdinalIgnoreCase));
                var matches = rows.OrderByDescending(x => x.ProductId).ToList();
                int page = int.Parse(query["page"]), size = int.Parse(query["size"]);
                data = new ProductListResponse { Items = matches.Skip((page - 1) * size).Take(size).ToList(), Total = matches.Count, Page = page, Size = size };
            }
            else if (response == typeof(DrawingDto))
                data = new DrawingDto { DrawingId = long.Parse(route.Split('/').Last()), DrawingNo = route.EndsWith("/2") ? "D-002" : "D-001", IsActive = true };
            else data = Activator.CreateInstance(response);
        }
        else if (name == "PostAsync" && args[1] is ProductCreateRequest product)
        {
            LastProduct = product;
            var saved = new ProductDto { ProductId = 2, ProductCode = "MES-U000001", ProductName = product.ProductName, IsUnprintedManaged = true, DrawingId = 2, DrawingNo = "D-002", RoutingTemplateId = 1, Uom = "EA", IsActive = true };
            Products.Add(saved); data = saved;
        }
        else if (name == "PatchAsync")
        {
            PatchCount++; Printed.IsUnprintedManaged = true; data = Printed;
        }
        else if (name == "PostAsync" && args[1] is PartnerProductMappingCreateRequest mapping)
        {
            MappingWrites++;
            success = !FailWrite;
            if (success)
            {
                var saved = new PartnerProductMappingDto { MappingId = Mappings.Count + 1, ProductId = 2, PartnerId = mapping.PartnerId, PartnerName = "A업체", ErpProductCode = mapping.ErpProductCode, CustomerProductName = mapping.CustomerProductName, CustomerProductSpec = mapping.CustomerProductSpec, IsActive = true };
                Mappings.Add(saved); data = saved;
                if (PendingMapping != null) return PendingMapping.Task;
            }
        }
        else if (name == "DeleteAsync")
        {
            Mappings.Single(x => x.MappingId == long.Parse(route.Split('/').Last())).IsActive = false; data = true;
        }
        else if (response == typeof(OrderLineBulkValidateResultDto))
        {
            data = new OrderLineBulkValidateResultDto { TotalRowCount = 1, ReadyRowCount = 1, Groups = new() { new OrderLineBulkValidateGroupDto { ErpOrderNo = "2026/10/19-1", CanCommit = true, Status = "READY", Rows = new() { new OrderLineBulkValidateRowDto { RowNumber = 1, ErpOrderNo = "2026/10/19-1", PartnerName = "A업체", ProductId = 2, MappingId = 100, ProductCode = "MUJI-100", MesProductCode = "MES-U000001", DrawingNo = "D-002", ErpProductDisplayName = "A용 무지 [100×200]", MesProductDisplayName = "공통 무지 상자 [100×200]", OrderQty = 100, IsUnprintedManaged = true, Status = "READY" } } } } };
        }
        else if (args.Length > 1 && args[1] is OrderLineBulkCommitRequest commit)
        {
            LastBulk = commit;
            data = new OrderLineBulkCommitResultDto { TotalGroupCount = 1, SuccessGroupCount = 1, Groups = new() { new OrderLineBulkCommitGroupResultDto { ErpOrderNo = "2026/10/19-1", Status = "SUCCESS" } } };
        }
        return typeof(ProductsApi).GetMethod(nameof(Result), BindingFlags.NonPublic | BindingFlags.Static)!.MakeGenericMethod(response).Invoke(null, new[] { data, success });
    }
    private static Task<ApiResult<T>> Result<T>(object? data, bool success) => Task.FromResult(new ApiResult<T> { Success = success, Data = data is T value ? value : default, Message = success ? null : "테스트 오류" });
}
internal class Messages : IMessageService
{
    public bool ConfirmResult = true;
    public void ShowInfo(string message, string title = "알림") { }
    public void ShowWarning(string message, string title = "경고") { Console.WriteLine("Test warning: " + message); }
    public void ShowError(string message, string title = "오류") { Console.WriteLine("Expected/test message: " + message); }
    public bool Confirm(string message, string title = "확인") => ConfirmResult;
}
internal class DrawingViewer : IDrawingViewer { public Task OpenCurrentDrawingAsync(long id) => Task.CompletedTask; }
internal class BindingErrors : TraceListener
{
    public List<string> Errors = new();
    public override void Write(string? message) { if (!string.IsNullOrEmpty(message)) Errors.Add(message); }
    public override void WriteLine(string? message) { if (!string.IsNullOrEmpty(message)) Errors.Add(message); }
}
