using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;

namespace MarcFinderExtension;

internal sealed record CodeValue(string Code, string Label, string Description);

internal sealed record Indicator(string Position, string Name, string Description, CodeValue[] Values);

internal sealed record Subfield(string Code, string Name, bool? Repeatable, string Description);

internal sealed record Position(string Pos, string Name, string Description, CodeValue[] Values)
{
    /// <summary>"07-10" -> (7, 10); null for anything that isn't a plain number or range.</summary>
    public (int Start, int End)? Range
    {
        get
        {
            var parts = Pos.Split('-');
            if (parts.Length is < 1 or > 2 || !int.TryParse(parts[0], out var start))
            {
                return null;
            }

            var end = start;
            if (parts.Length == 2 && !int.TryParse(parts[1], out end))
            {
                return null;
            }

            return (start, end);
        }
    }
}

/// <summary>Material-type specific positions, e.g. 008 for Books vs Maps.</summary>
internal sealed record Variant(string Name, string Url, Position[] Positions);

internal sealed record Field(
    string Tag,
    string Name,
    bool? Repeatable,
    string Definition,
    Indicator[] Indicators,
    Subfield[] Subfields,
    Position[] Positions,
    Variant[] Variants,
    string[] Examples,
    string[] Aliases,
    string Url,
    string Format)
{
    /// <summary>Subfields with letters before digits, as LOC lists them.</summary>
    public IEnumerable<Subfield> SortedSubfields =>
        Subfields.OrderBy(s => s.Code.Length > 0 && char.IsDigit(s.Code[0])).ThenBy(s => s.Code, StringComparer.Ordinal);

    /// <summary>The field's own positions, then each variant's, with the variant's name and URL.</summary>
    public IEnumerable<(Variant? Variant, Position Position)> AllPositions =>
        Positions.Select(p => ((Variant?)null, p))
            .Concat(Variants.SelectMany(v => v.Positions.Select(p => ((Variant?)v, p))));
}

internal static class MarcData
{
    public const string Bibliographic = "bibliographic";
    public const string Holdings = "holdings";

    private static readonly Lazy<Dictionary<string, Field>> _bib = new(() => Load(Bibliographic));
    private static readonly Lazy<Dictionary<string, Field>> _holdings = new(() => Load(Holdings));

    public static Dictionary<string, Field> Fields(string format) =>
        format == Holdings ? _holdings.Value : _bib.Value;

    public static string FormatName(string format) => format == Holdings ? "Holdings" : "Bibliographic";

    /// <summary>Bibliographic lookups fall back to holdings (841-878 etc.), as the CLI does.</summary>
    public static Field? Find(string tag, string format)
    {
        if (Fields(format).TryGetValue(tag, out var f))
        {
            return f;
        }

        return format == Bibliographic && _holdings.Value.TryGetValue(tag, out var h) ? h : null;
    }

    private static Dictionary<string, Field> Load(string format)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream($"{format}.json")
            ?? throw new FileNotFoundException($"Embedded {format}.json not found");
        using var doc = JsonDocument.Parse(stream);

        // Keep the file's order, which is tag order
        var fields = new Dictionary<string, Field>();
        foreach (var prop in doc.RootElement.GetProperty("fields").EnumerateObject())
        {
            var f = prop.Value;
            fields[prop.Name] = new Field(
                Str(f, "tag"),
                Str(f, "name"),
                Bool(f, "repeatable"),
                Str(f, "definition"),
                Arr(f, "indicators", i => new Indicator(Str(i, "position"), Str(i, "name"), Str(i, "description"), Values(i))),
                Arr(f, "subfields", s => new Subfield(Str(s, "code"), Str(s, "name"), Bool(s, "repeatable"), Str(s, "description"))),
                Positions(f),
                Arr(f, "variants", v => new Variant(Str(v, "name"), Str(v, "url"), Positions(v))),
                Arr(f, "examples", e => e.GetString() ?? string.Empty),
                Arr(f, "aliases", a => a.GetString() ?? string.Empty),
                Str(f, "url"),
                format);
        }

        return fields;
    }

    private static Position[] Positions(JsonElement e) =>
        Arr(e, "positions", p => new Position(Str(p, "position"), Str(p, "name"), Str(p, "description"), Values(p)));

    private static CodeValue[] Values(JsonElement e) =>
        Arr(e, "values", v => new CodeValue(Str(v, "code"), Str(v, "label"), Str(v, "description")));

    private static string Str(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? string.Empty : string.Empty;

    private static bool? Bool(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False ? v.GetBoolean() : null;

    private static T[] Arr<T>(JsonElement e, string name, Func<JsonElement, T> map) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Array ? v.EnumerateArray().Select(map).ToArray() : [];
}
