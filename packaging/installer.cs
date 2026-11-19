using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Principal;
using System.Text;

[assembly: AssemblyTitle("BiliNote Mini Setup")]
[assembly: AssemblyProduct("BiliNote Mini")]
[assembly: AssemblyDescription("BiliNote Mini Windows installer")]
[assembly: AssemblyVersion("0.7.6.0")]
[assembly: AssemblyFileVersion("0.7.6.0")]

internal static class Program
{
    private static string InstallDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "BiliNote Mini");

    private static int Main(string[] args)
    {
        try { Console.OutputEncoding = Encoding.UTF8; } catch { }
        try { Console.Title = "BiliNote Mini 安装程序"; } catch { }
        string requestedDir = null;
        foreach (string arg in args)
        {
            if (arg.StartsWith("/DIR=", StringComparison.OrdinalIgnoreCase))
            {
                requestedDir = arg.Substring(5).Trim('"');
            }
        }

        Console.WriteLine("BiliNote Mini 安装程序");
        try
        {
            InstallDir = ResolveInstallDir(requestedDir);
        }
        catch (Exception ex)
        {
            Console.WriteLine("安装失败：" + ex.Message);
            if (!IsElevated() && TryElevate(args))
            {
                Console.WriteLine("已请求管理员权限继续安装，请在弹出的窗口中确认。");
                return 0;
            }
            Console.WriteLine("按 Enter 退出...");
            try { Console.ReadLine(); } catch { }
            return 1;
        }
        Console.WriteLine("安装目录：" + InstallDir);
        Console.WriteLine();

        try
        {
            StopOldProcesses();
            ExtractPayload();
            int code = RunInstallScript();
            if (code != 0)
            {
                throw new InvalidOperationException("安装脚本返回错误码 " + code + "，请查看上方输出。");
            }
            Console.WriteLine();
            Console.WriteLine("安装完成。托盘图标已在通知区域，右键可退出或打开工作台。");
            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine();
            Console.WriteLine("安装失败：" + ex.Message);
            Console.WriteLine("如果反复失败，可以解压 Setup.zip 后运行 install.cmd，");
            Console.WriteLine("或用 /DIR=C:\\BiliNoteMini 指定一个确定可写的目录。");
            if (!IsElevated())
            {
                Console.WriteLine("也可以用管理员身份运行本安装程序。");
            }
            Console.WriteLine("按 Enter 退出...");
            try { Console.ReadLine(); } catch { }
            return 1;
        }
    }

    private static bool IsElevated()
    {
        try
        {
            using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
            {
                WindowsPrincipal principal = new WindowsPrincipal(identity);
                return principal.IsInRole(WindowsBuiltInRole.Administrator);
            }
        }
        catch
        {
            return false;
        }
    }

    private static bool TryElevate(string[] args)
    {
        try
        {
            StringBuilder quoted = new StringBuilder();
            foreach (string arg in args)
            {
                if (quoted.Length > 0) quoted.Append(' ');
                quoted.Append('"').Append(arg.Replace("\"", "\\\"")).Append('"');
            }
            ProcessStartInfo info = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, quoted.ToString());
            info.UseShellExecute = true;
            info.Verb = "runas";
            Process.Start(info);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static string ResolveInstallDir(string requestedDir)
    {
        if (!string.IsNullOrEmpty(requestedDir))
        {
            string explicitDir = Path.GetFullPath(requestedDir);
            EnsureWritable(explicitDir);
            return explicitDir;
        }

        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string roaming = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        string profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string documents = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        string publicDir = Environment.GetFolderPath(Environment.SpecialFolder.CommonDocuments);
        string[] candidates = new string[]
        {
            Path.Combine(local, "BiliNote Mini"),
            Path.Combine(local, "BiliNoteMini"),
            Path.Combine(roaming, "BiliNoteMini"),
            Path.Combine(profile, "BiliNoteMini"),
            Path.Combine(documents, "BiliNoteMini"),
            Path.Combine(publicDir, "BiliNoteMini"),
            Path.Combine(desktop, "BiliNoteMini"),
            @"C:\BiliNoteMini",
            Path.Combine(Environment.CurrentDirectory, "BiliNoteMini")
        };

        Exception last = null;
        foreach (string candidate in candidates)
        {
            if (string.IsNullOrWhiteSpace(candidate)) continue;
            try
            {
                string full = Path.GetFullPath(candidate);
                EnsureWritable(full);
                return full;
            }
            catch (Exception ex)
            {
                last = ex;
                Console.WriteLine("目录不可用，尝试下一个：" + candidate);
            }
        }
        throw new InvalidOperationException(
            "默认目录和备用目录都无法写入。最后一个错误：" + (last == null ? "未知" : last.Message));
    }

    private static void EnsureWritable(string dir)
    {
        Directory.CreateDirectory(dir);
        string probe = Path.Combine(dir, ".write-test-" + Guid.NewGuid().ToString("N"));
        File.WriteAllText(probe, "ok");
        File.Delete(probe);
    }

    private static void StopOldProcesses()
    {
        string stopScript = Path.Combine(InstallDir, "packaging", "stop.ps1");
        if (!File.Exists(stopScript)) return;
        try
        {
            ProcessStartInfo info = new ProcessStartInfo("powershell.exe",
                "-NoProfile -ExecutionPolicy Bypass -File \"" + stopScript + "\"");
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WorkingDirectory = InstallDir;
            using (Process process = Process.Start(info))
            {
                process.WaitForExit(8000);
            }
            Console.WriteLine("已停止旧版本进程。");
        }
        catch
        {
            // A failed cleanup should not block a fresh install.
        }
    }

    private static void ExtractPayload()
    {
        Console.WriteLine("正在解压程序文件...");
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
        {
            if (stream == null) throw new InvalidOperationException("安装包缺少 payload.zip。");
            using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                int total = archive.Entries.Count;
                int done = 0;
                string root = InstallDir.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string target = Path.GetFullPath(Path.Combine(root, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    {
                        throw new InvalidOperationException("安装包包含非法路径：" + entry.FullName);
                    }
                    if (string.IsNullOrEmpty(entry.Name))
                    {
                        Directory.CreateDirectory(target);
                    }
                    else
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(target));
                        entry.ExtractToFile(target, true);
                    }
                    done++;
                    if (done % 20 == 0 || done == total)
                    {
                        Console.Write("\r  已解压 {0}/{1}", done, total);
                    }
                }
                Console.WriteLine();
            }
        }
    }

    private static int RunInstallScript()
    {
        string script = Path.Combine(InstallDir, "packaging", "install.ps1");
        if (!File.Exists(script))
        {
            throw new InvalidOperationException("安装包缺少 packaging\\install.ps1。");
        }
        Console.WriteLine("正在准备 Python 环境和依赖（首次需要联网，可能需要几分钟）...");
        ProcessStartInfo info = new ProcessStartInfo("powershell.exe",
            "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\" -RuntimeOnly -InstallDir \"" + InstallDir + "\"");
        info.UseShellExecute = false;
        info.WorkingDirectory = InstallDir;
        using (Process process = Process.Start(info))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }
}
