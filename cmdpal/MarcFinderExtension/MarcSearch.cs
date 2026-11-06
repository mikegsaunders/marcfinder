using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace MarcFinderExtension;

internal enum HitKind
{
    Field,
    Subfield,
    Position,
}

/// <summary>
/// One search result. For positions, <see cref="Variants"/> lists the material types the
/// position was found in (null entry = the field's own positions), and <see cref="Value"/>
/// is the code that matched a keyword, if any.
/// </summary>
internal sealed record Hit(
    HitKind Kind,
    Field Field,
    Subfield? Subfield = null,
    Position? Position = null,
    IReadOnlyList<Variant?>? Variants = null,
    CodeValue? Value = null);

internal sealed record SearchResult(string Format, IReadOnlyList<Hit> Hits, string? Message = null);

/// <summary>Same query language as the marc CLI: 245, 245a, 008/23, 5xx, 6, keywords.</summary>
internal static partial class MarcSearch
{
    [GeneratedRegex(@"^(ldr|leader|\d{3})\s*/\s*(\d{1,2})(?:\s*-\s*(\d{1,2}))?$", RegexOptions.IgnoreCase)]
    private static partial Regex PositionRegex();

    [GeneratedRegex(@"^(ldr|leader|\d{3})\s*(?:[$‡|]?\s*([a-z0-9]))?$", RegexOptions.IgnoreCase)]
    private static partial Regex CodeRegex();

    [GeneratedRegex(@"^[\dx]{3}$", RegexOptions.IgnoreCase)]
    private static partial Regex PatternRegex();

    [GeneratedRegex(@"^\d{1,2}$")]
    private static partial Regex PrefixRegex();

    [GeneratedRegex(@"^(?:-h|h|holdings?)\s+", RegexOptions.IgnoreCase)]
    private static partial Regex HoldingsPrefixRegex();

    [GeneratedRegex("[a-z0-9]+")]
    private static partial Regex WordRegex();

    /// <summary>True for queries that name a field, subfield or position directly.</summary>
    public static bool IsCode(string query)
    {
        var q = StripFormat(query, out _);
        return PositionRegex().IsMatch(q) || CodeRegex().IsMatch(q);
    }

    public static SearchResult Run(string query)
    {
        var q = StripFormat(query, out var format);
        if (q.Length == 0)
        {
            return new(format, MarcData.Fields(format).Values.Select(f => new Hit(HitKind.Field, f)).ToList());
        }

        var m = PositionRegex().Match(q);
        if (m.Success)
        {
            var start = int.Parse(m.Groups[2].Value);
            var end = m.Groups[3].Success ? int.Parse(m.Groups[3].Value) : start;
            return Positions(NormTag(m.Groups[1].Value), start, end, format);
        }

        m = CodeRegex().Match(q);
        if (m.Success)
        {
            return Code(NormTag(m.Groups[1].Value), m.Groups[2].Success ? m.Groups[2].Value.ToLowerInvariant() : null, format);
        }

        if (PatternRegex().IsMatch(q) && q.Contains('x', StringComparison.OrdinalIgnoreCase))
        {
            var rx = new Regex("^" + q.ToLowerInvariant().Replace("x", @"\d") + "$");
            return FieldList(format, f => rx.IsMatch(f.Tag), $"No {MarcData.FormatName(format).ToLowerInvariant()} fields match {q.ToUpperInvariant()}.");
        }

        if (PrefixRegex().IsMatch(q))
        {
            return FieldList(format, f => f.Tag.StartsWith(q, StringComparison.Ordinal), $"No {MarcData.FormatName(format).ToLowerInvariant()} fields start with {q}.");
        }

        var hits = Keyword(q, format);
        return new(format, hits, hits.Count == 0 ? $"No {MarcData.FormatName(format).ToLowerInvariant()} fields match '{q}'." : null);
    }

    /// <summary>"h 852" or "-h 852" searches the Holdings format.</summary>
    private static string StripFormat(string query, out string format)
    {
        var q = query.Trim();
        var m = HoldingsPrefixRegex().Match(q);
        format = m.Success ? MarcData.Holdings : MarcData.Bibliographic;
        return m.Success ? q[m.Length..].Trim() : q;
    }

    private static string NormTag(string tag) =>
        tag.Equals("ldr", StringComparison.OrdinalIgnoreCase) || tag.Equals("leader", StringComparison.OrdinalIgnoreCase) ? "LDR" : tag;

    private static SearchResult FieldList(string format, Func<Field, bool> match, string empty)
    {
        var hits = MarcData.Fields(format).Values.Where(match).Select(f => new Hit(HitKind.Field, f)).ToList();
        return new(format, hits, hits.Count == 0 ? empty : null);
    }

    private static SearchResult Code(string tag, string? sub, string format)
    {
        var f = MarcData.Find(tag, format);
        if (f is null)
        {
            return new(format, [], $"No {MarcData.FormatName(format).ToLowerInvariant()} field {tag}.");
        }

        if (sub is not null)
        {
            var sf = f.Subfields.FirstOrDefault(s => s.Code == sub);
            return sf is null
                ? new(format, [new Hit(HitKind.Field, f)], $"Field {tag} has no subfield ${sub}.")
                : new(format, [new Hit(HitKind.Subfield, f, sf), new Hit(HitKind.Field, f)]);
        }

        // The field, then its subfields and character positions
        var hits = new List<Hit> { new(HitKind.Field, f) };
        hits.AddRange(f.SortedSubfields.Select(s => new Hit(HitKind.Subfield, f, s)));
        hits.AddRange(f.AllPositions.Select(p => new Hit(HitKind.Position, f, Position: p.Position, Variants: [p.Variant])));
        return new(format, hits);
    }

    private static SearchResult Positions(string tag, int start, int end, string format)
    {
        var f = MarcData.Find(tag, format);
        if (f is null)
        {
            return new(format, [], $"No {MarcData.FormatName(format).ToLowerInvariant()} field {tag}.");
        }

        var hits = f.AllPositions
            .Where(p => p.Position.Range is { } r && r.Start <= end && start <= r.End)
            .Select(p => new Hit(HitKind.Position, f, Position: p.Position, Variants: [p.Variant]))
            .ToList();
        var range = end != start ? $"{start:00}-{end:00}" : $"{start:00}";
        return new(format, hits, hits.Count == 0 ? $"No character position {range} defined for {tag}." : null);
    }

    private static HashSet<string> Words(string text) =>
        WordRegex().Matches(text.ToLowerInvariant()).Select(m => m.Value).ToHashSet();

    /// <summary>Port of the CLI's keyword search; definitions are always searched but rank last.</summary>
    private static List<Hit> Keyword(string query, string format)
    {
        var q = query.ToLowerInvariant().Trim();
        var qwords = Words(q);
        bool Whole(string text) => qwords.Count > 0 && qwords.IsSubsetOf(Words(text));
        bool Has(string text) => text.Contains(q, StringComparison.OrdinalIgnoreCase);

        var scored = new List<(double Score, Hit Hit)>();
        foreach (var f in MarcData.Fields(format).Values)
        {
            double? score =
                f.Aliases.Any(a => a.Equals(q, StringComparison.OrdinalIgnoreCase)) ? 0 :
                Whole(f.Name) ? 1 :
                Has(f.Name) ? 2 :
                Has(f.Definition) ? 6 : null;
            if (score is { } s)
            {
                scored.Add((s, new Hit(HitKind.Field, f)));
            }

            foreach (var sf in f.Subfields)
            {
                score = Whole(sf.Name) ? 3 : Has(sf.Name) ? 4 : Has(sf.Description) ? 7 : null;
                if (score is { } ss)
                {
                    // Generic control subfields ($6 Linkage, $8 ...) appear everywhere; rank them lower
                    var digit = sf.Code.Length > 0 && char.IsDigit(sf.Code[0]);
                    scored.Add((ss + (digit ? 0.5 : 0), new Hit(HitKind.Subfield, f, sf)));
                }
            }

            // The same position often recurs per material type, so group those into one hit
            var groups = new Dictionary<(double, string, string, string), (Position Position, CodeValue? Value, List<Variant?> Variants)>();
            foreach (var (variant, p) in f.AllPositions)
            {
                var value = p.Values.FirstOrDefault(v => Whole(v.Label));
                double? ps = Whole(p.Name) ? 3 : Has(p.Name) ? 4 : value is not null ? 5 : null;
                if (ps is not { } pscore)
                {
                    continue;
                }

                if (pscore < 5)
                {
                    value = null;
                }

                var key = (pscore, p.Pos, p.Name, value?.Code ?? string.Empty);
                if (!groups.TryGetValue(key, out var g))
                {
                    g = (p, value, []);
                    groups[key] = g;
                }

                g.Variants.Add(variant);
            }

            foreach (var (key, g) in groups)
            {
                scored.Add((key.Item1, new Hit(HitKind.Position, f, Position: g.Position, Variants: g.Variants, Value: g.Value)));
            }
        }

        return scored.OrderBy(h => h.Score).ThenBy(h => h.Hit.Field.Tag, StringComparer.Ordinal).Select(h => h.Hit).ToList();
    }
}
