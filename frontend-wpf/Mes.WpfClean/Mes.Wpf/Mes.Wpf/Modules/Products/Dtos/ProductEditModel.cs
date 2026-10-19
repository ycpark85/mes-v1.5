using Mes.Wpf.Core.Common;
using System;

namespace Mes.Wpf.Modules.Products.Dtos
{
    public class ProductEditModel : ViewModelBase
    {
        private bool _isUnprintedManaged;
        public bool IsUnprintedManaged
        {
            get => _isUnprintedManaged;
            set => SetProperty(ref _isUnprintedManaged, value);
        }

        private string _productCode = string.Empty;
        private string _productName = string.Empty;
        private string _uom = string.Empty;
        private long? _drawingId;
        private long? _routingTemplateId;
        private int? _panelWidthMm;
        private int? _panelLengthMm;
        private string? _productSpec;
        private int? _cutQtyPerPanel;
        private string _useYn = "사용";
        private string? _memo;

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

        public string Uom
        {
            get => _uom;
            set => SetProperty(ref _uom, value);
        }

        public long? DrawingId
        {
            get => _drawingId;
            set => SetProperty(ref _drawingId, value);
        }

        public long? RoutingTemplateId
        {
            get => _routingTemplateId;
            set => SetProperty(ref _routingTemplateId, value);
        }

        public int? PanelWidthMm
        {
            get => _panelWidthMm;
            set => SetProperty(ref _panelWidthMm, value);
        }

        public int? PanelLengthMm
        {
            get => _panelLengthMm;
            set => SetProperty(ref _panelLengthMm, value);
        }

        public string? ProductSpec
        {
            get => _productSpec;
            set => SetProperty(ref _productSpec, value);
        }

        public int? CutQtyPerPanel
        {
            get => _cutQtyPerPanel;
            set => SetProperty(ref _cutQtyPerPanel, value);
        }

        public string UseYn
        {
            get => _useYn;
            set => SetProperty(ref _useYn, value);
        }

        public string? Memo
        {
            get => _memo;
            set => SetProperty(ref _memo, value);
        }

        public void LoadFromDto(ProductDto dto)
        {
            IsUnprintedManaged = dto.IsUnprintedManaged;
            ProductCode = dto.ProductCode ?? string.Empty;
            ProductName = dto.ProductName ?? string.Empty;
            Uom = dto.Uom ?? string.Empty;
            DrawingId = dto.DrawingId;
            RoutingTemplateId = dto.RoutingTemplateId;
            PanelWidthMm = dto.PanelWidthMm;
            PanelLengthMm = dto.PanelLengthMm;
            ProductSpec = dto.ProductSpec;
            CutQtyPerPanel = dto.CutQtyPerPanel;
            UseYn = dto.IsActive ? "사용" : "미사용";
            Memo = dto.Memo;
        }

        public void Clear()
        {
            IsUnprintedManaged = false;
            ProductCode = string.Empty;
            ProductName = string.Empty;
            Uom = string.Empty;
            DrawingId = null;
            RoutingTemplateId = null;
            PanelWidthMm = null;
            PanelLengthMm = null;
            ProductSpec = null;
            CutQtyPerPanel = null;
            UseYn = "사용";
            Memo = null;
        }
    }
}