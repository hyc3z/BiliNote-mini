using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        bool created;
        using (Mutex mutex = new Mutex(true, "Local\\BiliNoteMiniTrayHost", out created))
        {
            if (!created)
            {
                MessageBox.Show("BiliNote Mini 已经在运行。\n\n如果任务栏没有图标，请点击右下角的 ^ 查看隐藏图标。",
                    "BiliNote Mini", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new TrayContext(args));
        }
    }
}

internal sealed class TrayContext : ApplicationContext
{
    private const string BaseUrl = "http://127.0.0.1:8483";
    private const string HealthUrl = BaseUrl + "/api/sys_check";
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string RunValue = "BiliNoteMini";
    private const string TaskName = "BiliNoteMini";

    private readonly string root;
    private readonly string backendDir;
    private readonly string python;
    private readonly NotifyIcon notify;
    private readonly ToolStripMenuItem autostartItem;
    private Process backend;
    private bool owned;
    private readonly object logLock = new object();

    public TrayContext(string[] args)
    {
        root = Path.GetDirectoryName(Application.ExecutablePath);
        backendDir = Path.Combine(root, "backend");
        python = Path.Combine(backendDir, ".venv", "Scripts", "python.exe");

        Icon icon;
        try
        {
            icon = new Icon(Path.Combine(root, "packaging", "assets", "bilinote.ico"));
        }
        catch
        {
            icon = SystemIcons.Application;
        }

        ContextMenuStrip menu = new ContextMenuStrip();
        menu.Items.Add(new ToolStripMenuItem("打开工作台", null, delegate { OpenUrl(BaseUrl); }) { Font = new Font(menu.Font, FontStyle.Bold) });
        menu.Items.Add(new ToolStripMenuItem("打开数据目录", null, delegate { OpenFolder(Path.Combine(backendDir, "data")); }));
        menu.Items.Add(new ToolStripMenuItem("打开日志", null, delegate { OpenFolder(Path.Combine(backendDir, "logs")); }));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("重启后端", null, delegate { RestartBackend(); }));
        autostartItem = new ToolStripMenuItem("开机自启动", null, delegate { ToggleAutostart(); });
        autostartItem.Checked = IsAutostartEnabled();
        menu.Items.Add(autostartItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("退出 BiliNote", null, delegate { ExitApp(); }));

        notify = new NotifyIcon();
        notify.Icon = icon;
        notify.Text = "BiliNote Mini";
        notify.ContextMenuStrip = menu;
        notify.DoubleClick += delegate { OpenUrl(BaseUrl); };
        notify.Visible = true;
        Log("tray host started; install=" + root);

        bool open = Array.IndexOf(args, "--open") >= 0;
        Thread thread = new Thread(new ThreadStart(delegate { StartBackendAndMaybeOpen(open); }));
        thread.IsBackground = true;
        thread.Start();
    }

    private void StartBackendAndMaybeOpen(bool open)
    {
        if (Health())
        {
            owned = false;
            Log("backend already healthy; attaching");
            Balloon("BiliNote Mini 已连接现有后端");
        }
        else if (!File.Exists(python))
        {
            Log("missing python: " + python);
            Balloon("找不到 Python 环境，请重新运行安装程序");
            return;
        }
        else
        {
            try
            {
                Directory.CreateDirectory(Path.Combine(backendDir, "logs"));
                ProcessStartInfo info = new ProcessStartInfo(python, "-u main.py");
                info.WorkingDirectory = backendDir;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.RedirectStandardOutput = true;
                info.RedirectStandardError = true;
                info.EnvironmentVariables["PYTHONUTF8"] = "1";
                info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                info.EnvironmentVariables["BACKEND_HOST"] = "127.0.0.1";
                info.EnvironmentVariables["BACKEND_PORT"] = "8483";
                backend = new Process();
                backend.StartInfo = info;
                backend.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { LogBackend("out", e.Data); };
                backend.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { LogBackend("err", e.Data); };
                backend.Start();
                backend.BeginOutputReadLine();
                backend.BeginErrorReadLine();
                owned = true;
                try
                {
                    Directory.CreateDirectory(Path.Combine(backendDir, ".run"));
                    File.WriteAllText(Path.Combine(backendDir, ".run", "backend.pid"), backend.Id.ToString());
                }
                catch { }
                Log("backend started pid=" + backend.Id);

                DateTime deadline = DateTime.UtcNow.AddSeconds(60);
                while (DateTime.UtcNow < deadline)
                {
                    if (backend.HasExited)
                    {
                        Log("backend exited code=" + backend.ExitCode);
                        Balloon("后端启动失败，请查看日志");
                        return;
                    }
                    if (Health())
                    {
                        Balloon("BiliNote Mini 已就绪");
                        break;
                    }
                    Thread.Sleep(500);
                }
            }
            catch (Exception ex)
            {
                Log("start backend failed: " + ex);
                Balloon("后端启动失败：" + ex.Message);
                return;
            }
        }

        if (open)
        {
            Thread.Sleep(400);
            OpenUrl(BaseUrl);
        }
    }

    private bool Health()
    {
        try
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(HealthUrl);
            request.Timeout = 1200;
            request.ReadWriteTimeout = 1200;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            {
                if ((int)response.StatusCode != 200) return false;
                using (StreamReader reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                {
                    string body = reader.ReadToEnd();
                    return body.IndexOf("\"code\":0", StringComparison.Ordinal) >= 0 ||
                           body.IndexOf("\"code\": 0", StringComparison.Ordinal) >= 0;
                }
            }
        }
        catch
        {
            return false;
        }
    }

    private void RestartBackend()
    {
        if (!owned && Health())
        {
            MessageBox.Show("当前后端不是由托盘启动的，请在原进程里重启。", "BiliNote Mini",
                MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        StopBackend();
        Thread.Sleep(800);
        Thread thread = new Thread(new ThreadStart(delegate { StartBackendAndMaybeOpen(false); }));
        thread.IsBackground = true;
        thread.Start();
    }

    private void StopBackend()
    {
        Process process = backend;
        backend = null;
        bool wasOwned = owned;
        owned = false;
        if (!wasOwned || process == null) return;
        try
        {
            Log("stopping backend pid=" + process.Id);
            ProcessStartInfo kill = new ProcessStartInfo("taskkill", "/PID " + process.Id + " /T /F");
            kill.UseShellExecute = false;
            kill.CreateNoWindow = true;
            using (Process p = Process.Start(kill)) { p.WaitForExit(8000); }
        }
        catch (Exception ex)
        {
            Log("stop backend failed: " + ex.Message);
        }
        try { File.Delete(Path.Combine(backendDir, ".run", "backend.pid")); } catch { }
    }

    private void OpenUrl(string url)
    {
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            Log("open url failed: " + ex.Message);
            MessageBox.Show("无法打开浏览器：" + ex.Message, "BiliNote Mini");
        }
    }

    private void OpenFolder(string path)
    {
        try
        {
            Directory.CreateDirectory(path);
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            MessageBox.Show("无法打开目录：" + ex.Message, "BiliNote Mini");
        }
    }

    private bool IsAutostartEnabled()
    {
        try
        {
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RunKey))
            {
                if (key != null && key.GetValue(RunValue) != null) return true;
            }
        }
        catch { }
        return RunSchtasks("/Query /TN " + TaskName) == 0;
    }

    private void ToggleAutostart()
    {
        try
        {
            if (IsAutostartEnabled())
            {
                try
                {
                    using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RunKey, true))
                    {
                        if (key != null) key.DeleteValue(RunValue, false);
                    }
                }
                catch { }
                RunSchtasks("/Delete /TN " + TaskName + " /F");
                autostartItem.Checked = false;
                return;
            }

            bool ok = false;
            try
            {
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(RunKey))
                {
                    key.SetValue(RunValue, "\"" + Application.ExecutablePath + "\" --autostart");
                }
                ok = true;
            }
            catch { }

            if (!ok)
            {
                string cmd = Path.Combine(root, "Autostart-BiliNoteMini.cmd");
                File.WriteAllText(cmd,
                    "@echo off\r\nstart \"\" \"" + Application.ExecutablePath + "\" --autostart\r\n",
                    Encoding.ASCII);
                ok = RunSchtasks("/Create /TN " + TaskName + " /SC ONLOGON /TR \"" + cmd + "\" /RL LIMITED /F") == 0;
            }

            autostartItem.Checked = ok || IsAutostartEnabled();
            if (!autostartItem.Checked)
            {
                MessageBox.Show("无法设置开机自启动，请改用管理员权限或在任务计划程序中手动创建。",
                    "BiliNote Mini", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show("无法修改开机自启动：" + ex.Message, "BiliNote Mini");
        }
    }

    private static int RunSchtasks(string arguments)
    {
        try
        {
            ProcessStartInfo info = new ProcessStartInfo("schtasks.exe", arguments);
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            using (Process process = Process.Start(info))
            {
                if (!process.WaitForExit(10000))
                {
                    try { process.Kill(); } catch { }
                    return -1;
                }
                return process.ExitCode;
            }
        }
        catch
        {
            return -1;
        }
    }

    private void ExitApp()
    {
        StopBackend();
        notify.Visible = false;
        notify.Dispose();
        ExitThread();
    }

    private void Balloon(string text)
    {
        try
        {
            notify.BalloonTipTitle = "BiliNote Mini";
            notify.BalloonTipText = text;
            notify.ShowBalloonTip(3000);
        }
        catch { }
    }

    private void LogBackend(string stream, string line)
    {
        if (line == null) return;
        string file = Path.Combine(backendDir, "logs", stream == "err" ? "tray-backend.err.log" : "tray-backend.out.log");
        try
        {
            lock (logLock) { File.AppendAllText(file, line + Environment.NewLine, Encoding.UTF8); }
        }
        catch { }
    }

    private void Log(string text)
    {
        try
        {
            string file = Path.Combine(backendDir, "logs", "tray-host.log");
            Directory.CreateDirectory(Path.GetDirectoryName(file));
            lock (logLock) { File.AppendAllText(file, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + text + Environment.NewLine, Encoding.UTF8); }
        }
        catch { }
    }
}
