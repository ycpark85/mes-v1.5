using Mes.Wpf.Core.Common;
using System;

namespace Mes.Wpf.Modules.Lots.Dtos
{
    public class LotCreateEditModel : ViewModelBase
    {
        private long _orderLineId;
        private string _orderNo = string.Empty;
        private string _partnerName = string.Empty;
        private string _productCode = string.Empty;
        private string _productName = string.Empty;
        private int _orderQty;
        private string _uom = string.Empty;
        private DateTime _dueDate;
        private string _status = string.Empty;

        private int? _panelWidthMm;
        private int? _panelLengthMm;
        private int? _cutQtyPerPanel;
        private string _productSpec = string.Empty;

        private long? _drawingId;
        private string _drawingNo = string.Empty;
        private string _drawingRevisionNo = string.Empty;

        private long? _drawingFileId;
        private string _drawingFileName = string.Empty;
        private long? _originalFileId;
        private string _originalFileName = string.Empty;
        private long? _plateFileId;
        private string _plateFileName = string.Empty;

        private bool _isRework;
        private long? _parentLotId;
        private string _parentLotNo = string.Empty;
        private string _parentLotStatus = string.Empty;

        private string _materialLotNo = string.Empty;
        private decimal? _materialUsedQty;
        private int? _materialSheetCount;
        private int? _planQty;
        private string? _memo;

        public long OrderLineId
        {
            get => _orderLineId;
            set => SetProperty(ref _orderLineId, value);
        }

        public string OrderNo
        {
            get => _orderNo;
            set => SetProperty(ref _orderNo, value);
        }

        public string PartnerName
        {
            get => _partnerName;
            set => SetProperty(ref _partnerName, value);
        }

        private string? _mesProductCode;
        public string? MesProductCode { get => _mesProductCode; set => SetProperty(ref _mesProductCode, value); }

        public string ProductCode
        {
            get => _productCode;
            set => SetProperty(ref _productCode, value);
        }

        public string ProductName
        {
            get => _productName;
            set => SetProperty(ref _productName, value);
        }

        public int OrderQty
        {
            get => _orderQty;
            set => SetProperty(ref _orderQty, value);
        }

        public string Uom
        {
            get => _uom;
            set => SetProperty(ref _uom, value);
        }

        public DateTime DueDate
        {
            get => _dueDate;
            set => SetProperty(ref _dueDate, value);
        }

        public string Status
        {
            get => _status;
            set => SetProperty(ref _status, value);
        }

        public int? PanelWidthMm
        {
            get => _panelWidthMm;
            set
            {
                if (SetProperty(ref _panelWidthMm, value))
                {
                    OnPropertyChanged(nameof(PanelSpecText));
                }
            }
        }

        public int? PanelLengthMm
        {
            get => _panelLengthMm;
            set
            {
                if (SetProperty(ref _panelLengthMm, value))
                {
                    OnPropertyChanged(nameof(PanelSpecText));
                }
            }
        }

        public int? CutQtyPerPanel
        {
            get => _cutQtyPerPanel;
            set => SetProperty(ref _cutQtyPerPanel, value);
        }

        public string ProductSpec
        {
            get => _productSpec;
            set => SetProperty(ref _productSpec, value);
        }

        public long? DrawingId
        {
            get => _drawingId;
            set => SetProperty(ref _drawingId, value);
        }

        public string DrawingNo
        {
            get => _drawingNo;
            set => SetProperty(ref _drawingNo, value);
        }

        public string DrawingRevisionNo
        {
            get => _drawingRevisionNo;
            set => SetProperty(ref _drawingRevisionNo, value);
        }

        public long? DrawingFileId
        {
            get => _drawingFileId;
            set => SetProperty(ref _drawingFileId, value);
        }

        public string DrawingFileName
        {
            get => _drawingFileName;
            set => SetProperty(ref _drawingFileName, value);
        }

        public long? OriginalFileId
        {
            get => _originalFileId;
            set => SetProperty(ref _originalFileId, value);
        }

        public string OriginalFileName
        {
            get => _originalFileName;
            set => SetProperty(ref _originalFileName, value);
        }

        public long? PlateFileId
        {
            get => _plateFileId;
            set => SetProperty(ref _plateFileId, value);
        }

        public string PlateFileName
        {
            get => _plateFileName;
            set => SetProperty(ref _plateFileName, value);
        }

        public bool IsRework
        {
            get => _isRework;
            set => SetProperty(ref _isRework, value);
        }

        public long? ParentLotId
        {
            get => _parentLotId;
            set => SetProperty(ref _parentLotId, value);
        }

        public string ParentLotNo
        {
            get => _parentLotNo;
            set => SetProperty(ref _parentLotNo, value);
        }

        public string ParentLotStatus
        {
            get => _parentLotStatus;
            set => SetProperty(ref _parentLotStatus, value);
        }

        public string MaterialLotNo
        {
            get => _materialLotNo;
            set => SetProperty(ref _materialLotNo, value);
        }

        public decimal? MaterialUsedQty
        {
            get => _materialUsedQty;
            set => SetProperty(ref _materialUsedQty, value);
        }

        public int? MaterialSheetCount
        {
            get => _materialSheetCount;
            set => SetProperty(ref _materialSheetCount, value);
        }

        public int? PlanQty
        {
            get => _planQty;
            set => SetProperty(ref _planQty, value);
        }

        public string? Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public string PanelSpecText =>
            PanelWidthMm.HasValue && PanelLengthMm.HasValue
                ? $"{PanelWidthMm.Value} X {PanelLengthMm.Value}"
                : string.Empty;

        public void LoadFromContext(LotCreateContextDto dto)
        {
            OrderLineId = dto.OrderLineId;
            OrderNo = dto.OrderNo;
            PartnerName = dto.PartnerName;
            MesProductCode = dto.MesProductCode;
            ProductCode = dto.ProductCode;
            ProductName = dto.ProductName;
            OrderQty = dto.OrderQty;
            Uom = dto.Uom;
            DueDate = dto.DueDate;
            Status = dto.Status;

            PanelWidthMm = dto.PanelWidthMm;
            PanelLengthMm = dto.PanelLengthMm;
            CutQtyPerPanel = dto.CutQtyPerPanel;
            ProductSpec = dto.ProductSpec ?? string.Empty;

            DrawingId = dto.Drawing?.DrawingId;
            DrawingNo = dto.Drawing?.DrawingNo ?? string.Empty;
            DrawingRevisionNo = dto.Drawing?.CurrentRevisionNo ?? string.Empty;

            DrawingFileId = dto.Drawing?.DrawingFileId;
            DrawingFileName = dto.Drawing?.DrawingFileName ?? string.Empty;

            OriginalFileId = dto.Drawing?.OriginalFileId;
            OriginalFileName = dto.Drawing?.OriginalFileName ?? string.Empty;

            PlateFileId = dto.Drawing?.PlateFileId;
            PlateFileName = dto.Drawing?.PlateFileName ?? string.Empty;

            PlanQty = dto.OrderQty;

            IsRework = true;
            ParentLotId = null;
            ParentLotNo = string.Empty;
            ParentLotStatus = string.Empty;
        }

        public void ApplyParentLot(LotCreatePrimaryCandidateDto? dto)
        {
            if (dto == null)
            {
                ParentLotId = null;
                ParentLotNo = string.Empty;
                ParentLotStatus = string.Empty;
                return;
            }

            ParentLotId = dto.LotId;
            ParentLotNo = dto.LotNo;
            ParentLotStatus = dto.Status;
        }

        public void Clear()
        {
            OrderLineId = 0;
            OrderNo = string.Empty;
            PartnerName = string.Empty;
            ProductCode = string.Empty;
            MesProductCode = null;
            ProductName = string.Empty;
            OrderQty = 0;
            Uom = string.Empty;
            DueDate = DateTime.Today;
            Status = string.Empty;

            PanelWidthMm = null;
            PanelLengthMm = null;
            CutQtyPerPanel = null;
            ProductSpec = string.Empty;

            DrawingId = null;
            DrawingNo = string.Empty;
            DrawingRevisionNo = string.Empty;

            DrawingFileId = null;
            DrawingFileName = string.Empty;
            OriginalFileId = null;
            OriginalFileName = string.Empty;
            PlateFileId = null;
            PlateFileName = string.Empty;

            IsRework = true;
            ParentLotId = null;
            ParentLotNo = string.Empty;
            ParentLotStatus = string.Empty;

            MaterialLotNo = string.Empty;
            MaterialUsedQty = null;
            MaterialSheetCount = null;
            PlanQty = null;
            Memo = null;
        }
    }
}