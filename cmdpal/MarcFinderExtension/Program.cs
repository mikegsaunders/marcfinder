using System;
using System.Threading;
using Microsoft.CommandPalette.Extensions;
using Shmuelie.WinRTServer.CsWinRT;

namespace MarcFinderExtension;

public static class Program
{
    [MTAThread]
    public static void Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "-RegisterProcessAsComServer")
        {
            global::Shmuelie.WinRTServer.ComServer server = new();
            ManualResetEvent extensionDisposedEvent = new(false);

            // One extension instance, handed back every time Command Palette asks for it.
            // The process exits once Command Palette disposes it.
            MarcFinderExtension extensionInstance = new(extensionDisposedEvent);
            server.RegisterClass<MarcFinderExtension, IExtension>(() => extensionInstance);
            server.Start();
            extensionDisposedEvent.WaitOne();
            server.Stop();
            server.UnsafeDispose();
        }
        else
        {
            Console.WriteLine("This is a PowerToys Command Palette extension; it isn't run directly.");
        }
    }
}
