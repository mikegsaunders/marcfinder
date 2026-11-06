using System.Collections.Generic;
using System.Linq;
using System.Text;
using Microsoft.CommandPalette.Extensions;
using Microsoft.CommandPalette.Extensions.Toolkit;

namespace MarcFinderExtension;

/// <summary>Turns search hits into Command Palette list items with a details pane.</summary>
internal static class MarcItems
{
    private static readonly Tag RepeatableTag = new("R") { ToolTip = "Repeatable" };
    private static readonly Tag NonRepeatableTag = new("NR") { ToolTip = "Not repeatable" };
    private static readonly Tag HoldingsTag = new("Holdings") { ToolTip = "MARC 21 Holdings format" };

    public static ListItem ToListItem(Hit hit, string askedFormat)
    {
        var (title, copy, url) = hit.Kind switch
        {
            HitKind.Subfield => ($"{hit.Field.Tag} ${hit.Subfield!.Code}  {hit.Subfield.Name}", $"{hit.Field.Tag}${hit.Subfield.Code}", hit.Field.Url),
            HitKind.Position => ($"{hit.Field.Tag}/{hit.Position!.Pos}  {hit.Position.Name}", $"{hit.Field.Tag}/{hit.Position.Pos}", hit.Variants?.FirstOrDefault()?.Url is { Length: > 0 } u ? u : hit.Field.Url),
            _ => ($"{hit.Field.Tag}  {hit.Field.Name}", hit.Field.Tag, hit.Field.Url),
        };

        var tags = new List<ITag>();
        var repeatable = hit.Kind switch
        {
            HitKind.Field => hit.Field.Repeatable,
            HitKind.Subfield => hit.Subfield!.Repeatable,
            _ => null,
        };
        if (repeatable is { } r)
        {
            tags.Add(r ? RepeatableTag : NonRepeatableTag);
        }

        if (hit.Field.Format != askedFormat || askedFormat == MarcData.Holdings)
        {
            tags.Add(HoldingsTag);
        }

        return new ListItem(new OpenUrlCommand(url) { Name = "Open LOC documentation" })
        {
            Title = title,
            Subtitle = Subtitle(hit),
            Tags = [.. tags],
            Details = new Details { Title = title, Body = Markdown(hit) },
            MoreCommands =
            [
                new CommandContextItem(new CopyTextCommand(copy) { Name = $"Copy {copy}" }),
                new CommandContextItem(new CopyTextCommand(title) { Name = "Copy title" }),
            ],
        };
    }

    private static string Subtitle(Hit hit)
    {
        switch (hit.Kind)
        {
            case HitKind.Field:
                return hit.Field.Subfields.Length > 0 ? $"{hit.Field.Subfields.Length} subfields" :
                       hit.Field.Positions.Length > 0 ? "Character positions" : string.Empty;
            case HitKind.Subfield:
                return hit.Field.Name;
            default:
                var parts = new List<string>();
                if (hit.Value is { } v)
                {
                    parts.Add($"{v.Code} - {v.Label}");
                }

                var groups = hit.Variants?.Where(g => g is not null).Select(g => g!.Name).ToList() ?? [];
                parts.Add(groups.Count > 0 ? string.Join(", ", groups) : hit.Field.Name);
                return string.Join(" · ", parts);
        }
    }

    private static string Markdown(Hit hit)
    {
        var sb = new StringBuilder();
        switch (hit.Kind)
        {
            case HitKind.Subfield:
                FieldHeader(sb, hit.Field);
                sb.AppendLine($"## ${hit.Subfield!.Code} - {Esc(hit.Subfield.Name)} {Rep(hit.Subfield.Repeatable)}").AppendLine();
                Para(sb, hit.Subfield.Description);
                break;

            case HitKind.Position:
                FieldHeader(sb, hit.Field);
                var groups = hit.Variants?.Where(g => g is not null).Select(g => g!.Name).ToList() ?? [];
                if (groups.Count > 0)
                {
                    sb.AppendLine($"*{Esc(string.Join(", ", groups))}*").AppendLine();
                }

                Position(sb, hit.Field.Tag, hit.Position!, "##");
                break;

            default:
                FieldBody(sb, hit.Field);
                break;
        }

        var url = hit.Kind == HitKind.Position && hit.Variants?.FirstOrDefault()?.Url is { Length: > 0 } u ? u : hit.Field.Url;
        if (url.Length > 0)
        {
            sb.AppendLine().AppendLine($"[Library of Congress documentation]({url})");
        }

        return sb.ToString();
    }

    private static void FieldHeader(StringBuilder sb, Field f) =>
        sb.AppendLine($"**{f.Tag} - {Esc(f.Name)}** {Rep(f.Repeatable)}").AppendLine();

    private static void FieldBody(StringBuilder sb, Field f)
    {
        sb.AppendLine($"# {f.Tag} - {Esc(f.Name)} {Rep(f.Repeatable)}").AppendLine();
        if (f.Format == MarcData.Holdings)
        {
            sb.AppendLine("*Holdings format*").AppendLine();
        }

        Para(sb, f.Definition);

        if (f.Indicators.Length > 0)
        {
            sb.AppendLine("## Indicators").AppendLine();
            foreach (var ind in f.Indicators)
            {
                sb.AppendLine($"**{Esc(ind.Position)} - {Esc(ind.Name)}**").AppendLine();
                Values(sb, ind.Values);
            }
        }

        if (f.Subfields.Length > 0)
        {
            sb.AppendLine("## Subfields").AppendLine();
            foreach (var sf in f.SortedSubfields)
            {
                sb.AppendLine($"- **${sf.Code}** - {Esc(sf.Name)} {Rep(sf.Repeatable)}");
            }

            sb.AppendLine();
        }

        if (f.Positions.Length > 0)
        {
            sb.AppendLine("## Character positions").AppendLine();
            PositionList(sb, f.Tag, f.Positions);
        }

        foreach (var v in f.Variants)
        {
            sb.AppendLine($"## {Esc(v.Name)}").AppendLine();
            PositionList(sb, f.Tag, v.Positions);
        }

        if (f.Examples.Length > 0)
        {
            sb.AppendLine("## Examples").AppendLine();
            foreach (var ex in f.Examples.Take(6))
            {
                sb.AppendLine($"- `{ex.Replace("`", "'")}`");
            }

            sb.AppendLine();
        }
    }

    private static void PositionList(StringBuilder sb, string tag, IEnumerable<Position> positions)
    {
        foreach (var p in positions)
        {
            sb.AppendLine($"- **{tag}/{p.Pos}** - {Esc(p.Name)}");
        }

        sb.AppendLine();
    }

    private static void Position(StringBuilder sb, string tag, Position p, string level)
    {
        sb.AppendLine($"{level} {tag}/{p.Pos} - {Esc(p.Name)}").AppendLine();
        Para(sb, p.Description);
        Values(sb, p.Values);
    }

    private static void Values(StringBuilder sb, CodeValue[] values)
    {
        if (values.Length == 0)
        {
            return;
        }

        foreach (var v in values)
        {
            var code = string.IsNullOrWhiteSpace(v.Code) ? "(blank)" : v.Code.Replace("`", "'");
            sb.AppendLine($"- `{code}` - {Esc(v.Label)}");
        }

        sb.AppendLine();
    }

    private static void Para(StringBuilder sb, string text)
    {
        if (!string.IsNullOrWhiteSpace(text))
        {
            sb.AppendLine(Esc(text)).AppendLine();
        }
    }

    private static string Rep(bool? repeatable) => repeatable switch
    {
        true => "(R)",
        false => "(NR)",
        null => string.Empty,
    };

    /// <summary>Escape characters that would otherwise turn LOC prose into markdown formatting.</summary>
    private static string Esc(string text)
    {
        var sb = new StringBuilder(text.Length);
        foreach (var c in text)
        {
            if (c is '\\' or '*' or '_' or '`' or '[' or ']' or '<' or '>' or '#')
            {
                sb.Append('\\');
            }

            sb.Append(c);
        }

        return sb.ToString();
    }
}
