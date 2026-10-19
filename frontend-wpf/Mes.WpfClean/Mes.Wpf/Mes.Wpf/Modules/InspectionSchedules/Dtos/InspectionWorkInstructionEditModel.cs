using System;
using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.InspectionSchedules.Dtos
{
    public class InspectionWorkInstructionEditModel : ViewModelBase
    {
        private long? _lotId;
        private long? _outsourceWorkGroupId;
        private long? _outsourceWorkGroupItemId;
        private string _bundleNo = string.Empty;
        private string _lotNo = string.Empty;
        private string _productCode = string.Empty;
        private string _productName = string.Empty;
        private string _partnerName = string.Empty;
        private DateTime? _inspectionDate;
        private string _memo = string.Empty;

        public long? LotId
        {
            get => _lotId;
            set => SetProperty(ref _lotId, value);
        }

        public long? OutsourceWorkGroupId
        {
            get => _outsourceWorkGroupId;
            set => SetProperty(ref _outsourceWorkGroupId, value);
        }

        public long? OutsourceWorkGroupItemId
        {
            get => _outsourceWorkGroupItemId;
            set => SetProperty(ref _outsourceWorkGroupItemId, value);
        }

        public string BundleNo
        {
            get => _bundleNo;
            set => SetProperty(ref _bundleNo, value);
        }

        public string LotNo
        {
            get => _lotNo;
            set => SetProperty(ref _lotNo, value);
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

        public string PartnerName
        {
            get => _partnerName;
            set => SetProperty(ref _partnerName, value);
        }

        public DateTime? InspectionDate
        {
            get => _inspectionDate;
            set => SetProperty(ref _inspectionDate, value);
        }

        public string Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public void LoadFromDto(InspectionWorkInstructionLotListItemDto dto)
        {
            LotId = dto.LotId;
            OutsourceWorkGroupId = dto.OutsourceWorkGroupId;
            OutsourceWorkGroupItemId = dto.OutsourceWorkGroupItemId;
            BundleNo = dto.BundleNo ?? string.Empty;
            LotNo = dto.LotNo ?? string.Empty;
            MesProductCode = dto.MesProductCode;
            ProductCode = dto.ProductCode ?? string.Empty;
            ProductName = dto.ProductName ?? string.Empty;
            PartnerName = dto.PartnerName ?? string.Empty;
            Memo = dto.Memo ?? string.Empty;

            if (!InspectionDate.HasValue)
            {
                InspectionDate = DateTime.Today;
            }
        }

        public void Clear()
        {
            LotId = null;
            OutsourceWorkGroupId = null;
            OutsourceWorkGroupItemId = null;
            BundleNo = string.Empty;
            LotNo = string.Empty;
            ProductCode = string.Empty;
            MesProductCode = null;
            ProductName = string.Empty;
            PartnerName = string.Empty;
            InspectionDate = DateTime.Today;
            Memo = string.Empty;
        }
    }
}