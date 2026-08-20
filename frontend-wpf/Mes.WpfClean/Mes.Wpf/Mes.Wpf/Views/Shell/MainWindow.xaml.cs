using Mes.Wpf.Core.Configuration;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Infrastructure.Api;
using Mes.Wpf.Infrastructure.Dialogs;
using Mes.Wpf.Modules.Auth.Dtos;
using Mes.Wpf.Modules.BohyunOutsourceManagement.ViewModels;
using Mes.Wpf.Modules.BohyunOutsourceManagement.Views;
using Mes.Wpf.Modules.Dashboard.ViewModels;
using Mes.Wpf.Modules.Dashboard.Views;
using Mes.Wpf.Modules.DefectTypes.ViewModels;
using Mes.Wpf.Modules.Drawings.ViewModels;
using Mes.Wpf.Modules.Drawings.Views;
using Mes.Wpf.Modules.InspectionSchedules.ViewModels;
using Mes.Wpf.Modules.InspectionSchedules.Views;
using Mes.Wpf.Modules.Inventories.ViewModels;
using Mes.Wpf.Modules.Inventories.Views;
using Mes.Wpf.Modules.LotDetails.ViewModels;
using Mes.Wpf.Modules.LotDetails.Views;
using Mes.Wpf.Modules.Lots.ViewModels;
using Mes.Wpf.Modules.Lots.Views;
using Mes.Wpf.Modules.OrderLineList.Dtos;
using Mes.Wpf.Modules.OrderLineList.ViewModels;
using Mes.Wpf.Modules.OrderLineList.Views;
using Mes.Wpf.Modules.OrderLines.ViewModels;
using Mes.Wpf.Modules.OrderLines.Views;
using Mes.Wpf.Modules.OutsourceWorkInstructions.ViewModels;
using Mes.Wpf.Modules.OutsourceWorkInstructions.Views;
using Mes.Wpf.Modules.OutsourceProcessingCosts.ViewModels;
using Mes.Wpf.Modules.OutsourceProcessingCosts.Views;
using Mes.Wpf.Modules.Partners.ViewModels;
using Mes.Wpf.Modules.Partners.Views;
using Mes.Wpf.Modules.Processes.ViewModels;
using Mes.Wpf.Modules.Processes.Views;
using Mes.Wpf.Modules.Products.ViewModels;
using Mes.Wpf.Modules.Products.Views;
using Mes.Wpf.Modules.ProductionDaily.ViewModels;
using Mes.Wpf.Modules.ProductionDaily.Views;
using Mes.Wpf.Modules.Roles.ViewModels;
using Mes.Wpf.Modules.Roles.Views;
using Mes.Wpf.Modules.RoutingTemplates.ViewModels;
using Mes.Wpf.Modules.RoutingTemplates.Views;
using Mes.Wpf.Modules.Shipments.Dtos;
using Mes.Wpf.Modules.Shipments.ViewModels;
using Mes.Wpf.Modules.Shipments.Views;
using Mes.Wpf.Modules.Users.ViewModels;
using Mes.Wpf.Modules.Users.Views;
using Mes.Wpf.Modules.MyPage.ViewModels;
using Mes.Wpf.Modules.MyPage.Views;


using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;

namespace Mes.Wpf.Views.Shell
{
    public partial class MainWindow : Window
    {
        private readonly ApiClient _apiClient;
        private readonly MessageService _messageService;
        private readonly AuthLoginResponse? _loginResponse;
        private readonly HashSet<string> _permissionCodes = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly DefectTypePageViewModel _defectTypePageViewModel;
        private readonly RoutingTemplatePageViewModel _routingTemplatePageViewModel;
        private readonly DrawingFileOpener _drawingFileOpener;
        private readonly DrawingViewer _drawingViewer;

        public MainWindow()
    : this(null, null, null)
        {
        }

        public MainWindow(
            ApiClient? apiClient,
            MessageService? messageService,
            AuthLoginResponse? loginResponse)
        {
            InitializeComponent();

            if (apiClient == null)
            {
                var appSettings = AppSettings.Load();
                _apiClient = new ApiClient(appSettings.Api);
            }
            else
            {
                _apiClient = apiClient;
            }

            _messageService = messageService ?? new MessageService();
            _loginResponse = loginResponse;
            LoadPermissions(_loginResponse);


            if (_loginResponse?.User != null)
            {
                Title = $"MES - {_loginResponse.User.UserName}";
            }

            _drawingFileOpener = new DrawingFileOpener(_apiClient, _messageService);

            _drawingViewer = new DrawingViewer(
                _apiClient,
                _messageService,
                _drawingFileOpener);

            _defectTypePageViewModel = new DefectTypePageViewModel(
                _apiClient,
                _messageService);

            _routingTemplatePageViewModel = new RoutingTemplatePageViewModel(
                _apiClient,
                _messageService);

            Loaded += MainWindow_Loaded;
        }

        private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
        {
            ApplyMenuPermissions();

            if (_loginResponse?.User?.PasswordChangeRequired == true)
            {
                var changed = OpenPasswordChangeWindow(true);

                if (!changed)
                {
                    Close();
                    return;
                }

                _loginResponse.User.PasswordChangeRequired = false;
            }

            if (HasPermission(PermissionCodes.DashboardView))
            {
                await ShowDashboardAsync();
                return;
            }

            HeaderTitle.Text = "MES";
            HeaderSubtitle.Text = "접근 가능한 메뉴를 선택하세요.";
            MainContent.Content = null;
        }

        private void MenuExpander_Expanded(object sender, RoutedEventArgs e)
        {
            if (sender is not Expander openedExpander)
            {
                return;
            }

            CollapseAllSidebarExpanders(openedExpander);
        }

        private void CollapseAllSidebarExpanders(Expander? exceptExpander = null)
        {
            if (SidebarMenuStack == null)
            {
                return;
            }

            foreach (var child in SidebarMenuStack.Children)
            {
                if (child is Expander expander &&
                    !ReferenceEquals(expander, exceptExpander))
                {
                    expander.IsExpanded = false;
                }
            }
        }

        private async void Dashboard_Click(object sender, RoutedEventArgs e)
        {
            CollapseAllSidebarExpanders();

            await ShowDashboardAsync();
        }

        private void MyPage_Click(object sender, RoutedEventArgs e)
        {
            ShowMyPage();
        }

        private void ShowMyPage()
        {
            CollapseAllSidebarExpanders();

            var page = new MyPage();
            var viewModel = new MyPageViewModel(
                _loginResponse?.User,
                isRequired => OpenPasswordChangeWindow(isRequired));

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "마이페이지";
            HeaderSubtitle.Text = "내 정보 확인 및 비밀번호 변경";
        }

        private bool OpenPasswordChangeWindow(bool isRequired)
        {
            var viewModel = new PasswordChangeWindowViewModel(
                _apiClient,
                _messageService,
                isRequired);

            var window = new PasswordChangeWindow(viewModel)
            {
                Owner = this
            };

            var result = window.ShowDialog();

            if (result == true && window.ChangedAuthContext?.User != null && _loginResponse?.User != null)
            {
                _loginResponse.AccessToken = window.ChangedAuthContext.AccessToken;
                _loginResponse.TokenType = window.ChangedAuthContext.TokenType;
                _loginResponse.ExpiresInMinutes = window.ChangedAuthContext.ExpiresInMinutes;
                _loginResponse.User.PasswordChangeRequired = window.ChangedAuthContext.User.PasswordChangeRequired;
                return true;
            }

            return result == true;
        }

        private void DefectType_Click(object sender, RoutedEventArgs e)
        {
            ShowDefectType();
        }

        private async void Process_Click(object sender, RoutedEventArgs e)
        {
            var processPage = new ProcessPage();
            var processViewModel = new ProcessPageViewModel(
                _apiClient,
                _messageService);

            processPage.DataContext = processViewModel;

            MainContent.Content = processPage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "공정 관리";
            HeaderSubtitle.Text = "공정 마스터 등록 / 조회 / 수정 / 삭제";

            await processViewModel.InitializeAsync();
        }

        private async void Partner_Click(object sender, RoutedEventArgs e)
        {
            var partnerPage = new PartnerPage();
            var partnerViewModel = new PartnerPageViewModel(
                _apiClient,
                _messageService);

            partnerPage.DataContext = partnerViewModel;

            MainContent.Content = partnerPage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "거래처 관리";
            HeaderSubtitle.Text = "거래처 마스터 등록 / 조회 / 수정 / 삭제 / 벌크업로드";

            await partnerViewModel.InitializeAsync();
        }

        private async void RoutingTemplate_Click(object sender, RoutedEventArgs e)
        {
            var routingTemplatePage = new RoutingTemplatePage();
            var routingTemplateViewModel = new RoutingTemplatePageViewModel(
                _apiClient,
                _messageService);

            routingTemplatePage.DataContext = routingTemplateViewModel;

            MainContent.Content = routingTemplatePage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "라우팅 템플릿 관리";
            HeaderSubtitle.Text = "라우팅 템플릿 마스터 등록 / 조회 / 수정 / 삭제";

            await routingTemplateViewModel.InitializeAsync();
        }

        private void ShowDefectType()
        {
            var defectTypePage = new Modules.DefectTypes.Views.DefectTypePage();
            defectTypePage.DataContext = _defectTypePageViewModel;

            MainContent.Content = defectTypePage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "불량유형 관리";
            HeaderSubtitle.Text = "불량유형 마스터 등록 / 조회 / 수정 / 삭제";
        }

        private async Task ShowDashboardAsync()
        {
            var page = new DashboardPage();

            var viewModel = new DashboardPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "메인 대시보드";
            HeaderSubtitle.Text = "발주 · LOT · 외주 · 검수 · 품질 현황";

            await viewModel.InitializeAsync();
        }

        private async void RoutingTemplateStep_Click(object sender, RoutedEventArgs e)
        {
            var routingTemplateStepPage = new RoutingTemplateStepPage();
            var routingTemplateStepViewModel = new RoutingTemplateStepPageViewModel(
                _apiClient,
                _messageService);

            routingTemplateStepPage.DataContext = routingTemplateStepViewModel;

            MainContent.Content = routingTemplateStepPage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "라우팅 Step 관리";
            HeaderSubtitle.Text = "라우팅 템플릿별 Step 등록 / 조회 / 수정 / 삭제";

            await routingTemplateStepViewModel.InitializeAsync();
        }

        private async void Drawing_Click(object sender, RoutedEventArgs e)
        {
            var drawingPage = new DrawingPage();

            var drawingViewModel = new DrawingPageViewModel(
                _apiClient,
                _messageService,
                _drawingFileOpener);

            drawingPage.DataContext = drawingViewModel;

            MainContent.Content = drawingPage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "도면 관리";
            HeaderSubtitle.Text = "도면 / 리비전 / 파일 등록 / 조회 / 수정";

            await drawingViewModel.InitializeAsync();
        }

        private async void PendingNewDrawing_Click(object sender, RoutedEventArgs e)
        {
            var page = new PendingNewDrawingPage();

            var viewModel = new PendingNewDrawingPageViewModel(
                _apiClient,
                _messageService,
                _drawingFileOpener);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "신규작성도면";
            HeaderSubtitle.Text = "품목에 매칭되었지만 도면파일이 아직 등록되지 않은 도면 목록";

            await viewModel.InitializeAsync();
        }

        private async void Product_Click(object sender, RoutedEventArgs e)
        {
            var productPage = new ProductPage();

            var productViewModel = new ProductPageViewModel(
                _apiClient,
                _messageService,
                _drawingViewer);

            productPage.DataContext = productViewModel;

            MainContent.Content = productPage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "품목 관리";
            HeaderSubtitle.Text = "품목 마스터 등록 / 조회 / 수정 / 삭제 / 벌크업로드";

            await productViewModel.InitializeAsync();
        }

        private async void OrderLineCreate_Click(object sender, RoutedEventArgs e)
        {
            var page = new OrderLineCreatePage();

            var viewModel = new OrderLineCreatePageViewModel(
                _apiClient,
                _messageService,
                _drawingViewer);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "수주 등록";
            HeaderSubtitle.Text = "수주 헤더 / 수주 라인 등록";

            await viewModel.InitializeAsync();
        }

        private async void OrderLineList_Click(object sender, RoutedEventArgs e)
        {
            await OpenOrderLineListAsync();
        }

        private async Task OpenOrderLineDetailAsync(long orderLineId)
        {
            var page = new OrderLineDetailPage();

            var vm = new OrderLineDetailPageViewModel(
                _apiClient,
                _messageService,
                async () => await OpenOrderLineListAsync());

            page.DataContext = vm;

            MainContent.Content = page;

            await vm.InitializeAsync(orderLineId);
        }

        private async Task OpenOrderLineListAsync()
        {
            var page = new OrderLineListPage();

            var vm = new OrderLineListPageViewModel(
                _apiClient,
                _messageService,
                async orderLineId => await OpenOrderLineDetailWindowAsync(orderLineId),
                async item => await OpenLotCreateWindowAsync(item));

            page.DataContext = vm;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "발주리스트";
            HeaderSubtitle.Text = "수주라인 조회 / 발주상세 / LOT 생성";

            await vm.InitializeAsync();
        }

        private async Task OpenLotCreateWindowAsync(OrderLineListItemDto item)
        {
            var vm = new LotCreateWindowViewModel(
                _apiClient,
                _messageService,
                _drawingViewer,
                _drawingFileOpener);

            var window = new LotCreateWindow(vm)
            {
                Owner = this
            };

            await vm.InitializeAsync(item.OrderLineId);

            window.ShowDialog();

            await OpenOrderLineListAsync();
        }

        private async void LotProcess_Click(object sender, RoutedEventArgs e)
        {
            var page = new LotPage();
            var viewModel = new LotPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "LOT 공정관리";
            HeaderSubtitle.Text = "LOT 조회 / 공정 진행상태 확인 / 외주공정 시작 / 완료";

            await viewModel.InitializeAsync();
        }

        private async void ProductionDaily_Click(object sender, RoutedEventArgs e)
        {
            var page = new ProductionDailyPage();
            var viewModel = new ProductionDailyPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "생산진행현황";
            HeaderSubtitle.Text = "검수 완료 전 생산 진행현황";

            await viewModel.InitializeAsync();
        }

        private async void InspectionWorkInstruction_Click(object sender, RoutedEventArgs e)
        {
            var inspectionWorkInstructionPage = new InspectionWorkInstructionPage();

            var inspectionWorkInstructionViewModel =
                new InspectionWorkInstructionPageViewModel(
                    _apiClient,
                    _messageService);

            inspectionWorkInstructionPage.DataContext = inspectionWorkInstructionViewModel;

            MainContent.Content = inspectionWorkInstructionPage;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "검수 작업지시 / 등록";
            HeaderSubtitle.Text = "최초 검수일정이 등록되지 않은 LOT 기준 검수 작업지시 등록";

            await inspectionWorkInstructionViewModel.InitializeAsync();
        }

        private async void InspectionScheduleManagement_Click(object sender, RoutedEventArgs e)
        {
            var view = new InspectionScheduleManagementView();

            var viewModel = new InspectionScheduleManagementPageViewModel(
                _apiClient,
                _messageService,
                _drawingViewer,
                HasPermission(PermissionCodes.InspectionsWrite));

            view.DataContext = viewModel;

            MainContent.Content = view;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "검수 스케줄 관리";
            HeaderSubtitle.Text = "검수 일정 조회 / 일정변경 / 입고완료 / 검수시작 / 취소 / 순서변경";

            await viewModel.InitializeAsync();
        }

        private async void InspectionResultManagement_Click(object sender, RoutedEventArgs e)
        {
            var view = new InspectionResultManagementView();

            var viewModel = new InspectionResultManagementPageViewModel(
                _apiClient,
                _messageService,
                HasPermission(PermissionCodes.InspectionsWrite));

            view.DataContext = viewModel;

            MainContent.Content = view;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "검수실적관리";
            HeaderSubtitle.Text = "검수 완료 실적 조회 / 상세보기 / 실적 수정";

            await viewModel.InitializeAsync();
        }

        private async void OutsourceWorkInstruction_Click(object sender, RoutedEventArgs e)
        {
            var page = new OutsourceWorkInstructionPage();

            var viewModel = new OutsourceWorkInstructionPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "외주 작업지시 등록";
            HeaderSubtitle.Text = "후보 LOT 조회 / 묶음·개별 작업지시 생성 / 파일 첨부 / 일괄 저장";

            await viewModel.InitializeAsync();
        }

        private async void OutsourcePurchaseOrder_Click(object sender, RoutedEventArgs e)
        {
            var page = new OutsourcePurchaseOrderPage();

            var viewModel = new OutsourcePurchaseOrderPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "외주 발주서 작성 / 출력";
            HeaderSubtitle.Text = "재단 / 인쇄 발주 대상 조회 / 발주서 헤더·상세 입력 / 출력";

            await viewModel.InitializeAsync();
        }

        private async void OutsourcePurchaseOrderList_Click(object sender, RoutedEventArgs e)
        {
            var view = new OutsourcePurchaseOrderListView();

            var viewModel = new OutsourcePurchaseOrderListPageViewModel(
                _apiClient,
                _messageService);

            view.DataContext = viewModel;

            MainContent.Content = view;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "외주발주 리스트";
            HeaderSubtitle.Text = "저장된 외주발주 목록 조회 / 발주서 엑셀 다운로드";

            await viewModel.InitializeAsync();
        }

        private async void BohyunOutsourceManagement_Click(object sender, RoutedEventArgs e)
        {
            var view = new BohyunOutsourceManagementView();

            var viewModel = new BohyunOutsourceManagementViewModel(
                _apiClient,
                _messageService);

            view.DataContext = viewModel;

            MainContent.Content = view;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "보현문화 외주관리";
            HeaderSubtitle.Text = "보현문화 입고 / 작업완료 / 출고 처리";

            await viewModel.InitializeAsync();
        }

        private async void BohyunOutsourceShipmentList_Click(object sender, RoutedEventArgs e)
        {
            var view = new BohyunOutsourceShipmentListView();

            var viewModel = new BohyunOutsourceShipmentListViewModel(
                _apiClient,
                _messageService);

            view.DataContext = viewModel;

            MainContent.Content = view;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "보현문화 출고리스트";
            HeaderSubtitle.Text = "보현문화 출고완료 내역 확인";

            await viewModel.InitializeAsync();
        }

        private async void ProductMonitoring_Click(object sender, RoutedEventArgs e)
        {
            var page = new ProductMonitoringPage();

            var viewModel = new ProductMonitoringPageViewModel(
                _apiClient,
                _messageService,
                _drawingViewer);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "품목 모니터링";
            HeaderSubtitle.Text = "품목 기준 LOT 이력 조회 / 최근 진행 현황 확인";

            await viewModel.InitializeAsync();
        }

        private async void OutsourceWorkInstructionList_Click(object sender, RoutedEventArgs e)
        {
            var page = new OutsourceWorkGroupListPage();

            var viewModel = new OutsourceWorkGroupListPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "외주 작업지시 리스트";
            HeaderSubtitle.Text = "외주 작업지시 조회 / 상세 확인 / 취소";

            await viewModel.InitializeAsync();
        }

        private async void OutsourceProcessingCost_Click(object sender, RoutedEventArgs e)
        {
            var view = new OutsourceProcessingCostManagementView();

            var viewModel = new OutsourceProcessingCostManagementViewModel(
                _apiClient,
                _messageService);

            view.DataContext = viewModel;

            MainContent.Content = view;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "외주가공비 관리";
            HeaderSubtitle.Text = "표준작업비 · 실제가공비 등록 / LOT별 배부 / 월마감";

            await viewModel.InitializeAsync();
        }

        private async void Inventory_Click(object sender, RoutedEventArgs e)
        {
            var page = new InventoryPage();
            var viewModel = new InventoryPageViewModel(_apiClient, _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "재고 관리";
            HeaderSubtitle.Text = "품목별 현재고 / 입출고 이력 / 재고 조정";

            await viewModel.InitializeAsync();
        }

        private async void Shipment_Click(object sender, RoutedEventArgs e)
        {
            var page = new ShipmentPage();

            var viewModel = new ShipmentPageViewModel(
                _apiClient,
                _messageService,
                async orderLineId => await OpenOrderLineDetailWindowAsync(orderLineId),
                async lotId => await OpenLotCertificateWindowAsync(lotId),
                async item => await OpenShipmentCoaAsync(item));

            page.DataContext = viewModel;
            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;
            HeaderTitle.Text = "출하 관리";
            HeaderSubtitle.Text = "출하대기 / 출하완료 조회 및 선택출하 처리";

            await viewModel.InitializeAsync();
        }

        private Task OpenShipmentInspectionReportAsync(ShipmentDisplayItemDto item)
        {
            // 성적서 출력은 LOT 관리에서 사용하는 공통 성적서 화면/서비스가 이미 있다면
            // 여기에서 그 기존 진입 메서드만 연결하세요.
            //
            // 현재 ShipmentDisplayItemDto는 그룹 행이라 생산 LOT가 여러 개일 수 있습니다.
            // 성적서가 LOT 단위라면 item.Lines 중 INSPECTION_RESULT 라인의 LotId를 사용해야 합니다.

            var productionLot = item.Lines
                .FirstOrDefault(x => x.SourceType == "INSPECTION_RESULT" && x.LotId.HasValue);

            if (productionLot == null)
            {
                _messageService.ShowWarning("성적서를 출력할 생산 LOT가 없습니다.");
                return Task.CompletedTask;
            }

            _messageService.ShowInfo("성적서 출력 연결은 LOT 관리의 기존 성적서 공통 진입 메서드에 연결하세요.");
            return Task.CompletedTask;
        }

        private async Task OpenShipmentCoaAsync(ShipmentDisplayItemDto item)
        {
            if (item == null)
            {
                _messageService.ShowWarning("COA를 출력할 출고 항목을 선택하세요.");
                return;
            }

            var viewModel = new ShipmentCoaWindowViewModel(_apiClient, _messageService);
            var window = new ShipmentCoaWindow(viewModel)
            {
                Owner = this
            };

            await viewModel.InitializeAsync(item.OrderLineId);

            window.ShowDialog();
        }
        private async Task OpenOrderLineDetailWindowAsync(long orderLineId)
        {
            var page = new OrderLineDetailPage();

            var vm = new OrderLineDetailPageViewModel(
                _apiClient,
                _messageService,
                null);

            page.DataContext = vm;

            var window = new OrderLineDetailWindow(page)
            {
                Owner = this
            };

            await vm.InitializeAsync(orderLineId);

            window.ShowDialog();
        }
        private async Task OpenLotCertificateWindowAsync(long lotId)
        {
            if (lotId <= 0)
            {
                _messageService.ShowWarning("LOT 정보가 없습니다.");
                return;
            }

            var windowVm = new LotCertificateWindowViewModel(_apiClient, _messageService);
            await windowVm.InitializeAsync(lotId);

            var window = new LotCertificateWindow(windowVm)
            {
                Owner = this
            };

            window.ShowDialog();
        }

        private async void UserManagement_Click(object sender, RoutedEventArgs e)
        {
            var page = new UserPage();
            var viewModel = new UserPageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "회원 관리";
            HeaderSubtitle.Text = "회원 등록 / 조회 / 수정 / 삭제 / 비밀번호 초기화";

            await viewModel.InitializeAsync();
        }

        private async void RoleManagement_Click(object sender, RoutedEventArgs e)
        {
            var page = new RolePage();
            var viewModel = new RolePageViewModel(
                _apiClient,
                _messageService);

            page.DataContext = viewModel;

            MainContent.Content = page;
            MainContent.Visibility = Visibility.Visible;

            HeaderTitle.Text = "역할 / 권한 관리";
            HeaderSubtitle.Text = "역할 등록 / 수정 / 삭제 및 메뉴·버튼 권한 설정";

            await viewModel.InitializeAsync();
        }

        private void LoadPermissions(AuthLoginResponse? loginResponse)
        {
            _permissionCodes.Clear();

            foreach (var permissionCode in loginResponse?.Permissions ?? Enumerable.Empty<string>())
            {
                if (string.IsNullOrWhiteSpace(permissionCode))
                {
                    continue;
                }

                _permissionCodes.Add(permissionCode.Trim());
            }
        }

        private bool HasPermission(string permissionCode)
        {
            if (string.IsNullOrWhiteSpace(permissionCode))
            {
                return false;
            }

            return _permissionCodes.Contains(permissionCode);
        }

        private void ApplyMenuPermissions()
        {
            SetMenuVisibility(DashboardMenuButton, PermissionCodes.DashboardView);

            SetMenuVisibility(DefectTypeMenuButton, PermissionCodes.DefectTypesView);
            SetMenuVisibility(ProcessMenuButton, PermissionCodes.ProcessesView);
            SetMenuVisibility(PartnerMenuButton, PermissionCodes.PartnersView);
            SetMenuVisibility(RoutingTemplateMenuButton, PermissionCodes.RoutingTemplatesView);
            SetMenuVisibility(RoutingTemplateStepMenuButton, PermissionCodes.RoutingTemplateStepsView);
            SetMenuVisibility(DrawingMenuButton, PermissionCodes.DrawingsView);
            SetMenuVisibility(PendingNewDrawingMenuButton, PermissionCodes.DrawingsView);
            SetMenuVisibility(ProductMenuButton, PermissionCodes.ProductsView);

            SetMenuVisibility(OrderLineCreateMenuButton, PermissionCodes.OrderLineCreateView);
            SetMenuVisibility(OrderLineListMenuButton, PermissionCodes.OrderLineListView);

            SetMenuVisibility(LotProcessMenuButton, PermissionCodes.LotsView);
            SetMenuVisibility(ProductionDailyMenuButton, PermissionCodes.ProductionDailyView);

            SetMenuVisibility(InspectionWorkInstructionMenuButton, PermissionCodes.InspectionWorkInstructionsView);
            SetMenuVisibility(InspectionScheduleManagementMenuButton, PermissionCodes.InspectionSchedulesView);
            SetMenuVisibility(InspectionResultManagementMenuButton, PermissionCodes.InspectionResultsView);

            SetMenuVisibility(OutsourceWorkInstructionMenuButton, PermissionCodes.OutsourceWorkInstructionsView);
            SetMenuVisibility(OutsourceWorkInstructionListMenuButton, PermissionCodes.OutsourceWorkInstructionsView);
            SetMenuVisibility(OutsourcePurchaseOrderMenuButton, PermissionCodes.OutsourcePurchaseOrdersView);
            SetMenuVisibility(OutsourcePurchaseOrderListMenuButton, PermissionCodes.OutsourcePurchaseOrderListView);
            SetMenuVisibility(BohyunOutsourceManagementMenuButton, PermissionCodes.BohyunOutsourceManagementView);
            SetMenuVisibility(BohyunOutsourceShipmentListMenuButton, PermissionCodes.BohyunOutsourceShipmentListView);

            SetMenuVisibility(ProductMonitoringMenuButton, PermissionCodes.ProductMonitoringView);
            SetMenuVisibility(OutsourceProcessingCostMenuButton, PermissionCodes.OutsourceProcessingCostsView);
            SetMenuVisibility(InventoryMenuButton, PermissionCodes.InventoriesView);
            ShipmentMenuButton.Visibility = Visibility.Collapsed;

            SetMenuVisibility(UserManagementMenuButton, PermissionCodes.UsersView);
            SetMenuVisibility(RoleManagementMenuButton, PermissionCodes.RolesView);
        }

        private void SetMenuVisibility(FrameworkElement menuElement, string permissionCode)
        {
            menuElement.Visibility = HasPermission(permissionCode)
                ? Visibility.Visible
                : Visibility.Collapsed;
        }

        private void OpenNewMainWindow_Click(object sender, RoutedEventArgs e)
        {
            var window = new MainWindow(
                _apiClient,
                _messageService,
                _loginResponse)
            {
                Title = $"{Title} - 보조 창",
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };

            window.Show();
        }


    }
}

