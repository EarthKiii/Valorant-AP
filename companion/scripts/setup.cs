// VALORANT Companion setup: the self-extracting installer `npm run sfx` builds around the packed companion.
//
// Installs to %LOCALAPPDATA%\Programs\VALORANT Companion (no admin rights needed), replaces the previous version's
// files but keeps your settings and credentials (app\.env), and creates Desktop and Start Menu shortcuts.
//
// Options: /dir=<folder> installs somewhere else; /quiet skips every dialog, shortcut and launch (for testing).
// Written for the C# 5 compiler that ships with Windows (.NET Framework 4).

using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("VALORANT Companion Setup")]
[assembly: AssemblyProduct("VALORANT Archipelago Companion")]

static class Setup
{
    const string Title = "VALORANT Companion Setup";
    const string AppName = "VALORANT Companion";
    const string Launcher = "Start VALORANT Companion.cmd";
    const string SettingsFile = @"app\.env";

    static bool quiet;

    [STAThread]
    static int Main(string[] args)
    {
        quiet = args.Any(arg => arg.Equals("/quiet", StringComparison.OrdinalIgnoreCase));
        string dirArg = args.FirstOrDefault(arg => arg.StartsWith("/dir=", StringComparison.OrdinalIgnoreCase));
        string defaultDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", AppName);
        string target = Path.GetFullPath(dirArg != null ? dirArg.Substring(5).Trim('"') : defaultDir);
        string settings = Path.Combine(target, SettingsFile);
        bool update = File.Exists(Path.Combine(target, Launcher));

        string question = update
            ? "Update the VALORANT Companion in:\n" + target + "\n\nYour settings and credentials (app\\.env) are kept."
            : "Install the VALORANT Companion to:\n" + target;
        if (!quiet && MessageBox.Show(question, Title, MessageBoxButtons.OKCancel, MessageBoxIcon.Information)
                != DialogResult.OK)
            return 1;

        while (IsRunning(target))
        {
            if (quiet || MessageBox.Show("The VALORANT Companion is running. Close it, then click Retry.", Title,
                    MessageBoxButtons.RetryCancel, MessageBoxIcon.Warning) != DialogResult.Retry)
                return 1;
        }

        try
        {
            byte[] keptSettings = File.Exists(settings) ? File.ReadAllBytes(settings) : null;
            // Replace the previous version's files instead of mixing old and new ones.
            foreach (string folder in new[] { "app", "runtime" })
            {
                string path = Path.Combine(target, folder);
                if (Directory.Exists(path))
                    Directory.Delete(path, true);
            }
            Extract(target);
            if (keptSettings != null)
                File.WriteAllBytes(settings, keptSettings);
        }
        catch (Exception error)
        {
            Show("Couldn't " + (update ? "update" : "install") + " the VALORANT Companion:\n\n" + error.Message,
                MessageBoxIcon.Error);
            return 2;
        }

        if (quiet)
            return 0;

        string launcher = Path.Combine(target, Launcher);
        string icon = Path.Combine(target, @"runtime\electron.exe");
        try
        {
            CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                AppName + ".lnk"), launcher, target, icon);
            CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                AppName + ".lnk"), launcher, target, icon);
        }
        catch (Exception error)
        {
            Show("Installed, but the shortcuts couldn't be created:\n\n" + error.Message + "\n\nStart it with \""
                + Launcher + "\" in " + target + ".", MessageBoxIcon.Warning);
        }

        if (!HasCredentials(settings))
        {
            Show("Add your Overwolf developer credentials (OW_CLI_EMAIL and OW_CLI_API_KEY) to the settings file "
                + "that opens next, then save and close it.\n\nWithout them the companion still starts, but live "
                + "game events and the in-game overlay stay off.", MessageBoxIcon.Information);
            using (Process notepad = Process.Start("notepad.exe", "\"" + settings + "\""))
                notepad.WaitForExit();
        }

        string done = (update ? "Updated." : "Installed, with shortcuts on your Desktop and in the Start Menu.")
            + "\n\nStart the VALORANT Companion now?";
        if (MessageBox.Show(done, Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
        {
            Process.Start(new ProcessStartInfo(launcher)
            {
                WorkingDirectory = target,
                WindowStyle = ProcessWindowStyle.Minimized,
                UseShellExecute = true,
            });
        }
        return 0;
    }

    static void Extract(string target)
    {
        string root = Path.GetFullPath(target).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
        using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
        {
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string name = entry.FullName.Replace('\\', '/');
                string path = Path.GetFullPath(Path.Combine(root, name));
                if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    continue; // never write outside the install folder
                if (name.EndsWith("/"))
                {
                    Directory.CreateDirectory(path);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                entry.ExtractToFile(path, true);
            }
        }
    }

    static bool IsRunning(string target)
    {
        string runtime = Path.Combine(Path.GetFullPath(target), "runtime") + Path.DirectorySeparatorChar;
        foreach (Process process in Process.GetProcessesByName("electron"))
        {
            try
            {
                if (process.MainModule.FileName.StartsWith(runtime, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            catch (Exception)
            {
                // Another user's or a protected process: not ours.
            }
            finally
            {
                process.Dispose();
            }
        }
        return false;
    }

    static bool HasCredentials(string path)
    {
        if (!File.Exists(path))
            return false;
        string email = null, apiKey = null, devKey = null;
        foreach (string raw in File.ReadAllLines(path))
        {
            string line = raw.Trim();
            int equals = line.IndexOf('=');
            if (line.StartsWith("#") || equals < 0)
                continue;
            string name = line.Substring(0, equals).Trim();
            string value = line.Substring(equals + 1).Trim();
            if (value.Length == 0)
                continue;
            if (name == "OW_CLI_EMAIL") email = value;
            else if (name == "OW_CLI_API_KEY") apiKey = value;
            else if (name == "OW_DEV_KEY") devKey = value;
        }
        return devKey != null || (email != null && apiKey != null);
    }

    static void CreateShortcut(string shortcutPath, string target, string workingDirectory, string icon)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell,
            new object[] { shortcutPath });
        Type type = shortcut.GetType();
        type.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
        type.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut,
            new object[] { workingDirectory });
        type.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { icon + ",0" });
        type.InvokeMember("WindowStyle", BindingFlags.SetProperty, null, shortcut, new object[] { 7 }); // minimized
        type.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut,
            new object[] { "VALORANT companion app for Archipelago" });
        type.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
    }

    static void Show(string message, MessageBoxIcon icon)
    {
        if (!quiet)
            MessageBox.Show(message, Title, MessageBoxButtons.OK, icon);
    }
}
