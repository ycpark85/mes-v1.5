using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.Drawings.Dtos;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;
using Mes.Wpf.Modules.InspectionSchedules.ViewModels;
using Mes.Wpf.Modules.InspectionSchedules.Views;
using Mes.Wpf.Modules.OrderLineList.Dtos;
using Mes.Wpf.Modules.OrderLineList.ViewModels;
using Mes.Wpf.Modules.OrderLineList.Views;
using Mes.Wpf.Modules.OrderLines.Dtos;
using Mes.Wpf.Modules.OrderLines.ViewModels;
using Mes.Wpf.Modules.OrderLines.Views;
using Mes.Wpf.Modules.Products.Dtos;
using Mes.Wpf.Modules.Products.ViewModels;
using Mes.Wpf.Modules.Products.Views;
using Mes.Wpf.Modules.RoutingTemplates.Dtos;
using Mes.Wpf.Modules.Shipments.Dtos;
using Mes.Wpf.Modules.Shipments.ViewModels;
using Mes.Wpf.Modules.Shipments.Views;

// Reproducible screenshots of the production views with isolated, in-memory example responses.
// This walkthrough never opens a connection to a business database or sends network requests.
internal static class SharedCodeWalkthrough
{
    internal static void Run(string directory)
    {
        Directory.CreateDirectory(directory);
        var errors = new BindingErrors();
        PresentationTraceSources.DataBindingSource.Listeners.Add(errors);
        PresentationTraceSources.DataBindingSource.Switch.Level = SourceLevels.Error;
        var api = DispatchProxy.Create<IApiClient, SharedCodeExampleApi>();
        var example = (SharedCodeExampleApi)(object)api;
        var messages = new Messages();
        var products = new ProductPageViewModel(api, messages, new DrawingViewer());
        Program.Wait(products.InitializeAsync());
        products.EditModel.IsUnprintedManaged = true;
        products.EditModel.ProductName = "공통 무지 상자";
        products.EditModel.ProductSpec = "100×200";
        products.EditModel.Uom = "EA";
        products.SelectDrawing(new DrawingDto { DrawingId = 2, DrawingNo = "D-002", IsActive = true });
        products.EditModel.RoutingTemplateId = 1;
        Program.Render(new ProductPage { DataContext = products }, Path.Combine(directory, "01-product-input.png"), 1440, 1000);

        Program.Wait(products.SaveCommand.ExecuteAsync());
        var product = products.SelectedItem ?? throw new Exception("Example product was not saved.");
        if (product.ProductCode != "MES-U000001" || !products.CanManagePartnerMappings)
            throw new Exception("Example product did not enable partner linking.");
        Program.Render(new ProductPage { DataContext = products }, Path.Combine(directory, "02-product-saved.png"), 1440, 1000);

        var mappings = new PartnerProductMappingViewModel(api, messages, product);
        Program.Wait(mappings.RefreshAsync());
        mappings.SelectPartner(new OrderLinePartnerLookupDto { PartnerId = 1, Name = "A업체", PartnerType = "CUSTOMER" });
        mappings.ErpCode = "MUJI-100";
        mappings.CustomerName = "A용 무지 상자";
        mappings.CustomerSpec = "100×200";
        Program.Wait(mappings.AddCommand.ExecuteAsync());
        mappings.SelectPartner(new OrderLinePartnerLookupDto { PartnerId = 2, Name = "B업체", PartnerType = "CUSTOMER" });
        mappings.ErpCode = "MUJI-100";
        mappings.CustomerName = "B용 포장재";
        mappings.CustomerSpec = "100×200";
        RenderMappings(mappings, Path.Combine(directory, "03-add-partner-b.png"));
        Program.Wait(mappings.AddCommand.ExecuteAsync());
        if (mappings.Items.Count != 2 || mappings.Items.Any(x => x.ProductId != product.ProductId))
            throw new Exception("Both example partners must link to the same product.");
        RenderMappings(mappings, Path.Combine(directory, "04-partners-linked.png"));

        var bulk = new OrderLineBulkImportPageViewModel(api, messages);
        bulk.SelectedFilePath = "예시_무지수주_AB.xlsx";
        bulk.SourceRows.Add(new OrderLineBulkImportRowDto { RowNumber = 1, ErpOrderNo = "2026/10/19-1", PartnerName = "A업체", ProductCode = "MUJI-100", ErpProductDisplayName = "A용 무지 상자 [100×200]", OrderQtyText = "1000", DueDateText = "2026-10-31" });
        bulk.SourceRows.Add(new OrderLineBulkImportRowDto { RowNumber = 2, ErpOrderNo = "2026/10/19-2", PartnerName = "B업체", ProductCode = "MUJI-100", ErpProductDisplayName = "B용 포장재 [100×200]", OrderQtyText = "2000", DueDateText = "2026-10-31" });
        Program.Wait(bulk.ValidateCommand.ExecuteAsync());
        if (!bulk.CanCommit || bulk.ReadyRowCount != 2 || bulk.FlatRows.Any(x => x.ProductId != product.ProductId || x.CanApplyProductNameChange))
            throw new Exception("The example preview must retain partner names and resolve one product.");
        Program.Render(new OrderLineBulkImportPage { DataContext = bulk }, Path.Combine(directory, "05-orders-validated.png"), 1600, 420);
        Program.Wait(bulk.CommitCommand.ExecuteAsync());
        if (bulk.CommitResult?.SuccessGroupCount != 2 || example.Orders.Count != 2 || bulk.SourceRows.Count != 0)
            throw new Exception("Both example orders must be committed and removed from the upload list.");
        var orders = new OrderLineListPageViewModel(api, messages);
        Program.Wait(orders.InitializeAsync());
        if (orders.Items.Select(x => x.ProductName).Distinct().Count() != 2 || orders.Items.Select(x => x.ProductId).Distinct().Count() != 1)
            throw new Exception("The order list must retain different customer names for one MES product.");
        if (orders.Items.Any(x => x.ProductCode != "MUJI-100" || x.MesProductCode != "MES-U000001"))
            throw new Exception("The order list must show the business code and MES code separately.");
        Program.Render(new OrderLineListPage { DataContext = orders }, Path.Combine(directory, "06-orders-registered.png"), 1600, 760);

        var inspection = new InspectionResultWindowViewModel(api, messages);
        Program.Wait(inspection.InitializeAsync(1, "LOT-20261019-002", "B용 포장재", "B업체",
            new DateTime(2026, 10, 30), 2000, new DateTime(2026, 10, 31), 2000));
        if (inspection.ProductCode != "MUJI-100" || inspection.MesProductCode != "MES-U000001" || !inspection.InventorySummaryAvailable)
            throw new Exception("Inspection registration must show both codes from the order without changing inventory.");
        var inspectionWindow = new InspectionResultWindow(inspection);
        var inspectionContent = (FrameworkElement)inspectionWindow.Content;
        inspectionWindow.Content = null;
        inspectionContent.DataContext = inspection;
        inspectionContent.Resources = inspectionWindow.Resources;
        Program.Render(inspectionContent, Path.Combine(directory, "07-inspection-result.png"), 1180, 820);
        var shipments = new ShipmentPageViewModel(api, messages);
        Program.Wait(shipments.InitializeAsync());
        if (shipments.Items.Count != 1 || shipments.Items[0].ProductCode != "MUJI-100" || shipments.Items[0].MesProductCode != "MES-U000001")
            throw new Exception("Grouped shipment rows must preserve both business and MES codes.");
        Program.Render(new ShipmentPage { DataContext = shipments }, Path.Combine(directory, "08-shipments.png"), 1600, 760);
        if (errors.Errors.Count > 0) throw new Exception(string.Join("; ", errors.Errors));
        PresentationTraceSources.DataBindingSource.Listeners.Remove(errors);
        Console.WriteLine("PASS: shared-code walkthrough; 1 product, 2 partner connections, 2 example orders; separate business/MES codes through inspection and shipment; 8 actual view renders; no binding errors.");
    }

    private static void RenderMappings(PartnerProductMappingViewModel mappings, string path)
    {
        var window = new PartnerProductMappingWindow(mappings);
        var content = (FrameworkElement)window.Content;
        window.Content = null;
        content.DataContext = mappings;
        content.Resources = window.Resources;
        Program.Render(content, path, 1000, 680);
    }
}

public class SharedCodeExampleApi : ProductsApi
{
    public List<OrderLineListItemDto> Orders { get; } = new();

    protected override object? Invoke(MethodInfo? method, object?[]? args)
    {
        var response = method!.Name == "DeleteAsync" ? typeof(bool) : method.GetGenericArguments().Last();
        if (method.Name == "GetAsync" && response == typeof(PagedResult<RoutingTemplateDto>))
            return Task.FromResult(new ApiResult<PagedResult<RoutingTemplateDto>> { Success = true, Data = new() { Items = new() { new() { RoutingTemplateId = 1, TemplateCode = "UNPRINTED", TemplateName = "무지 도무송", IsActive = true } }, Total = 1, Page = 1, Size = 100 } });
        if (method.Name == "GetAsync" && response == typeof(OrderLineListResponse))
            return Task.FromResult(new ApiResult<OrderLineListResponse> { Success = true, Data = new() { Items = Orders.ToList(), Meta = new() { Page = 1, Size = 20, Total = Orders.Count }, QueueCounts = new() { ["lot_creation"] = Orders.Count, ["close_decision"] = 0 } } });
        if (method.Name == "GetAsync" && response == typeof(InspectionResultResponse))
            return Task.FromResult(new ApiResult<InspectionResultResponse> { Success = true, Data = new() {
                ProductCode = "MUJI-100", MesProductCode = "MES-U000001", ScheduleStatus = "RECEIVED",
                InspectionRound = 1, InspectionRoundCount = 1,
                Inventory = new() { ViewMode = "edit", StockLots = new(), ProductId = 2, OrderLineId = 2,
                    OrderQty = 2000, ShipTargetQty = 2000, RemainingBeforeCurrentResultQty = 2000 }
            } });
        if (method.Name == "GetAsync" && response == typeof(ShipmentLineListResponse))
            return Task.FromResult(new ApiResult<ShipmentLineListResponse> { Success = true, Data = new() {
                Total = 1, Page = 1, Size = 50, Items = new() { new() {
                    OrderLineId = 2, OrderNo = "2026/10/19-2", PartnerName = "B업체", ProductName = "B용 포장재",
                    ProductCode = "MUJI-100", MesProductCode = "MES-U000001", Status = "WAITING", SourceType = "INSPECTION_RESULT", ShipQty = 2000
                } }
            } });
        if (args!.Length > 1 && args[1] is OrderLineBulkValidateRequest validation)
        {
            var preview = new OrderLineBulkValidateResultDto { TotalRowCount = validation.Items.Count, ReadyRowCount = validation.Items.Count };
            foreach (var row in validation.Items)
            {
                var mapping = Mappings.Single(x => x.PartnerName == row.PartnerName && x.ErpProductCode == row.ProductCode && x.IsActive);
                var product = Products.Single(x => x.ProductId == mapping.ProductId);
                preview.Groups.Add(new() { ErpOrderNo = row.ErpOrderNo, PartnerName = row.PartnerName, PartnerId = mapping.PartnerId, Status = "READY", CanCommit = true, Rows = new() { new() {
                    RowNumber = row.RowNumber, ErpOrderNo = row.ErpOrderNo, PartnerName = row.PartnerName, PartnerId = mapping.PartnerId,
                    ProductId = product.ProductId, MappingId = mapping.MappingId, ProductCode = row.ProductCode, MesProductCode = product.ProductCode,
                    DrawingNo = product.DrawingNo, ErpProductDisplayName = row.ErpProductDisplayName, MesProductDisplayName = $"{product.ProductName} [{product.ProductSpec}]",
                    OrderQty = int.Parse(row.OrderQtyText), IsUnprintedManaged = true, Status = "READY"
                } } });
            }
            return Task.FromResult(new ApiResult<OrderLineBulkValidateResultDto> { Success = true, Data = preview });
        }
        if (args.Length > 1 && args[1] is OrderLineBulkCommitRequest commit)
        {
            LastBulk = commit;
            var result = new OrderLineBulkCommitResultDto { TotalGroupCount = commit.Items.Count, SuccessGroupCount = commit.Items.Count };
            foreach (var row in commit.Items)
            {
                var mapping = Mappings.Single(x => x.PartnerName == row.PartnerName && x.ErpProductCode == row.ProductCode && x.IsActive);
                var choice = commit.RowChoices.Single(x => x.RowNumber == row.RowNumber);
                if (choice.ExpectedMappingId != mapping.MappingId || choice.ExpectedProductId != mapping.ProductId || choice.ApplyProductNameChange)
                    throw new Exception("Unexpected example commit selection.");
                var product = Products.Single(x => x.ProductId == mapping.ProductId);
                var quantity = int.Parse(row.OrderQtyText);
                Orders.Add(new() { OrderLineId = Orders.Count + 1, OrderNo = row.ErpOrderNo, LineNo = 1, PartnerId = mapping.PartnerId, PartnerName = row.PartnerName,
                    ProductId = product.ProductId, ProductCode = row.ProductCode, MesProductCode = product.ProductCode, ProductName = mapping.CustomerProductName,
                    SourceErpProductCode = row.ProductCode, SourceProductName = mapping.CustomerProductName, SourceProductSpec = mapping.CustomerProductSpec,
                    OrderDate = new DateTime(2026, 10, 19), DueDate = new DateTime(2026, 10, 31), OrderQty = quantity, Uom = "EA", Status = "OPEN", IsActive = true,
                    TargetShipQty = quantity, ShipTargetQty = quantity, RemainingShipQty = quantity, RecommendedProductionQty = quantity,
                    RecommendedFulfillmentMode = "PRODUCTION_FIRST", DecisionRequired = true, WorkQueue = "LOT_CREATION" });
                result.Groups.Add(new() { ErpOrderNo = row.ErpOrderNo, Status = "SUCCESS", CreatedOrderLineIds = new() { Orders.Last().OrderLineId } });
            }
            return Task.FromResult(new ApiResult<OrderLineBulkCommitResultDto> { Success = true, Data = result });
        }
        var task = base.Invoke(method, args);
        if (args.Length > 1 && args[1] is ProductCreateRequest productRequest)
        {
            Products.Last().ProductSpec = productRequest.ProductSpec;
            Products.Last().RoutingTemplateName = "무지 도무송";
        }
        if (args.Length > 1 && args[1] is PartnerProductMappingCreateRequest mappingRequest)
            Mappings.Last().PartnerName = mappingRequest.PartnerId == 1 ? "A업체" : "B업체";
        return task;
    }
}
