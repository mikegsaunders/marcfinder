using System;
using System.Linq;
using Microsoft.CommandPalette.Extensions.Toolkit;

namespace MarcFinderExtension;

/// <summary>
/// Shows a MARC result straight from the main Command Palette search box when the query is a
/// tag, subfield or position (245, 245a, 008/23). Keywords are left to the MARC lookup page,
/// so ordinary searches like "settings" don't get a MARC row.
/// </summary>
internal sealed partial class MarcFallbackItem : FallbackCommandItem
{
    private readonly NoOpCommand _empty = new();

    public MarcFallbackItem()
        : base(new NoOpCommand(), "MARC field lookup", "MarcFinder.Fallback")
    {
        Title = string.Empty;
        Subtitle = string.Empty;
        Icon = IconHelpers.FromRelativePath("Assets\\Icon.png");
    }

    public override void UpdateQuery(string query)
    {
        // "marc isbn" opts in to any query; without the prefix only codes like 245a show up
        var q = query.TrimStart();
        var prefixed = q.StartsWith("marc ", StringComparison.OrdinalIgnoreCase);
        if (prefixed)
        {
            q = q[5..];
        }

        var result = prefixed && q.Trim().Length > 0 || MarcSearch.IsCode(q) ? MarcSearch.Run(q) : null;
        var hit = result?.Hits.FirstOrDefault();
        if (result is null || hit is null)
        {
            // An empty title hides the fallback row
            Command = _empty;
            Title = string.Empty;
            Subtitle = string.Empty;
            return;
        }

        var item = MarcItems.ToListItem(hit, result.Format);
        Command = item.Command;
        Title = item.Title;
        Subtitle = $"MARC · {item.Subtitle}";
        MoreCommands = item.MoreCommands;
    }
}
