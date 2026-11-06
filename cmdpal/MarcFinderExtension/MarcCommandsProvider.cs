using Microsoft.CommandPalette.Extensions;
using Microsoft.CommandPalette.Extensions.Toolkit;

namespace MarcFinderExtension;

public sealed partial class MarcCommandsProvider : CommandProvider
{
    private readonly ICommandItem[] _commands;
    private readonly IFallbackCommandItem[] _fallbacks = [new MarcFallbackItem()];

    public MarcCommandsProvider()
    {
        Id = "MarcFinder";
        DisplayName = "marcfinder";
        Icon = IconHelpers.FromRelativePath("Assets\\Icon.png");
        _commands =
        [
            new CommandItem(new MarcSearchPage())
            {
                Title = "MARC lookup",
                Subtitle = "Look up MARC 21 fields, subfields and character positions",
            },
        ];
    }

    public override ICommandItem[] TopLevelCommands() => _commands;

    public override IFallbackCommandItem[] FallbackCommands() => _fallbacks;
}
