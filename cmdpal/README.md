# marcfinder for PowerToys Command Palette

A [Command Palette](https://learn.microsoft.com/windows/powertoys/command-palette/overview)
extension that looks up MARC 21 fields with the same queries as the `marc` CLI. It embeds
`marc_cli/data/*.json` at build time, so it doesn't need Python or marcfinder installed.

## Using it

Open Command Palette (Win+Alt+Space) and pick **MARC lookup**, then type:

| Query          | Shows                                              |
| -------------- | -------------------------------------------------- |
| `245`          | Field 245, its subfields and character positions   |
| `245a`         | One subfield (`245$a` also works)                  |
| `008/23`       | A character position, for every material type      |
| `ldr/06`       | Leader positions                                   |
| `5xx`, `6`     | Browse fields by pattern or prefix                 |
| `isbn`, `braille` | Keyword search, including definitions           |
| `h 852`        | Holdings format (prefix any query with `h`)        |

Each result shows the definition, indicators, codes and examples in the details pane.
**Enter** opens the Library of Congress page; the context menu (Ctrl+K) copies the tag.

Tags and positions also work straight from the main Command Palette search box: type
`245a` or `008/23` without opening MARC lookup first. Start with `marc` to get keywords
there too (`marc isbn`).

**Tip:** give MARC lookup the alias `marc` (Command Palette settings > Extensions >
marcfinder). Then typing `marc ` jumps straight into the lookup page with its details pane.

## Building

Needs the .NET 10 SDK and Windows Developer Mode (Settings > System > For developers).

```powershell
cd cmdpal
dotnet build MarcFinderExtension -c Debug -p:Platform=x64
Add-AppxPackage -Register MarcFinderExtension\bin\x64\Debug\net10.0-windows10.0.26100.0\win-x64\AppxManifest.xml
```

Then run **Reload** in Command Palette (or restart it). After code or data changes, build
again and re-run the `Add-AppxPackage` line.

To remove it: `Get-AppxPackage mikegsaunders.marcfinder | Remove-AppxPackage`.

Releasing (Store signing, WinGet and the Command Palette gallery) is covered in [RELEASING.md](RELEASING.md).
