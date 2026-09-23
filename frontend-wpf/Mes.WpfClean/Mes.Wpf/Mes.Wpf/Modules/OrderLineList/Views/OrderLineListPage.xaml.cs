using System.Windows.Controls;

using Mes.Wpf.Modules.OrderLineList.ViewModels;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;

namespace Mes.Wpf.Modules.OrderLineList.Views
{
    public partial class OrderLineListPage : UserControl
    {
        private OrderLineListPageViewModel? _subscribed;
        private double _pageOffset;
        private double _gridOffset;
        private double _horizontalOffset;

        public OrderLineListPage()
        {
            InitializeComponent();
            Loaded += (_, _) => Subscribe(DataContext as OrderLineListPageViewModel);
            Unloaded += (_, _) => Subscribe(null);
            DataContextChanged += (_, _) => Subscribe(DataContext as OrderLineListPageViewModel);
        }

        private void Subscribe(OrderLineListPageViewModel? vm)
        {
            if (_subscribed != null)
            {
                _subscribed.ItemsRefreshing -= CaptureScroll;
                _subscribed.ItemsRefreshed -= RestoreScroll;
            }
            _subscribed = vm;
            if (vm != null)
            {
                vm.ItemsRefreshing += CaptureScroll;
                vm.ItemsRefreshed += RestoreScroll;
            }
        }

        private void CaptureScroll()
        {
            _pageOffset = PageScroll.VerticalOffset;
            var scroll = FindScroll(OrdersGrid);
            _gridOffset = scroll?.VerticalOffset ?? 0;
            _horizontalOffset = scroll?.HorizontalOffset ?? 0;
        }

        private void RestoreScroll() => Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new System.Action(() =>
        {
            PageScroll.ScrollToVerticalOffset(_pageOffset);
            var scroll = FindScroll(OrdersGrid);
            scroll?.ScrollToVerticalOffset(_gridOffset);
            scroll?.ScrollToHorizontalOffset(_horizontalOffset);
        }));

        private static ScrollViewer? FindScroll(DependencyObject root)
        {
            if (root is ScrollViewer scroll) return scroll;
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
            {
                var found = FindScroll(VisualTreeHelper.GetChild(root, i));
                if (found != null) return found;
            }
            return null;
        }
    }
}
