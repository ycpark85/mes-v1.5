using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

namespace Mes.Wpf.Core.Controls
{
    public partial class PaginationBar : UserControl
    {
        public static readonly DependencyProperty PageTextProperty = DependencyProperty.Register(
            nameof(PageText),
            typeof(string),
            typeof(PaginationBar),
            new PropertyMetadata(string.Empty));

        public static readonly DependencyProperty PreviousCommandProperty = DependencyProperty.Register(
            nameof(PreviousCommand),
            typeof(ICommand),
            typeof(PaginationBar));

        public static readonly DependencyProperty NextCommandProperty = DependencyProperty.Register(
            nameof(NextCommand),
            typeof(ICommand),
            typeof(PaginationBar));

        public PaginationBar()
        {
            InitializeComponent();
        }

        public string PageText
        {
            get => (string)GetValue(PageTextProperty);
            set => SetValue(PageTextProperty, value);
        }

        public ICommand? PreviousCommand
        {
            get => (ICommand?)GetValue(PreviousCommandProperty);
            set => SetValue(PreviousCommandProperty, value);
        }

        public ICommand? NextCommand
        {
            get => (ICommand?)GetValue(NextCommandProperty);
            set => SetValue(NextCommandProperty, value);
        }
    }
}
