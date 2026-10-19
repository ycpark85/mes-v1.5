using Mes.Wpf.Core.Common;

namespace Mes.Wpf.Modules.BohyunOutsourceManagement.Dtos
{
    public class BohyunOutsourceWorkDoneEditModel : ViewModelBase
    {
        private long? _outsourceWorkGroupId;
        private string _partnerName = string.Empty;
        private string _workTypeName = string.Empty;
        private string _lotNosText = string.Empty;
        private string _productNamesText = string.Empty;
        private string _productCodesText = string.Empty;
        private string _mesProductCodesText = string.Empty;

        public string ProductCodesText { get => _productCodesText; set => SetProperty(ref _productCodesText, value); }
        public string MesProductCodesText { get => _mesProductCodesText; set => SetProperty(ref _mesProductCodesText, value); }
        private int? _sheetQty;
        private int? _workDoneSheetQty;
        private decimal? _outsourceProcessingFee;
        private string _remark = string.Empty;

        public long? OutsourceWorkGroupId
        {
            get => _outsourceWorkGroupId;
            set => SetProperty(ref _outsourceWorkGroupId, value);
        }

        public string PartnerName
        {
            get => _partnerName;
            set => SetProperty(ref _partnerName, value);
        }

        public string WorkTypeName
        {
            get => _workTypeName;
            set => SetProperty(ref _workTypeName, value);
        }

        public string LotNosText
        {
            get => _lotNosText;
            set => SetProperty(ref _lotNosText, value);
        }

        public string ProductNamesText
        {
            get => _productNamesText;
            set => SetProperty(ref _productNamesText, value);
        }

        public int? SheetQty
        {
            get => _sheetQty;
            set => SetProperty(ref _sheetQty, value);
        }

        public int? WorkDoneSheetQty
        {
            get => _workDoneSheetQty;
            set => SetProperty(ref _workDoneSheetQty, value);
        }

        public decimal? OutsourceProcessingFee
        {
            get => _outsourceProcessingFee;
            set => SetProperty(ref _outsourceProcessingFee, value);
        }

        public string Remark
        {
            get => _remark;
            set => SetProperty(ref _remark, value);
        }

        public void LoadFromDto(BohyunOutsourceRowModel row)
        {
            OutsourceWorkGroupId = row.OutsourceWorkGroupId;
            PartnerName = row.PartnerName;
            WorkTypeName = row.WorkTypeName;
            LotNosText = row.LotNosText;
            ProductNamesText = row.ProductNamesText;
            ProductCodesText = row.ProductCodesText;
            MesProductCodesText = row.MesProductCodesText;
            SheetQty = row.SheetQty;
            WorkDoneSheetQty = row.WorkDoneSheetQty ?? row.SheetQty;
            OutsourceProcessingFee = row.OutsourceProcessingFee;
            Remark = row.WorkDoneRemark;
        }

        public void Clear()
        {
            OutsourceWorkGroupId = null;
            PartnerName = string.Empty;
            WorkTypeName = string.Empty;
            LotNosText = string.Empty;
            ProductNamesText = string.Empty;
            ProductCodesText = string.Empty;
            MesProductCodesText = string.Empty;
            SheetQty = null;
            WorkDoneSheetQty = null;
            OutsourceProcessingFee = null;
            Remark = string.Empty;
        }
    }
}
