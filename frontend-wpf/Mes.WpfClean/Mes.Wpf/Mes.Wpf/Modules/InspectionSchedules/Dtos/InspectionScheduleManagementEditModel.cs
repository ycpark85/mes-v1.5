using System;
using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.InspectionSchedules.Dtos
{
    public class InspectionScheduleManagementEditModel : ViewModelBase
    {
        private long? _inspectionScheduleId;
        private long? _lotId;
        private string _lotNo = string.Empty;
        private DateTime? _inspectionDate;
        private string _status = string.Empty;
        private int? _daySeq;
        private DateTime? _dueDate;
        private string _partnerName = string.Empty;
        private string _productCode = string.Empty;
        private string _productName = string.Empty;
        private string _memo = string.Empty;

        public long? InspectionScheduleId
        {
            get => _inspectionScheduleId;
            set => SetProperty(ref _inspectionScheduleId, value);
        }

        public long? LotId
        {
            get => _lotId;
            set => SetProperty(ref _lotId, value);
        }

        public string LotNo
        {
            get => _lotNo;
            set => SetProperty(ref _lotNo, value);
        }

        public DateTime? InspectionDate
        {
            get => _inspectionDate;
            set => SetProperty(ref _inspectionDate, value);
        }

        public string Status
        {
            get => _status;
            set => SetProperty(ref _status, value);
        }

        public int? DaySeq
        {
            get => _daySeq;
            set => SetProperty(ref _daySeq, value);
        }

        public DateTime? DueDate
        {
            get => _dueDate;
            set => SetProperty(ref _dueDate, value);
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

        public string Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public void LoadFromDto(InspectionScheduleListItemDto dto)
        {
            InspectionScheduleId = dto.InspectionScheduleId;
            LotId = dto.LotId;
            LotNo = dto.LotNo ?? string.Empty;
            InspectionDate = dto.InspectionDate;
            Status = dto.Status ?? string.Empty;
            DaySeq = dto.DaySeq;
            DueDate = dto.DueDate;
            PartnerName = dto.PartnerName ?? string.Empty;
            MesProductCode = dto.MesProductCode;
            ProductCode = dto.ProductCode ?? string.Empty;
            ProductName = dto.ProductName ?? string.Empty;
            Memo = dto.Memo ?? string.Empty;
        }

        public void Clear()
        {
            InspectionScheduleId = null;
            LotId = null;
            LotNo = string.Empty;
            InspectionDate = DateTime.Today;
            Status = string.Empty;
            DaySeq = null;
            DueDate = null;
            PartnerName = string.Empty;
            ProductCode = string.Empty;
            MesProductCode = null;
            ProductName = string.Empty;
            Memo = string.Empty;
        }
    }
}