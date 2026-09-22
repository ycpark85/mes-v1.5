using System;
using System.Collections.ObjectModel;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Input;
using Microsoft.Win32;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Infrastructure.Diagnostics;
using Mes.Wpf.Modules.InspectionSchedules.Services;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;

namespace Mes.Wpf.Modules.InspectionSchedules.ViewModels
{
    public class InspectionResultWindowViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
        private readonly InspectionPhotoService _photos;
        private readonly Action<Exception> _reportError;
        private readonly bool _canEdit;
        private readonly bool _canRequestEdit;

        private long _inspectionScheduleId;
        private string _lotNo = string.Empty;
        private string _productName = string.Empty;
        private string _partnerName = string.Empty;
        private DateTime? _inspectionDate;
        private int _planQty;
        private DateTime? _dueDate;
        private int _orderQty;

        private int _baseAccumulatedGoodQty;
        private int _baseAccumulatedDefectQty;
        private int _baseAccumulatedDefectShipQty;
        private int _baseAccumulatedInspectedQty;
        private int _baseAccumulatedUninspectedQty;

        private int _accumulatedGoodQty;
        private int _accumulatedDefectQty;
        private int _accumulatedDefectShipQty;
        private int _accumulatedInspectedQty;
        private int _accumulatedUninspectedQty;

        private int _currentStockQty;
        private int _shipTargetQty;
        private int _priorShippedQty;
        private int _remainingBeforeCurrentResultQty;
        private int _priorUnsettledSellableQty;

        private int _currentResultStockShipQty;
        private int _currentResultResultShipQty;
        private int _currentResultStockInQty;
        private int _currentResultDiscardQty;

        private int _stockShipQty;
        private int _resultShipQty;
        private int _stockInQty;
        private int _discardQty;

        private int _goodQty;
        private int _defectShipQty;
        private int _defectQty;
        private int _uninspectedQty;
        private bool _isPartial;
        private DateTime? _nextInspectionDate;
        private string _partialReason = string.Empty;
        private string _memo = string.Empty;
        private DateTimeOffset? _expectedUpdatedAt;
        private bool _isLoading;
        private bool _isRecalculatingInventoryPreview;
        private InspectionResultDefectEditModel? _selectedDefect;

        private ObservableCollection<InspectionStockLotDto> _stockLots = new();
        private ObservableCollection<InspectionRoundSummaryDto> _rounds = new();
        private string _scheduleStatus = string.Empty;
        private int _inspectionRound;
        private int _inspectionRoundCount;
        private bool _isInitializing;
        private bool _loadFailed;
        private string _shortageReason = string.Empty;
        private string _stockError = string.Empty;
        private string _settlementError = string.Empty;
        private int _originalOwnInventoryInQty;
        private int _physicalStockQty;
        private bool _inventorySummaryAvailable;

        public event Action<bool>? CloseRequested;
        public event Action? EditRequested;

        public IApiClient ApiClient => _apiClient;
        public IMessageService MessageService => _messageService;

        public InspectionResultWindowViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            bool canEdit = true,
            bool canRequestEdit = false,
            Action<Exception>? reportError = null)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _photos = new InspectionPhotoService(apiClient, messageService);
            _reportError = reportError ?? (error => UiErrorReporter.Report(error, messageService));
            _canEdit = canEdit;
            _canRequestEdit = canRequestEdit;

            Defects = new ObservableCollection<InspectionResultDefectEditModel>();

            AddDefectCommand = new RelayCommand(_ => AddDefect(), _ => CanEdit);
            RemoveDefectCommand = new RelayCommand(
                x => RemoveDefect(x as InspectionResultDefectEditModel),
                x => CanEdit && x is InspectionResultDefectEditModel);
            UploadPhotoCommand = new AsyncRelayCommand<InspectionResultDefectEditModel>(
                UploadPhotoAsync, x => CanEdit && !IsLoading && x != null, _reportError);
            RemovePhotoCommand = new RelayCommand(
                x => RemovePhoto(x as DefectAttachmentEditModel),
                x => CanEdit && x is DefectAttachmentEditModel);
            OpenPhotoCommand = new AsyncRelayCommand<DefectAttachmentEditModel>(
                OpenPhotoAsync, x => !IsLoading && x != null, _reportError);
            SaveCommand = new AsyncRelayCommand(SaveAsync, () => CanEdit && !IsLoading, _reportError);
            EditCommand = new RelayCommand(
                _ => EditRequested?.Invoke(),
                _ => CanRequestEdit && !IsLoading);
            CancelCommand = new RelayCommand(_ => CloseRequested?.Invoke(false));
        }
        public ObservableCollection<InspectionStockLotDto> StockLots
        {
            get => _stockLots;
            set => SetProperty(ref _stockLots, value);
        }

        public string ShortageReason
        {
            get => _shortageReason;
            set => SetProperty(ref _shortageReason, value);
        }
        public string StockError { get => _stockError; set => SetProperty(ref _stockError, value); }
        public string SettlementError { get => _settlementError; set => SetProperty(ref _settlementError, value); }
        public int PhysicalStockQty { get => _physicalStockQty; set => SetProperty(ref _physicalStockQty, value); }
        public int PlanShortageQty => Math.Max(PlanQty - AccumulatedReceivedQty, 0);
        private InspectionQuantities Quantities => new(GoodQty, DefectShipQty, DefectQty, UninspectedQty,
            StockShipQty, ResultShipQty, StockInQty, DiscardQty, PriorUnsettledSellableQty);
        public string AllocationPreview => $"{(CanEdit ? "저장 시" : "이번 회차")} 실제 출고 {CurrentRoundShipQty:N0} / 재고편입 {StockInQty:N0} / 폐기 {DiscardQty:N0}";

        public long InspectionScheduleId
        {
            get => _inspectionScheduleId;
            set => SetProperty(ref _inspectionScheduleId, value);
        }

        public string LotNo
        {
            get => _lotNo;
            set => SetProperty(ref _lotNo, value);
        }

        public string ProductName
        {
            get => _productName;
            set => SetProperty(ref _productName, value);
        }

        public string PartnerName
        {
            get => _partnerName;
            set => SetProperty(ref _partnerName, value);
        }

        public DateTime? DueDate
        {
            get => _dueDate;
            set => SetProperty(ref _dueDate, value);
        }

        public int OrderQty
        {
            get => _orderQty;
            set => SetProperty(ref _orderQty, value);
        }

        public DateTime? InspectionDate
        {
            get => _inspectionDate;
            set => SetProperty(ref _inspectionDate, value);
        }

        public int PlanQty
        {
            get => _planQty;
            set => SetProperty(ref _planQty, value);
        }

        public int AccumulatedGoodQty
        {
            get => _accumulatedGoodQty;
            set => SetProperty(ref _accumulatedGoodQty, value);
        }

        public int AccumulatedDefectQty
        {
            get => _accumulatedDefectQty;
            set => SetProperty(ref _accumulatedDefectQty, value);
        }

        public int AccumulatedDefectShipQty
        {
            get => _accumulatedDefectShipQty;
            set => SetProperty(ref _accumulatedDefectShipQty, value);
        }

        public int AccumulatedInspectedQty
        {
            get => _accumulatedInspectedQty;
            set => SetProperty(ref _accumulatedInspectedQty, value);
        }

        public int AccumulatedUninspectedQty
        {
            get => _accumulatedUninspectedQty;
            set => SetProperty(ref _accumulatedUninspectedQty, value);
        }

        public int AccumulatedReceivedQty => AccumulatedInspectedQty + AccumulatedUninspectedQty;

        public int GoodQty
        {
            get => _goodQty;
            set
            {
                if (SetProperty(ref _goodQty, value))
                {
                    RecalculateTotals();
                }
            }
        }

        public int DefectShipQty
        {
            get => _defectShipQty;
            set
            {
                if (SetProperty(ref _defectShipQty, value))
                {
                    RecalculateTotals();
                }
            }
        }

        public int DefectQty
        {
            get => _defectQty;
            set
            {
                if (SetProperty(ref _defectQty, value))
                {
                    RecalculateTotals();
                }
            }
        }

        public int UninspectedQty
        {
            get => _uninspectedQty;
            set
            {
                if (SetProperty(ref _uninspectedQty, value))
                {
                    RecalculateTotals();
                }
            }
        }

        public int TotalQty => Quantities.Inspected;
        public int ReceivedQty => Quantities.Received;
        public int TotalDisposalQty => Quantities.Disposal;
        public int SellableQty => Quantities.Sellable;

        public bool CanEdit => _canEdit;
        public bool CanRequestEdit => _canRequestEdit && ScheduleStatus == "DONE";
        public bool IsReadOnlyMode => !CanEdit;
        public string InventorySummaryTitle => CanEdit ? "출고 / 재고 요약" : "출고 / 재고 요약 (저장 시점)";
        public string StockQuantityLabel => CanEdit ? "사용가능 재고" : "저장 후 재고";
        public string PhysicalStockLabel => CanEdit ? "전체 실재고" : "저장 후 재고";
        public string StockLotsTitle => CanEdit ? "FIFO 기존재고 LOT" : "저장 후 LOT별 재고";
        public bool InventorySummaryAvailable
        {
            get => _inventorySummaryAvailable;
            private set => SetProperty(ref _inventorySummaryAvailable, value);
        }
        public string CloseButtonText => CanEdit ? "취소" : "닫기";
        public bool IsShipmentInputEnabled => CanEdit;
        public bool IsUninspectedInputEnabled => CanEdit && !IsPartial;

        public int CurrentStockQty
        {
            get => _currentStockQty;
            set
            {
                if (SetProperty(ref _currentStockQty, value))
                {
                    RecalculateInventoryPreview();
                }
            }
        }

        public int ShipTargetQty
        {
            get => _shipTargetQty;
            set
            {
                if (SetProperty(ref _shipTargetQty, value))
                {
                    OnPropertyChanged(nameof(RemainingBeforeCurrentResultQty));
                    OnPropertyChanged(nameof(RemainingAfterCurrentQty));
                    RecalculateInventoryPreview();
                }
            }
        }

        public int PriorShippedQty
        {
            get => _priorShippedQty;
            set
            {
                if (SetProperty(ref _priorShippedQty, value))
                {
                    OnPropertyChanged(nameof(RemainingBeforeCurrentResultQty));
                    OnPropertyChanged(nameof(TotalShippedQty));
                    OnPropertyChanged(nameof(RemainingAfterCurrentQty));
                    RecalculateInventoryPreview();
                }
            }
        }

        public int RemainingBeforeCurrentResultQty
        {
            get => _remainingBeforeCurrentResultQty;
            set
            {
                if (SetProperty(ref _remainingBeforeCurrentResultQty, value))
                {
                    OnPropertyChanged(nameof(RemainingAfterCurrentQty));
                    RecalculateInventoryPreview();
                }
            }
        }

        public int CurrentRoundShipQty => Quantities.Shipment;

        public int TotalShippedQty => PriorShippedQty + CurrentRoundShipQty;

        public int RemainingAfterCurrentQty =>
            Math.Max(RemainingBeforeCurrentResultQty - CurrentRoundShipQty, 0);

        public int PriorUnsettledSellableQty
        {
            get => _priorUnsettledSellableQty;
            set
            {
                if (SetProperty(ref _priorUnsettledSellableQty, value))
                {
                    OnPropertyChanged(nameof(SellableQty));
                    RecalculateInventoryPreview();
                }
            }
        }

        public int CurrentResultStockShipQty
        {
            get => _currentResultStockShipQty;
            set => SetProperty(ref _currentResultStockShipQty, value);
        }

        public int CurrentResultResultShipQty
        {
            get => _currentResultResultShipQty;
            set => SetProperty(ref _currentResultResultShipQty, value);
        }

        public int CurrentResultStockInQty
        {
            get => _currentResultStockInQty;
            set => SetProperty(ref _currentResultStockInQty, value);
        }

        public int CurrentResultDiscardQty
        {
            get => _currentResultDiscardQty;
            set => SetProperty(ref _currentResultDiscardQty, value);
        }

        public int StockShipQty
        {
            get => _stockShipQty;
            set
            {
                if (SetProperty(ref _stockShipQty, value))
                {
                    if (!_isRecalculatingInventoryPreview)
                    {
                        RecalculateInventoryPreview();
                    }
                }
            }
        }

        public int ResultShipQty
        {
            get => _resultShipQty;
            set
            {
                if (SetProperty(ref _resultShipQty, value))
                {
                    if (!_isRecalculatingInventoryPreview)
                    {
                        RecalculateInventoryPreview();
                    }
                }
            }
        }

        public int StockInQty
        {
            get => _stockInQty;
            set
            {
                if (SetProperty(ref _stockInQty, value))
                {
                    if (!_isRecalculatingInventoryPreview)
                    {
                        RecalculateInventoryPreview();
                    }
                }
            }
        }

        public int DiscardQty
        {
            get => _discardQty;
            set
            {
                if (SetProperty(ref _discardQty, value))
                {
                    OnPropertyChanged(nameof(TotalDisposalQty));

                    if (!_isRecalculatingInventoryPreview)
                    {
                        RecalculateInventoryPreview();
                    }
                }
            }
        }

        public bool IsPartial
        {
            get => _isPartial;
            set
            {
                if (SetProperty(ref _isPartial, value))
                {
                    OnPropertyChanged(nameof(IsShipmentInputEnabled));
                    OnPropertyChanged(nameof(IsUninspectedInputEnabled));

                    if (value)
                    {
                        UninspectedQty = 0;
                    }

                    RecalculateTotals();
                }
            }
        }

        public DateTime? NextInspectionDate
        {
            get => _nextInspectionDate;
            set => SetProperty(ref _nextInspectionDate, value);
        }

        public string PartialReason
        {
            get => _partialReason;
            set => SetProperty(ref _partialReason, value);
        }

        public string Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public bool IsLoading
        {
            get => _isLoading;
            set
            {
                if (SetProperty(ref _isLoading, value))
                {
                    if (SaveCommand is AsyncRelayCommand saveCommand)
                    {
                        saveCommand.RaiseCanExecuteChanged();
                    }

                    if (EditCommand is RelayCommand editCommand)
                    {
                        editCommand.RaiseCanExecuteChanged();
                    }

                    if (AddDefectCommand is RelayCommand addDefectCommand)
                    {
                        addDefectCommand.RaiseCanExecuteChanged();
                    }

                    if (RemoveDefectCommand is RelayCommand removeDefectCommand)
                    {
                        removeDefectCommand.RaiseCanExecuteChanged();
                    }

                    if (UploadPhotoCommand is AsyncRelayCommand<InspectionResultDefectEditModel> uploadPhotoCommand)
                    {
                        uploadPhotoCommand.RaiseCanExecuteChanged();
                    }

                    if (RemovePhotoCommand is RelayCommand removePhotoCommand)
                    {
                        removePhotoCommand.RaiseCanExecuteChanged();
                    }

                    if (OpenPhotoCommand is AsyncRelayCommand<DefectAttachmentEditModel> openPhotoCommand)
                    {
                        openPhotoCommand.RaiseCanExecuteChanged();
                    }
                }
            }
        }

        public ObservableCollection<InspectionResultDefectEditModel> Defects { get; }

        public ObservableCollection<InspectionRoundSummaryDto> Rounds
        {
            get => _rounds;
            set => SetProperty(ref _rounds, value);
        }

        public string ScheduleStatus
        {
            get => _scheduleStatus;
            set
            {
                if (SetProperty(ref _scheduleStatus, value))
                {
                    OnPropertyChanged(nameof(CanRequestEdit));
                    if (EditCommand is RelayCommand editCommand)
                    {
                        editCommand.RaiseCanExecuteChanged();
                    }
                }
            }
        }

        public int InspectionRound
        {
            get => _inspectionRound;
            set
            {
                if (SetProperty(ref _inspectionRound, value))
                {
                    OnPropertyChanged(nameof(InspectionRoundDisplay));
                }
            }
        }

        public int InspectionRoundCount
        {
            get => _inspectionRoundCount;
            set
            {
                if (SetProperty(ref _inspectionRoundCount, value))
                {
                    OnPropertyChanged(nameof(InspectionRoundDisplay));
                }
            }
        }

        public string InspectionRoundDisplay => InspectionRound > 0
            ? $"{InspectionRound}차 / 총 {InspectionRoundCount}회"
            : "-";

        public InspectionResultDefectEditModel? SelectedDefect
        {
            get => _selectedDefect;
            set => SetProperty(ref _selectedDefect, value);
        }

        public ICommand AddDefectCommand { get; }
        public ICommand RemoveDefectCommand { get; }
        public ICommand UploadPhotoCommand { get; }
        public ICommand RemovePhotoCommand { get; }
        public ICommand OpenPhotoCommand { get; }
        public ICommand SaveCommand { get; }
        public ICommand EditCommand { get; }
        public ICommand CancelCommand { get; }

        public Task RefreshAsync() => LoadAsync();

        public async Task InitializeAsync(
            long inspectionScheduleId,
            string lotNo,
            string productName,
            string partnerName,
            DateTime? inspectionDate,
            int planQty,
            DateTime? dueDate,
            int orderQty)
        {
            InspectionScheduleId = inspectionScheduleId;
            LotNo = lotNo;
            ProductName = productName;
            PartnerName = partnerName;
            InspectionDate = inspectionDate;
            PlanQty = planQty;
            DueDate = dueDate;
            OrderQty = orderQty;

            await LoadAsync();
        }

        public void ApplySelectedDefectType(
            InspectionResultDefectEditModel defect,
            InspectionResultDefectTypeLookupDto selectedDefectType)
        {
            if (!CanEdit || defect == null || selectedDefectType == null)
            {
                return;
            }

            defect.DefectTypeId = (int)selectedDefectType.DefectTypeId;
            defect.DefectCode = selectedDefectType.DefectCode?.Trim().ToUpperInvariant() ?? string.Empty;
            defect.Category1Name = selectedDefectType.Category1Name?.Trim() ?? string.Empty;
            defect.Category2Name = selectedDefectType.Category2Name?.Trim() ?? string.Empty;
            defect.DefectTypeMemo = selectedDefectType.Memo?.Trim() ?? string.Empty;
        }

        public void ClearSelectedDefectType(InspectionResultDefectEditModel defect)
        {
            if (!CanEdit || defect == null)
            {
                return;
            }

            defect.DefectTypeId = null;
            defect.DefectCode = string.Empty;
            defect.Category1Name = string.Empty;
            defect.Category2Name = string.Empty;
            defect.DefectTypeMemo = string.Empty;
        }

        private async Task LoadAsync()
        {
            _isInitializing = true;
            _loadFailed = false;
            InventorySummaryAvailable = false;
            StockLots = new();
            try
            {
                IsLoading = true;

                var result = await _apiClient.GetAsync<InspectionResultResponse>(
                    $"{ApiRoutes.InspectionSchedules}/{InspectionScheduleId}/result{(CanEdit ? "" : "?view_mode=saved")}");

                if (!result.Success || result.Data?.Inventory == null)
                {
                    _loadFailed = true;
                    _messageService.ShowError(result.Message ?? "검수 정보를 불러오지 못했습니다. 창을 다시 열어주세요.");
                    return;
                }

                var response = result.Data;
                if (!CanEdit && response.Inventory.ViewMode != "saved")
                {
                    _loadFailed = true;
                    StockError = "서버에서 저장 당시 재고를 제공하지 않습니다. 서버 업데이트를 확인한 뒤 다시 열어주세요.";
                    _messageService.ShowError(StockError);
                    return;
                }
                if (CanEdit && response.Inventory.ViewMode == "saved")
                {
                    _loadFailed = true;
                    StockError = "수정에 필요한 현재 재고 정보를 받지 못했습니다. 창을 다시 열어주세요.";
                    _messageService.ShowError(StockError);
                    return;
                }
                var stockLots = response.Inventory.StockLots;
                if (stockLots == null)
                {
                    _loadFailed = true;
                    StockError = "서버에서 통합 재고 정보를 제공하지 않습니다. 서버 업데이트를 확인한 뒤 창을 다시 열어주세요.";
                    _messageService.ShowError(StockError);
                    return;
                }
                if (stockLots.Sum(row => (long)row.StockQty) != response.Inventory.CurrentStockQty
                    || (!CanEdit && stockLots.Any(row => row.StockQty != row.PhysicalQty))
                    || stockLots.Any(row => row.ProductInventoryLotId <= 0)
                    || stockLots.Select(row => row.ProductInventoryLotId).Distinct().Count() != stockLots.Count)
                {
                    _loadFailed = true;
                    StockError = "재고 요약과 LOT 정보가 일치하지 않습니다. 창을 다시 열어주세요.";
                    _messageService.ShowError(StockError);
                    return;
                }
                StockLots = stockLots;
                var dto = response?.Result;
                var accumulated = response?.Accumulated;
                var inventory = response?.Inventory;

                ScheduleStatus = response?.ScheduleStatus ?? string.Empty;
                InspectionRound = response?.InspectionRound ?? 0;
                InspectionRoundCount = response?.InspectionRoundCount ?? 0;
                Rounds = response?.Rounds ?? new ObservableCollection<InspectionRoundSummaryDto>();

                PhysicalStockQty = inventory?.PhysicalStockQty ?? 0;
                StockError = inventory?.StockError ?? string.Empty;
                InventorySummaryAvailable = CanEdit || string.IsNullOrWhiteSpace(StockError);
                SettlementError = inventory?.SettlementError ?? string.Empty;
                _originalOwnInventoryInQty = dto == null ? 0 : dto.GoodQty + dto.DefectShipQty - dto.DiscardQty;
                CurrentStockQty = inventory?.CurrentStockQty ?? 0;
                ShipTargetQty = inventory?.ShipTargetQty ?? OrderQty;
                PriorShippedQty = inventory?.PriorShippedQty ?? 0;
                RemainingBeforeCurrentResultQty =
                    inventory?.RemainingBeforeCurrentResultQty
                    ?? Math.Max(ShipTargetQty - PriorShippedQty, 0);
                PriorUnsettledSellableQty = inventory?.PriorUnsettledSellableQty ?? 0;

                CurrentResultStockShipQty = inventory?.CurrentResultStockShipQty ?? 0;
                CurrentResultResultShipQty = inventory?.CurrentResultResultShipQty ?? 0;
                CurrentResultStockInQty = inventory?.CurrentResultStockInQty ?? 0;
                CurrentResultDiscardQty = inventory?.CurrentResultDiscardQty ?? 0;

                _baseAccumulatedGoodQty = accumulated?.GoodQty ?? 0;
                _baseAccumulatedDefectQty = accumulated?.DefectQty ?? 0;
                _baseAccumulatedDefectShipQty = accumulated?.DefectShipQty ?? 0;
                _baseAccumulatedInspectedQty = accumulated?.InspectedQty ?? 0;
                _baseAccumulatedUninspectedQty = accumulated?.UninspectedQty ?? 0;

                if (dto == null)
                {
                    _expectedUpdatedAt = null;
                    GoodQty = 0;
                    DefectShipQty = 0;
                    DefectQty = 0;
                    UninspectedQty = 0;

                    StockShipQty = 0;
                    ResultShipQty = 0;
                    DiscardQty = CurrentResultDiscardQty;
                    StockInQty = CurrentResultStockInQty;

                    IsPartial = false;
                    NextInspectionDate = null;
                    PartialReason = string.Empty;
                    ShortageReason = string.Empty;
                    Memo = string.Empty;
                    Defects.Clear();

                    RecalculateTotals();
                    return;
                }

                GoodQty = dto.GoodQty;
                _expectedUpdatedAt = dto.UpdatedAt;
                DefectShipQty = dto.DefectShipQty;
                DefectQty = dto.DefectQty;
                UninspectedQty = dto.UninspectedQty;

                StockShipQty = CurrentResultStockShipQty;
                ResultShipQty = CurrentResultResultShipQty;
                DiscardQty = dto.DiscardQty;
                StockInQty = CurrentResultStockInQty;

                IsPartial = dto.IsPartial;
                NextInspectionDate = dto.NextInspectionDate;
                PartialReason = dto.PartialReason ?? string.Empty;
                ShortageReason = dto.ShortageReason ?? string.Empty;
                Memo = dto.Memo ?? string.Empty;

                Defects.Clear();
                if (dto.Defects != null)
                {
                    foreach (var defect in dto.Defects)
                    {
                        var edit = new InspectionResultDefectEditModel
                        {
                            DefectTypeId = defect.DefectTypeId,
                            DefectQty = defect.DefectQty,
                            Disposition = string.IsNullOrWhiteSpace(defect.Disposition)
                                ? "NOT_SHIPPABLE"
                                : defect.Disposition,
                            DefectCode = string.Empty,
                            Category1Name = string.Empty,
                            Category2Name = string.Empty,
                            DefectTypeMemo = defect.Memo ?? string.Empty,
                        };

                        if (defect.Attachments != null)
                        {
                            foreach (var att in defect.Attachments)
                            {
                                edit.Attachments.Add(new DefectAttachmentEditModel
                                {
                                    InspectionDefectAttachmentId = att.InspectionDefectAttachmentId,
                                    FileUri = att.FileUri,
                                    FileName = att.FileName ?? string.Empty,
                                    MimeType = att.MimeType ?? string.Empty,
                                    Memo = att.Memo ?? string.Empty,
                                });
                            }
                        }

                        Defects.Add(edit);
                    }

                    await LoadDefectTypeDisplayValuesAsync();
                }

                RecalculateTotals();
            }
            catch (Exception error)
            {
                _loadFailed = true;
                _reportError(error);
            }
            finally
            {
                _isInitializing = false;
                RecalculateTotals();
                IsLoading = false;
            }
        }

        private async Task LoadDefectTypeDisplayValuesAsync()
        {
            var defectTypeIds = Defects
                .Where(x => x.DefectTypeId.HasValue)
                .Select(x => x.DefectTypeId!.Value)
                .Distinct()
                .ToList();

            if (defectTypeIds.Count == 0)
            {
                return;
            }

            var lookupMap = new Dictionary<int, InspectionResultDefectTypeLookupDto>();

            foreach (var defectTypeId in defectTypeIds)
            {
                var result = await _apiClient.GetAsync<InspectionResultDefectTypeLookupDto>(
                    $"{ApiRoutes.DefectTypes}/{defectTypeId}");

                if (!result.Success || result.Data == null)
                {
                    continue;
                }

                lookupMap[defectTypeId] = result.Data;
            }

            foreach (var defect in Defects)
            {
                if (!defect.DefectTypeId.HasValue)
                {
                    continue;
                }

                if (!lookupMap.TryGetValue(defect.DefectTypeId.Value, out var defectType))
                {
                    continue;
                }

                defect.DefectCode = defectType.DefectCode?.Trim().ToUpperInvariant() ?? string.Empty;
                defect.Category1Name = defectType.Category1Name?.Trim() ?? string.Empty;
                defect.Category2Name = defectType.Category2Name?.Trim() ?? string.Empty;
                // Existing results own their saved memo, including an intentionally empty memo.
            }
        }

        private void RecalculateTotals()
        {
            OnPropertyChanged(nameof(TotalQty));
            OnPropertyChanged(nameof(ReceivedQty));
            OnPropertyChanged(nameof(TotalDisposalQty));

            AccumulatedGoodQty = _baseAccumulatedGoodQty + GoodQty;
            AccumulatedDefectQty = _baseAccumulatedDefectQty + DefectQty;
            AccumulatedDefectShipQty = _baseAccumulatedDefectShipQty + DefectShipQty;
            AccumulatedInspectedQty = _baseAccumulatedInspectedQty + TotalQty;
            AccumulatedUninspectedQty = _baseAccumulatedUninspectedQty + UninspectedQty;
            OnPropertyChanged(nameof(AccumulatedReceivedQty));
            OnPropertyChanged(nameof(PlanShortageQty));
            OnPropertyChanged(nameof(SellableQty));

            RecalculateInventoryPreview();
        }

        private void RecalculateInventoryPreview()
        {
            if (_isInitializing || _isRecalculatingInventoryPreview) return;
            try
            {
                _isRecalculatingInventoryPreview = true;
                // Keep manual shipment/disposal unchanged. A negative remainder is a visible error.
                if (CanEdit && string.IsNullOrWhiteSpace(SettlementError))
                    StockInQty = Quantities.ResidualStockIn;
                OnPropertyChanged(nameof(CurrentRoundShipQty));
                OnPropertyChanged(nameof(TotalShippedQty));
                OnPropertyChanged(nameof(RemainingAfterCurrentQty));
                OnPropertyChanged(nameof(AllocationPreview));
            }
            finally { _isRecalculatingInventoryPreview = false; }
        }

        private void AddDefect()
        {
            if (!CanEdit)
            {
                return;
            }

            var item = new InspectionResultDefectEditModel();
            Defects.Add(item);
            SelectedDefect = item;
        }

        private void RemoveDefect(InspectionResultDefectEditModel? item)
        {
            if (!CanEdit || item == null)
            {
                return;
            }

            Defects.Remove(item);
        }

        private void RemovePhoto(DefectAttachmentEditModel? item)
        {
            if (!CanEdit || item == null)
            {
                return;
            }

            foreach (var defect in Defects)
            {
                if (defect.Attachments.Contains(item))
                {
                    defect.Attachments.Remove(item);
                    return;
                }
            }
        }

        private async Task UploadPhotoAsync(InspectionResultDefectEditModel? defect)
        {
            if (!CanEdit)
            {
                return;
            }

            if (defect == null)
            {
                _messageService.ShowWarning("불량내역을 선택해주세요.");
                return;
            }

            var dialog = new OpenFileDialog
            {
                Filter = "Image Files|*.jpg;*.jpeg;*.png;*.bmp;*.webp",
                Multiselect = false,
            };

            if (dialog.ShowDialog() != true)
            {
                return;
            }

            try
            {
                IsLoading = true;
                var attachment = await _photos.UploadAsync(InspectionScheduleId, dialog.FileName);
                if (attachment != null) defect.Attachments.Add(attachment);
            }
            finally { IsLoading = false; }
        }

        private async Task OpenPhotoAsync(DefectAttachmentEditModel? attachment)
        {
            try
            {
                IsLoading = true;
                await _photos.OpenAsync(attachment);
            }
            finally { IsLoading = false; }
        }

        private InspectionResultDraft CreateDraft() => new()
        {
            Quantities = Quantities, IsPartial = IsPartial, NextInspectionDate = NextInspectionDate,
            PartialReason = PartialReason, ShortageReason = ShortageReason, Memo = Memo,
            ExpectedUpdatedAt = _expectedUpdatedAt, Defects = Defects
        };

        private InspectionSaveContext SaveContext() => new()
        {
            LoadFailed = _loadFailed, SettlementError = SettlementError, StockError = StockError,
            AvailableStock = CurrentStockQty,
            OriginalOwnInventoryIn = _originalOwnInventoryInQty,
            OriginalStockShip = CurrentResultStockShipQty, OriginalProductionShip = CurrentResultResultShipQty
        };

        private async Task SaveAsync()
        {
            if (!CanEdit)
            {
                return;
            }

            var draft = CreateDraft();
            var validationError = InspectionResultFormPolicy.Validate(draft, SaveContext());
            if (validationError != null)
            {
                _messageService.ShowWarning(validationError);
                return;
            }

            try
            {
                IsLoading = true;

                var request = InspectionResultFormPolicy.BuildRequest(draft);

                var result = await _apiClient.PutAsync<InspectionResultUpsertRequest, InspectionResultUpsertResponse>(
                    $"{ApiRoutes.InspectionSchedules}/{InspectionScheduleId}/result",
                    request);

                if (!result.Success)
                {
                    _messageService.ShowError(result.Message ?? "검수실적 저장에 실패했습니다.");
                    return;
                }

                _messageService.ShowInfo("검수실적 및 출고 이력이 저장되었습니다.");
                CloseRequested?.Invoke(true);
            }
            finally
            {
                IsLoading = false;
            }
        }
    }
}
