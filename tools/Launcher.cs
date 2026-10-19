// Original OpenCal Windows launcher. Copyright (c) 2026 OpenCal contributors.
// SPDX-License-Identifier: GPL-3.0-only
using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using Microsoft.Win32;

class OpenCalLauncher {
    [STAThread]
    static void Main() {
        string folder=AppDomain.CurrentDomain.BaseDirectory;
        string bundled=Path.Combine(folder,"runtime","pythonw.exe");
        string configured=Environment.GetEnvironmentVariable("OPENCAL_PYTHON");
        string python=File.Exists(bundled) ? bundled : (File.Exists(configured) ? configured : null);
        // Read installed Python locations; never install anything or invoke a
        // shell, Store alias, terminal command or downloaded runtime.
        if (python==null) {
            foreach (RegistryKey hive in new RegistryKey[] {Registry.CurrentUser,Registry.LocalMachine}) {
                using (RegistryKey core=hive.OpenSubKey(@"Software\Python\PythonCore")) {
                    if (core==null) continue;
                    string[] versions=core.GetSubKeyNames(); Array.Sort(versions); Array.Reverse(versions);
                    foreach (string version in versions) {
                        Version parsed;
                        if (!Version.TryParse(version,out parsed) || parsed<new Version(3,11)) continue;
                        using (RegistryKey install=core.OpenSubKey(version+@"\InstallPath")) {
                            if (install==null) continue;
                            string location=install.GetValue("") as string;
                            if (location==null) continue;
                            string candidate=Path.Combine(location,"pythonw.exe");
                            if (File.Exists(candidate)) {python=candidate;break;}
                        }
                    }
                }
                if (python!=null) break;
            }
        }
        if (python==null) {
            MessageBox.Show("OpenCal needs an installed Python 3.11 or newer with Tk. Install the free Windows Python distribution, or set OPENCAL_PYTHON to your pythonw.exe path.","OpenCal",MessageBoxButtons.OK,MessageBoxIcon.Information);
            return;
        }
        try {
            var info=new ProcessStartInfo(python,"-m opencal");
            info.WorkingDirectory=folder; info.UseShellExecute=false; info.CreateNoWindow=true;
            if (python==bundled) {
                string tcl=Path.Combine(folder,"runtime","tcl");
                foreach (string directory in Directory.GetDirectories(tcl)) {
                    if (File.Exists(Path.Combine(directory,"init.tcl"))) info.EnvironmentVariables["TCL_LIBRARY"]=directory;
                    if (File.Exists(Path.Combine(directory,"tk.tcl"))) info.EnvironmentVariables["TK_LIBRARY"]=directory;
                }
            }
            Process.Start(info);
        } catch (Exception error) {
            MessageBox.Show("OpenCal could not start: "+error.Message,"OpenCal",MessageBoxButtons.OK,MessageBoxIcon.Error);
        }
    }
}
