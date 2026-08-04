using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows.Input;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.LotDetails.Dtos;

namespace Mes.Wpf.Modules.LotDetails.ViewModels
{
    public class LotDetailWindowViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;

        private bool _isLoading;
        private LotTraceDetailDto? _detail;
        private LotTraceTimelineItemDto? _selectedTimelineItem;

        public LotDetailWindowViewModel(
            IApiClient apiClient,
            IMessageService messageService)
        {
            _apiClient = apiClient;
            _messageService = messageService;

            OutsourceWorks = new ObservableCollection<LotTraceOutsourceWorkDto>();
            InspectionRounds = new ObservableCollection<LotTraceInspectionRoundDto>();
            InspectionNoteRounds = new ObservableCollection<LotTraceInspectionRoundDto>();
            Timeline = new ObservableCollection<LotTraceTimelineItemDto>();
            Defects = new ObservableCollection<LotTraceInspectionDefectDto>();

            CloseCommand = new RelayCommand(_ => RequestClose?.Invoke());
            CopyLotNoCommand = new RelayCommand(_ => CopyLotNo());

            OpenDefectImageCommand = new RelayCommand(async parameter =>
            {
                if (parameter is LotTraceInspectionDefectDto defect)
                {
                    await OpenDefectImageAsync(defect);
                }
            });
        }

        public event Action? RequestClose;

        public ObservableCollection<LotTraceOutsourceWorkDto> OutsourceWorks { get; }

        public ObservableCollection<LotTraceInspectionRoundDto> InspectionRounds { get; }

        public ObservableCollection<LotTraceInspectionRoundDto> InspectionNoteRounds { get; }

        public ObservableCollection<LotTraceTimelineItemDto> Timeline { get; }

        public ObservableCollection<LotTraceInspectionDefectDto> Defects { get; }

        public LotTraceTimelineItemDto? SelectedTimelineItem
        {
            get => _selectedTimelineItem;
            set => SetProperty(ref _selectedTimelineItem, value);
        }

        public ICommand CloseCommand { get; }
        public ICommand CopyLotNoCommand { get; }
        public ICommand OpenDefectImageCommand { get; }

        public bool IsLoading
        {
            get => _isLoading;
            set => SetProperty(ref _isLoading, value);
        }

        public LotTraceDetailDto? Detail
        {
            get => _detail;
            set
            {
                if (SetProperty(ref _detail, value))
                {
                    RaiseAllDisplayProperties();
                }
            }
        }

        public string LotNo => Detail?.LotBasic.LotNo ?? "-";
        public string LotStatus => Detail?.LotBasic.Status ?? "-";
        public string ReworkText => Detail?.LotBasic.IsRework == true ? "재작업" : "일반";
        public bool IsRework => Detail?.LotBasic.IsRework == true;
        public string ParentLotNo => Detail?.LotBasic.ParentLotNo ?? "-";
        public string ReworkReasonText => Detail?.LotBasic.IsRework == true
            && !string.IsNullOrWhiteSpace(Detail.LotBasic.Memo)
                ? Detail.LotBasic.Memo!
                : "-";
        public string LotQtyText => FormatInt(Detail?.LotBasic.LotQty);
        public string CreatedDateText => FormatDate(Detail?.LotBasic.CreatedDate);
        public string DueDateText => FormatDate(Detail?.LotBasic.DueDate);
        public string LotQtyKpiText => Detail == null
            ? "-"
            : $"{Detail.LotBasic.LotQty:N0} {Detail.LotBasic.Uom}";
        public string OutsourceCompletedQtyKpiText
        {
            get
            {
                var completedQty = Detail?.OutsourceWorks
                    .Where(x => x.ConfirmedOutsourceQty.HasValue)
                    .OrderByDescending(x => x.WorkDoneAt)
                    .Select(x => x.ConfirmedOutsourceQty)
                    .FirstOrDefault();
                return FormatNullableInt(completedQty);
            }
        }
        public string InspectionQtyKpiText => FormatNullableInt(Detail?.Inspection?.InspectedQty);
        public string GoodQtyKpiText => FormatNullableInt(Detail?.Inspection?.GoodQty);
        public string DefectQtyKpiText => FormatNullableInt(Detail?.Inspection?.DefectQty);
        public string DueStatusText
        {
            get
            {
                if (Detail == null)
                {
                    return "-";
                }

                var days = (Detail.LotBasic.DueDate.Date - DateTime.Today).Days;
                return days switch
                {
                    < 0 => $"D+{Math.Abs(days)}",
                    0 => "D-DAY",
                    _ => $"D-{days}",
                };
            }
        }

        public string PartnerName => Detail?.ProductOrder.PartnerName ?? "-";
        public string ProductCode => Detail?.ProductOrder.ProductCode ?? "-";
        public string ProductName => Detail?.ProductOrder.ProductName ?? "-";
        public string ProductSpec => Detail?.ProductOrder.ProductSpec ?? "-";
        public string PlateSize => BuildPlateSize();
        public string OrderQtyText => FormatInt(Detail?.ProductOrder.OrderQty);
        public string StockQtyText => FormatInt(Detail?.ProductOrder.CurrentStockQty);
        public string OrderDueDateText => FormatDate(Detail?.ProductOrder.DueDate);

        public string OrderMemoText => string.IsNullOrWhiteSpace(Detail?.ProductOrder.Memo)
            ? "-"
            : Detail.ProductOrder.Memo!;
        public string PlanTypeDisplayText =>
            string.IsNullOrWhiteSpace(Detail?.ProductOrder.PlanTypeDisplay)
                ? "-"
                : Detail.ProductOrder.PlanTypeDisplay!;

        public string PlanShipTargetQtyText =>
            FormatNullableInt(Detail?.ProductOrder.PlanShipTargetQty);

        public string PlanAvailableInventoryQtyText =>
            FormatNullableInt(Detail?.ProductOrder.PlanAvailableInventoryQty);

        public string PlanStockShipQtyText =>
            FormatNullableInt(Detail?.ProductOrder.PlanStockShipQty);

        public string PlanProductionQtyText =>
            FormatNullableInt(Detail?.ProductOrder.PlanProductionQty);

        public string PlanShortCloseText =>
            Detail?.ProductOrder.PlanIsShortClose == true
                ? "예"
                : "아니오";


        public string InspectionStatusText
        {
            get
            {
                if (Detail?.Inspection == null)
                {
                    return "검수일정 없음";
                }

                if (Detail.Inspection.InspectionResultId.HasValue)
                {
                    return "검수완료";
                }

                return Detail.Inspection.ScheduleStatus ?? "검수 전";
            }
        }
        public string OutsourceWorkMemoText
        {
            get
            {
                if (Detail?.OutsourceWorks == null || Detail.OutsourceWorks.Count == 0)
                {
                    return "-";
                }

                var remark = Detail.OutsourceWorks[0].Remark;
                return string.IsNullOrWhiteSpace(remark) ? "-" : remark!;
            }
        }

        public string InspectionDateText => FormatDate(Detail?.Inspection?.InspectionDate);
        public string InspectedQtyText => FormatNullableInt(Detail?.Inspection?.InspectedQty);
        public string GoodQtyText => FormatNullableInt(Detail?.Inspection?.GoodQty);
        public string DefectQtyText => FormatNullableInt(Detail?.Inspection?.DefectQty);
        public string DefectShipQtyText => FormatNullableInt(Detail?.Inspection?.DefectShipQty);
        public string InspectionResultCreatedAtText => FormatDateTime(Detail?.Inspection?.ResultCreatedAt);
        public string InspectionMemoText => string.IsNullOrWhiteSpace(Detail?.Inspection?.Memo)
            ? "-"
            : Detail.Inspection.Memo!;
        public bool IsLotCreated => Detail?.Progress.LotCreated == true;
        public bool IsOutsourceInstructionCreated => Detail?.Progress.OutsourceInstructionCreated == true;
        public bool IsOutsourceWorkDone => Detail?.Progress.OutsourceWorkDone == true;
        public bool IsInspectionDone => Detail?.Progress.InspectionDone == true;

        public async Task InitializeAsync(long lotId)
        {
            try
            {
                IsLoading = true;

                var result = await _apiClient.GetAsync<LotTraceDetailDto>(
                    $"{ApiRoutes.Lots}/{lotId}/detail");

                if (!result.Success || result.Data == null)
                {
                    Detail = null;
                    OutsourceWorks.Clear();
                    InspectionRounds.Clear();
                    InspectionNoteRounds.Clear();
                    Timeline.Clear();
                    Defects.Clear();
                    _messageService.ShowError(result.Message ?? "LOT 상세정보 조회에 실패했습니다.");
                    return;
                }

                Detail = result.Data;

                OutsourceWorks.Clear();
                foreach (var item in result.Data.OutsourceWorks)
                {
                    OutsourceWorks.Add(item);
                }

                InspectionRounds.Clear();
                InspectionNoteRounds.Clear();
                foreach (var item in result.Data.InspectionRounds)
                {
                    InspectionRounds.Add(item);
                    if (item.InspectionResultId.HasValue)
                    {
                        InspectionNoteRounds.Add(item);
                    }
                }

                Timeline.Clear();
                foreach (var item in result.Data.Timeline)
                {
                    Timeline.Add(item);
                }
                SelectedTimelineItem = Timeline.LastOrDefault(x => x.IsCurrent)
                    ?? Timeline.LastOrDefault();

                Defects.Clear();
                if (result.Data.Inspection != null)
                {
                    foreach (var defect in result.Data.Inspection.Defects)
                    {
                        Defects.Add(defect);
                    }
                }
            }
            finally
            {
                IsLoading = false;
            }
        }

        private string BuildPlateSize()
        {
            var width = Detail?.ProductOrder.PanelWidthMm;
            var length = Detail?.ProductOrder.PanelLengthMm;

            if (!width.HasValue && !length.HasValue)
            {
                return "-";
            }

            return $"{width?.ToString() ?? "-"} x {length?.ToString() ?? "-"}";
        }

        private static string FormatDate(DateTime? value)
        {
            return value.HasValue ? value.Value.ToString("yyyy-MM-dd") : "-";
        }

        private static string FormatDateTime(DateTime? value)
        {
            return value.HasValue ? value.Value.ToString("yyyy-MM-dd HH:mm") : "-";
        }

        private static string FormatInt(int? value)
        {
            return value.HasValue ? value.Value.ToString("N0") : "-";
        }

        private static string FormatNullableInt(int? value)
        {
            return value.HasValue ? value.Value.ToString("N0") : "-";
        }

        private void RaiseAllDisplayProperties()
        {
            OnPropertyChanged(nameof(LotNo));
            OnPropertyChanged(nameof(LotStatus));
            OnPropertyChanged(nameof(ReworkText));
            OnPropertyChanged(nameof(IsRework));
            OnPropertyChanged(nameof(ParentLotNo));
            OnPropertyChanged(nameof(ReworkReasonText));
            OnPropertyChanged(nameof(LotQtyText));
            OnPropertyChanged(nameof(CreatedDateText));
            OnPropertyChanged(nameof(DueDateText));
            OnPropertyChanged(nameof(LotQtyKpiText));
            OnPropertyChanged(nameof(OutsourceCompletedQtyKpiText));
            OnPropertyChanged(nameof(InspectionQtyKpiText));
            OnPropertyChanged(nameof(GoodQtyKpiText));
            OnPropertyChanged(nameof(DefectQtyKpiText));
            OnPropertyChanged(nameof(DueStatusText));

            OnPropertyChanged(nameof(PartnerName));
            OnPropertyChanged(nameof(ProductCode));
            OnPropertyChanged(nameof(ProductName));
            OnPropertyChanged(nameof(ProductSpec));
            OnPropertyChanged(nameof(PlateSize));
            OnPropertyChanged(nameof(OrderQtyText));
            OnPropertyChanged(nameof(OrderMemoText));
            OnPropertyChanged(nameof(StockQtyText));
            OnPropertyChanged(nameof(OrderDueDateText));
            OnPropertyChanged(nameof(OutsourceWorkMemoText));

            OnPropertyChanged(nameof(InspectionStatusText));
            OnPropertyChanged(nameof(InspectionDateText));
            OnPropertyChanged(nameof(InspectedQtyText));
            OnPropertyChanged(nameof(GoodQtyText));
            OnPropertyChanged(nameof(DefectQtyText));
            OnPropertyChanged(nameof(DefectShipQtyText));
            OnPropertyChanged(nameof(InspectionResultCreatedAtText));
            OnPropertyChanged(nameof(InspectionMemoText));

            OnPropertyChanged(nameof(IsLotCreated));
            OnPropertyChanged(nameof(IsOutsourceInstructionCreated));
            OnPropertyChanged(nameof(IsOutsourceWorkDone));
            OnPropertyChanged(nameof(IsInspectionDone));

            OnPropertyChanged(nameof(PlanTypeDisplayText));
            OnPropertyChanged(nameof(PlanShipTargetQtyText));
            OnPropertyChanged(nameof(PlanAvailableInventoryQtyText));
            OnPropertyChanged(nameof(PlanStockShipQtyText));
            OnPropertyChanged(nameof(PlanProductionQtyText));
            OnPropertyChanged(nameof(PlanShortCloseText));
        }

        private void CopyLotNo()
        {
            var lotNo = LotNo?.Trim();
            if (string.IsNullOrWhiteSpace(lotNo) || lotNo == "-")
            {
                _messageService.ShowWarning("복사할 LOT 번호가 없습니다.");
                return;
            }

            Clipboard.SetText(lotNo);
            _messageService.ShowInfo($"LOT 번호가 복사되었습니다.\n{lotNo}");
        }

        private async Task OpenDefectImageAsync(LotTraceInspectionDefectDto defect)
        {
            if (defect == null || !defect.HasAttachment || defect.FirstAttachment == null)
            {
                _messageService.ShowWarning("첨부된 이미지가 없습니다.");
                return;
            }

            var attachment = defect.FirstAttachment;
            var imageUrl = attachment.ImageUrl;

            if (string.IsNullOrWhiteSpace(imageUrl))
            {
                _messageService.ShowWarning("이미지 경로가 없습니다.");
                return;
            }

            try
            {
                var requestUrl = imageUrl.Trim();

                if (Uri.TryCreate(requestUrl, UriKind.Absolute, out var absoluteUri))
                {
                    requestUrl = absoluteUri.PathAndQuery.TrimStart('/');
                }
                else
                {
                    requestUrl = requestUrl.TrimStart('/');
                }

                var extension = GetImageExtension(attachment.FileName, attachment.MimeType);
                var tempDir = Path.Combine(Path.GetTempPath(), "MesWpf", "DefectImages");

                Directory.CreateDirectory(tempDir);

                var rawFileName = string.IsNullOrWhiteSpace(attachment.FileName)
                    ? $"defect_{defect.InspectionDefectId}_{DateTime.Now:yyyyMMddHHmmss}{extension}"
                    : Path.GetFileName(attachment.FileName);

                var fileName = string.IsNullOrWhiteSpace(rawFileName)
                    ? $"defect_{defect.InspectionDefectId}_{DateTime.Now:yyyyMMddHHmmss}{extension}"
                    : rawFileName;

                if (string.IsNullOrWhiteSpace(Path.GetExtension(fileName)))
                {
                    fileName += extension;
                }

                var tempPath = Path.Combine(tempDir, fileName);

                var download = await _apiClient.DownloadFileAsync(requestUrl, tempPath);

                if (!download.Success)
                {
                    _messageService.ShowError(
                        download.Message ?? "이미지 다운로드에 실패했습니다.");
                    return;
                }

                Process.Start(new ProcessStartInfo
                {
                    FileName = tempPath,
                    UseShellExecute = true
                });
            }
            catch (Exception ex)
            {
                _messageService.ShowError($"이미지 열기 중 오류가 발생했습니다.\n{ex.Message}");
            }
        }

        private static string GetImageExtension(string? fileName, string? mimeType)
        {
            var extension = Path.GetExtension(fileName);

            if (!string.IsNullOrWhiteSpace(extension))
            {
                return extension;
            }

            return mimeType switch
            {
                "image/png" => ".png",
                "image/jpeg" => ".jpg",
                "image/jpg" => ".jpg",
                "image/gif" => ".gif",
                "image/bmp" => ".bmp",
                "image/webp" => ".webp",
                _ => ".png"
            };
        }
    }
}
