using System;
using System.Collections.ObjectModel;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows.Input;
using Microsoft.Win32;
using Mes.Wpf.Core.Common;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;

namespace Mes.Wpf.Modules.InspectionSchedules.ViewModels
{
    public class InspectionResultWindowViewModel : ViewModelBase
    {
        private readonly IApiClient _apiClient;
        private readonly IMessageService _messageService;
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
        private int _alreadyShippedQty;
        private int _remainingShipTargetQty;

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
        private bool _isAutoShipmentPreviewUpdating;

        private int _expectedShipQty;
        private int _shortageQty;
        public int ShipmentWaitingQty => ExpectedShipQty;

        public event Action<bool>? CloseRequested;
        public event Action? EditRequested;

        public IApiClient ApiClient => _apiClient;
        public IMessageService MessageService => _messageService;

        public InspectionResultWindowViewModel(
            IApiClient apiClient,
            IMessageService messageService,
            bool canEdit = true,
            bool canRequestEdit = false)
        {
            _apiClient = apiClient;
            _messageService = messageService;
            _canEdit = canEdit;
            _canRequestEdit = canRequestEdit;

            Defects = new ObservableCollection<InspectionResultDefectEditModel>();

            AddDefectCommand = new RelayCommand(_ => AddDefect(), _ => CanEdit);
            RemoveDefectCommand = new RelayCommand(
                x => RemoveDefect(x as InspectionResultDefectEditModel),
                x => CanEdit && x is InspectionResultDefectEditModel);
            UploadPhotoCommand = new RelayCommand(
                async x => await UploadPhotoAsync(x as InspectionResultDefectEditModel),
                x => CanEdit && !IsLoading && x is InspectionResultDefectEditModel);
            RemovePhotoCommand = new RelayCommand(
                x => RemovePhoto(x as DefectAttachmentEditModel),
                x => CanEdit && x is DefectAttachmentEditModel);
            OpenPhotoCommand = new RelayCommand(
                async x => await OpenPhotoAsync(x as DefectAttachmentEditModel),
                x => !IsLoading && x is DefectAttachmentEditModel);
            SaveCommand = new AsyncRelayCommand(SaveAsync, () => CanEdit && !IsLoading);
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

        public int StockLotTotalQty => StockLots.Sum(x => x.StockQty);

        public int StockLotAllocatedQty => StockLots.Sum(x => x.AllocatedShipQty);

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

        public int TotalQty => GoodQty + DefectShipQty + DefectQty;
        public int ReceivedQty => TotalQty + UninspectedQty;
        public int TotalDisposalQty => DiscardQty + UninspectedQty;
        public int SellableQty =>
            IsPartial
                ? GoodQty + DefectShipQty
                : AccumulatedGoodQty + AccumulatedDefectShipQty;

        public bool CanEdit => _canEdit;
        public bool CanRequestEdit => _canRequestEdit && ScheduleStatus == "DONE";
        public bool IsReadOnlyMode => !CanEdit;
        public string CloseButtonText => CanEdit ? "취소" : "닫기";
        public bool IsShipmentInputEnabled => CanEdit && !IsPartial;

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
                    RecalculateInventoryPreview();
                }
            }
        }

        public int AlreadyShippedQty
        {
            get => _alreadyShippedQty;
            set
            {
                if (SetProperty(ref _alreadyShippedQty, value))
                {
                    RecalculateInventoryPreview();
                }
            }
        }

        public int RemainingShipTargetQty
        {
            get => _remainingShipTargetQty;
            set
            {
                if (SetProperty(ref _remainingShipTargetQty, value))
                {
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

        public int ExpectedShipQty
        {
            get => _expectedShipQty;
            set => SetProperty(ref _expectedShipQty, value);
        }

        public int ShortageQty
        {
            get => _shortageQty;
            set => SetProperty(ref _shortageQty, value);
        }

        public bool IsPartial
        {
            get => _isPartial;
            set
            {
                if (SetProperty(ref _isPartial, value))
                {
                    OnPropertyChanged(nameof(IsShipmentInputEnabled));

                    if (value)
                    {
                        StockShipQty = 0;
                        ResultShipQty = 0;
                        StockInQty = 0;
                        DiscardQty = 0;
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

                    if (UploadPhotoCommand is RelayCommand uploadPhotoCommand)
                    {
                        uploadPhotoCommand.RaiseCanExecuteChanged();
                    }

                    if (RemovePhotoCommand is RelayCommand removePhotoCommand)
                    {
                        removePhotoCommand.RaiseCanExecuteChanged();
                    }

                    if (OpenPhotoCommand is RelayCommand openPhotoCommand)
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
            try
            {
                IsLoading = true;

                var result = await _apiClient.GetAsync<InspectionResultResponse>(
                    $"{ApiRoutes.InspectionSchedules}/{InspectionScheduleId}/result");

                if (!result.Success)
                {
                    return;
                }

                var response = result.Data;
                var dto = response?.Result;
                var accumulated = response?.Accumulated;
                var inventory = response?.Inventory;

                ScheduleStatus = response?.ScheduleStatus ?? string.Empty;
                InspectionRound = response?.InspectionRound ?? 0;
                InspectionRoundCount = response?.InspectionRoundCount ?? 0;
                Rounds = response?.Rounds ?? new ObservableCollection<InspectionRoundSummaryDto>();

                CurrentStockQty = inventory?.CurrentStockQty ?? 0;
                ShipTargetQty = inventory?.ShipTargetQty ?? OrderQty;
                AlreadyShippedQty = inventory?.AlreadyShippedQty ?? 0;
                RemainingShipTargetQty = inventory?.RemainingShipTargetQty
                    ?? Math.Max(ShipTargetQty - AlreadyShippedQty, 0);

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

                    StockShipQty = CurrentResultStockShipQty;
                    ResultShipQty = CurrentResultResultShipQty;
                    DiscardQty = CurrentResultDiscardQty;
                    StockInQty = CurrentResultStockInQty;

                    IsPartial = false;
                    NextInspectionDate = null;
                    PartialReason = string.Empty;
                    Memo = string.Empty;
                    Defects.Clear();

                    await LoadStockLotsAsync();
                    if (StockShipQty <= 0)
                    {
                        ApplyAutoShipmentPreview();
                    }
                    else
                    {
                        RecalculateInventoryPreview();
                    }
                    AllocateStockLotsByFifo();

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

                await LoadStockLotsAsync();
                AllocateStockLotsByFifo();

                RecalculateTotals();
            }
            finally
            {
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
                defect.DefectTypeMemo = defectType.Memo?.Trim() ?? string.Empty;
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
            OnPropertyChanged(nameof(SellableQty));

            RecalculateInventoryPreview();
        }

        private void RecalculateInventoryPreview()
        {
            if (_isRecalculatingInventoryPreview)
            {
                return;
            }

            try
            {
                _isRecalculatingInventoryPreview = true;

                var sellableQty = Math.Max(SellableQty, 0);

                if (IsPartial)
                {
                    if (_stockShipQty != 0)
                    {
                        _stockShipQty = 0;
                        OnPropertyChanged(nameof(StockShipQty));
                    }

                    if (_resultShipQty != 0)
                    {
                        _resultShipQty = 0;
                        OnPropertyChanged(nameof(ResultShipQty));
                    }

                    if (_stockInQty != 0)
                    {
                        _stockInQty = 0;
                        OnPropertyChanged(nameof(StockInQty));
                    }

                    if (_discardQty != 0)
                    {
                        _discardQty = 0;
                        OnPropertyChanged(nameof(DiscardQty));
                        OnPropertyChanged(nameof(TotalDisposalQty));
                    }

                    ExpectedShipQty = 0;
                    ShortageQty = Math.Max(RemainingShipTargetQty, 0);

                    OnPropertyChanged(nameof(ExpectedShipQty));
                    OnPropertyChanged(nameof(ShipmentWaitingQty));
                    OnPropertyChanged(nameof(ShortageQty));

                    AllocateStockLotsByFifo();
                    return;
                }

                var stockShipQty = Math.Max(StockShipQty, 0);
                var resultShipQty = Math.Max(ResultShipQty, 0);
                var discardQty = Math.Max(DiscardQty, 0);

                if (stockShipQty > CurrentStockQty)
                {
                    stockShipQty = CurrentStockQty;
                }

                if (resultShipQty > sellableQty)
                {
                    resultShipQty = sellableQty;
                }

                var maxDiscardQty = Math.Max(sellableQty - resultShipQty, 0);
                if (discardQty > maxDiscardQty)
                {
                    discardQty = maxDiscardQty;
                }

                var stockInQty = Math.Max(sellableQty - resultShipQty - discardQty, 0);
                var actualShipQty = stockShipQty + resultShipQty;

                if (_stockShipQty != stockShipQty)
                {
                    _stockShipQty = stockShipQty;
                    OnPropertyChanged(nameof(StockShipQty));
                }

                if (_resultShipQty != resultShipQty)
                {
                    _resultShipQty = resultShipQty;
                    OnPropertyChanged(nameof(ResultShipQty));
                }

                if (_stockInQty != stockInQty)
                {
                    _stockInQty = stockInQty;
                    OnPropertyChanged(nameof(StockInQty));
                }

                if (_discardQty != discardQty)
                {
                    _discardQty = discardQty;
                    OnPropertyChanged(nameof(DiscardQty));
                    OnPropertyChanged(nameof(TotalDisposalQty));
                }

                ExpectedShipQty = actualShipQty;
                ShortageQty = Math.Max(RemainingShipTargetQty - actualShipQty, 0);

                OnPropertyChanged(nameof(ExpectedShipQty));
                OnPropertyChanged(nameof(ShipmentWaitingQty));
                OnPropertyChanged(nameof(ShortageQty));

                AllocateStockLotsByFifo();
            }
            finally
            {
                _isRecalculatingInventoryPreview = false;
            }
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

                using var content = new MultipartFormDataContent();
                using var fileStream = File.OpenRead(dialog.FileName);
                using var streamContent = new StreamContent(fileStream);

                var ext = Path.GetExtension(dialog.FileName)?.ToLowerInvariant();
                streamContent.Headers.ContentType = ext switch
                {
                    ".jpg" or ".jpeg" => new System.Net.Http.Headers.MediaTypeHeaderValue("image/jpeg"),
                    ".png" => new System.Net.Http.Headers.MediaTypeHeaderValue("image/png"),
                    ".bmp" => new System.Net.Http.Headers.MediaTypeHeaderValue("image/bmp"),
                    ".webp" => new System.Net.Http.Headers.MediaTypeHeaderValue("image/webp"),
                    _ => new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream")
                };

                content.Add(streamContent, "file", Path.GetFileName(dialog.FileName));

                var result = await _apiClient.PostMultipartAsync<DefectAttachmentUploadResponse>(
                    $"{ApiRoutes.InspectionSchedules}/{InspectionScheduleId}/result/photos",
                    content);

                if (!result.Success || result.Data == null)
                {
                    _messageService.ShowError(result.Message ?? "불량사진 업로드에 실패했습니다.");
                    return;
                }

                defect.Attachments.Add(new DefectAttachmentEditModel
                {
                    FileUri = result.Data.FileUri,
                    FileName = result.Data.FileName,
                    MimeType = result.Data.MimeType ?? string.Empty,
                    Memo = string.Empty,
                    LocalFilePath = dialog.FileName,
                });
            }
            finally
            {
                IsLoading = false;
            }
        }

        private async Task OpenPhotoAsync(DefectAttachmentEditModel? attachment)
        {
            if (attachment == null)
            {
                return;
            }

            try
            {
                if (!string.IsNullOrWhiteSpace(attachment.LocalFilePath)
                    && File.Exists(attachment.LocalFilePath))
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = attachment.LocalFilePath,
                        UseShellExecute = true,
                    });
                    return;
                }

                if (!attachment.InspectionDefectAttachmentId.HasValue)
                {
                    _messageService.ShowWarning("저장된 이미지 정보가 없습니다.");
                    return;
                }

                var extension = Path.GetExtension(attachment.FileName);
                if (string.IsNullOrWhiteSpace(extension))
                {
                    extension = attachment.MimeType?.ToLowerInvariant() switch
                    {
                        "image/png" => ".png",
                        "image/bmp" => ".bmp",
                        "image/webp" => ".webp",
                        _ => ".jpg",
                    };
                }

                var tempDirectory = Path.Combine(Path.GetTempPath(), "MesWpf", "DefectImages");
                Directory.CreateDirectory(tempDirectory);

                var safeFileName = Path.GetFileName(attachment.FileName);
                if (string.IsNullOrWhiteSpace(safeFileName))
                {
                    safeFileName = $"inspection_attachment_{attachment.InspectionDefectAttachmentId}{extension}";
                }
                else if (string.IsNullOrWhiteSpace(Path.GetExtension(safeFileName)))
                {
                    safeFileName += extension;
                }

                var tempPath = Path.Combine(tempDirectory, safeFileName);
                var route = $"{ApiRoutes.InspectionSchedules}/result/attachments/{attachment.InspectionDefectAttachmentId}/content";
                var download = await _apiClient.DownloadFileAsync(route, tempPath);

                if (!download.Success)
                {
                    _messageService.ShowError(download.Message ?? "이미지 다운로드에 실패했습니다.");
                    return;
                }

                Process.Start(new ProcessStartInfo
                {
                    FileName = tempPath,
                    UseShellExecute = true,
                });
            }
            catch (Exception ex)
            {
                _messageService.ShowError($"이미지 열기 중 오류가 발생했습니다.\n{ex.Message}");
            }
        }

        private async Task SaveAsync()
        {
            if (!CanEdit)
            {
                return;
            }

            if (ReceivedQty <= 0)
            {
                _messageService.ShowWarning("검수수량 또는 미검수수량을 입력해주세요.");
                return;
            }

            if (!IsPartial && ResultShipQty + StockInQty + DiscardQty != SellableQty)
            {
                _messageService.ShowWarning("생산 출고수량 + 판매가능폐기 + 재고편입수량은 판매가능수량과 같아야 합니다.");
                return;
            }

            if (!IsPartial && StockShipQty > CurrentStockQty)
            {
                _messageService.ShowWarning("재고 출고수량이 현재 재고수량을 초과할 수 없습니다.");
                return;
            }

            if (IsPartial && !NextInspectionDate.HasValue)
            {
                _messageService.ShowWarning("분할검수일 경우 다음 검수일자를 입력해주세요.");
                return;
            }

            if (IsPartial && string.IsNullOrWhiteSpace(PartialReason))
            {
                _messageService.ShowWarning("분할검수일 경우 사유/메모를 입력해주세요.");
                return;
            }

            if (DefectQty > 0 && Defects.Count == 0)
            {
                _messageService.ShowWarning("불량수량이 있으면 불량내역을 등록해주세요.");
                return;
            }

            if (Defects.Any(x => !x.DefectTypeId.HasValue))
            {
                _messageService.ShowWarning("불량유형을 입력해주세요.");
                return;
            }

            try
            {
                IsLoading = true;

                var request = new InspectionResultUpsertRequest
                {
                    GoodQty = GoodQty,
                    DefectShipQty = DefectShipQty,
                    DefectQty = DefectQty,
                    UninspectedQty = IsPartial ? 0 : UninspectedQty,
                    StockShipQty = IsPartial ? 0 : StockShipQty,
                    ResultShipQty = IsPartial ? 0 : ResultShipQty,
                    StockInQty = IsPartial ? 0 : StockInQty,
                    DiscardQty = IsPartial ? 0 : DiscardQty,
                    IsPartial = IsPartial,
                    NextInspectionDate = IsPartial ? NextInspectionDate?.Date : null,
                    PartialReason = IsPartial ? PartialReason.Trim() : null,
                    Memo = string.IsNullOrWhiteSpace(Memo) ? null : Memo.Trim(),
                    ExpectedUpdatedAt = _expectedUpdatedAt,
                };

                foreach (var defect in Defects)
                {
                    request.Defects.Add(new InspectionResultDefectRequest
                    {
                        DefectTypeId = defect.DefectTypeId ?? 0,
                        DefectQty = defect.DefectQty,
                        Disposition = string.IsNullOrWhiteSpace(defect.Disposition)
                            ? "NOT_SHIPPABLE"
                            : defect.Disposition,
                        Memo = string.IsNullOrWhiteSpace(defect.Memo) ? null : defect.Memo.Trim(),
                        Attachments = new ObservableCollection<DefectAttachmentRequest>(
                            defect.Attachments.Select(x => new DefectAttachmentRequest
                            {
                                FileUri = x.FileUri,
                                FileName = string.IsNullOrWhiteSpace(x.FileName) ? null : x.FileName,
                                MimeType = string.IsNullOrWhiteSpace(x.MimeType) ? null : x.MimeType,
                                Memo = string.IsNullOrWhiteSpace(x.Memo) ? null : x.Memo.Trim()
                            }))
                    });
                }

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
        private async Task LoadStockLotsAsync()
        {
            var route = $"{ApiRoutes.InspectionSchedules}/{InspectionScheduleId}/stock-lots";

            var result = await _apiClient.GetAsync<InspectionStockLotListDto>(route);

            if (!result.Success || result.Data == null)
            {
                StockLots.Clear();
                OnPropertyChanged(nameof(StockLotTotalQty));
                OnPropertyChanged(nameof(StockLotAllocatedQty));
                return;
            }

            StockLots = result.Data.Items ?? new ObservableCollection<InspectionStockLotDto>();

            OnPropertyChanged(nameof(StockLotTotalQty));
            OnPropertyChanged(nameof(StockLotAllocatedQty));
        }
        private void ApplyAutoShipmentPreview()
        {
            if (_isAutoShipmentPreviewUpdating)
            {
                return;
            }

            try
            {
                _isAutoShipmentPreviewUpdating = true;

                if (IsPartial)
                {
                    StockShipQty = 0;
                    ResultShipQty = 0;
                    StockInQty = 0;
                    DiscardQty = 0;
                    UninspectedQty = 0;
                    return;
                }

                var sellableQty = Math.Max(SellableQty, 0);
                var remainingTargetQty = Math.Max(RemainingShipTargetQty, 0);
                var currentStockQty = Math.Max(CurrentStockQty, 0);

                var stockShipQty = Math.Min(currentStockQty, remainingTargetQty);
                var resultShipQty = Math.Min(sellableQty, Math.Max(remainingTargetQty - stockShipQty, 0));
                var stockInQty = Math.Max(sellableQty - resultShipQty, 0);

                StockShipQty = stockShipQty;
                ResultShipQty = resultShipQty;
                DiscardQty = 0;
                StockInQty = stockInQty;
            }
            finally
            {
                _isAutoShipmentPreviewUpdating = false;
            }

            AllocateStockLotsByFifo();
        }
        private void AllocateStockLotsByFifo()
        {
            var remainingQty = Math.Max(StockShipQty, 0);

            foreach (var lot in StockLots)
            {
                var allocatedQty = Math.Min(lot.StockQty, remainingQty);
                lot.AllocatedShipQty = allocatedQty;
                remainingQty -= allocatedQty;
            }

            OnPropertyChanged(nameof(StockLotTotalQty));
            OnPropertyChanged(nameof(StockLotAllocatedQty));
        }
    }
}
