using System.Linq;
using Microsoft.CommandPalette.Extensions;
using Microsoft.CommandPalette.Extensions.Toolkit;

namespace MarcFinderExtension;

internal sealed partial class MarcSearchPage : DynamicListPage
{
    // A keyword like "note" matches hundreds of things; the best ones come first
    private const int MaxItems = 100;

    private IListItem[] _items = [];

    public MarcSearchPage()
    {
        Icon = IconHelpers.FromRelativePath("Assets\\Icon.png");
        Title = "MARC lookup";
        Name = "Search";
        PlaceholderText = "245, 245a, 008/23, 5xx, isbn  ·  prefix with h for Holdings (h 852)";
        ShowDetails = true;
        Update(string.Empty);
    }

    public override void UpdateSearchText(string oldSearch, string newSearch)
    {
        Update(newSearch);
        RaiseItemsChanged(_items.Length);
    }

    public override IListItem[] GetItems() => _items;

    private void Update(string query)
    {
        var result = MarcSearch.Run(query);
        _items = [.. result.Hits.Take(MaxItems).Select(h => MarcItems.ToListItem(h, result.Format))];

        // A message alongside results (e.g. "245 has no subfield $x") goes first as a plain row
        if (result.Message is { } msg && _items.Length > 0)
        {
            _items = [new ListItem(new NoOpCommand()) { Title = msg }, .. _items];
        }

        EmptyContent = new CommandItem(new NoOpCommand())
        {
            Title = result.Message ?? "No matches",
            Subtitle = "Try a tag (245), subfield (245a), position (008/23), pattern (5xx) or keyword",
        };
    }
}
