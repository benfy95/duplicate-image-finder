// Single-file launcher for Duplicate Image Finder.
//
// The release exe is this small program with the zipped app folder appended:
//     [launcher exe][app.zip][trailer]
// trailer (40 bytes) = zip length (int64) + build id (24 ASCII chars) + "DIFPACK1"
//
// First launch (or after an update): unpacks the app to <exe folder>\data\app\
// with a progress window, then starts it. Later launches start it right away.
// Settings, cache and logs stay in <exe folder>\data and \logs (the app is told
// where through the DIF_HOME environment variable), so updating never loses them.
// If the exe's folder is not writable, %LOCALAPPDATA%\DuplicateImageFinder is used.
//
// Built by tools\pack_single_exe.py with the C# compiler that ships with Windows.

using System;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

static class Launcher
{
    const string Magic = "DIFPACK1";
    const int TrailerSize = 8 + 24 + 8;
    const string AppExe = "DuplicateImageFinder.exe";
    static readonly bool Zh = CultureInfo.CurrentUICulture.Name.StartsWith("zh", StringComparison.OrdinalIgnoreCase);

    static string T(string en, string zh) { return Zh ? zh : en; }

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            string self = Process.GetCurrentProcess().MainModule.FileName;
            long zipOffset, zipLength;
            string buildId;
            ReadTrailer(self, out zipOffset, out zipLength, out buildId);

            string home = PickHome(Path.GetDirectoryName(self));
            string appDir = Path.Combine(home, "data", "app");
            string marker = Path.Combine(appDir, ".build");

            if (!IsCurrent(appDir, marker, buildId))
            {
                // One unpacker at a time (double-clicking twice must not corrupt it).
                using (var mutex = new Mutex(false, "DuplicateImageFinder-unpack-" + buildId))
                {
                    try { mutex.WaitOne(); } catch (AbandonedMutexException) { }
                    try
                    {
                        if (!IsCurrent(appDir, marker, buildId))
                            if (!Unpack(self, zipOffset, zipLength, appDir, marker, buildId))
                                return 1;
                    }
                    finally { mutex.ReleaseMutex(); }
                }
            }

            var psi = new ProcessStartInfo(Path.Combine(appDir, AppExe))
            {
                UseShellExecute = false,
                Arguments = string.Join(" ", args.Select(Quote)),
                WorkingDirectory = Environment.CurrentDirectory,
            };
            psi.EnvironmentVariables["DIF_HOME"] = home;
            Process.Start(psi);
            return 0;
        }
        catch (Exception e)
        {
            MessageBox.Show(T("Duplicate Image Finder could not start:\n\n", "無法啟動 Duplicate Image Finder：\n\n") + e.Message,
                            "Duplicate Image Finder", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string Quote(string a)
    {
        return a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '"' }) < 0 ? a : "\"" + a.Replace("\"", "\\\"") + "\"";
    }

    static void ReadTrailer(string path, out long offset, out long length, out string buildId)
    {
        using (var f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        {
            if (f.Length < TrailerSize) throw new InvalidDataException("no app data in this exe");
            var t = new byte[TrailerSize];
            f.Seek(-TrailerSize, SeekOrigin.End);
            f.Read(t, 0, TrailerSize);
            if (Encoding.ASCII.GetString(t, 32, 8) != Magic)
                throw new InvalidDataException(T("this exe is incomplete (no app data found); download it again",
                                                 "此執行檔不完整（找不到程式資料），請重新下載"));
            length = BitConverter.ToInt64(t, 0);
            buildId = Encoding.ASCII.GetString(t, 8, 24).Trim();
            offset = f.Length - TrailerSize - length;
            if (offset <= 0) throw new InvalidDataException("corrupt app data");
        }
    }

    /// Folder for data\ and logs\: next to the exe if writable, else in the user profile.
    static string PickHome(string exeDir)
    {
        try
        {
            string data = Path.Combine(exeDir, "data");
            Directory.CreateDirectory(data);
            string probe = Path.Combine(data, ".write_test");
            File.WriteAllText(probe, "ok");
            File.Delete(probe);
            return exeDir;
        }
        catch (Exception)
        {
            string home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                       "DuplicateImageFinder");
            Directory.CreateDirectory(home);
            return home;
        }
    }

    static bool IsCurrent(string appDir, string marker, string buildId)
    {
        try
        {
            return File.Exists(Path.Combine(appDir, AppExe)) && File.Exists(marker)
                && File.ReadAllText(marker).Trim() == buildId;
        }
        catch (Exception) { return false; }
    }

    static bool Unpack(string self, long offset, long length, string appDir, string marker, string buildId)
    {
        string tmp = appDir + ".new";
        string old = appDir + ".old";
        Exception error = null;
        bool canceled = false;

        var form = new Form
        {
            Text = "Duplicate Image Finder",
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false, MinimizeBox = false,
            StartPosition = FormStartPosition.CenterScreen,
            ClientSize = new Size(440, 110),
            Font = SystemFonts.MessageBoxFont,
        };
        try { form.Icon = Icon.ExtractAssociatedIcon(self); } catch (Exception) { }
        var label = new Label
        {
            Text = T("Preparing Duplicate Image Finder (first launch only)…", "正在準備 Duplicate Image Finder（僅首次啟動）…"),
            AutoSize = false, Location = new Point(16, 14), Size = new Size(408, 22),
        };
        var bar = new ProgressBar { Location = new Point(16, 42), Size = new Size(408, 20), Maximum = 1000 };
        var detail = new Label { AutoSize = false, Location = new Point(16, 72), Size = new Size(408, 22), ForeColor = SystemColors.GrayText };
        form.Controls.AddRange(new Control[] { label, bar, detail });

        var worker = new Thread(() =>
        {
            try
            {
                if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
                Directory.CreateDirectory(tmp);
                using (var f = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var zip = new ZipArchive(new SubStream(f, offset, length), ZipArchiveMode.Read))
                {
                    long total = Math.Max(1, zip.Entries.Sum(e => e.Length)), done = 0;
                    string root = Path.GetFullPath(tmp) + Path.DirectorySeparatorChar;
                    var buf = new byte[1 << 20];
                    foreach (var e in zip.Entries)
                    {
                        if (canceled) return;
                        string dest = Path.GetFullPath(Path.Combine(tmp, e.FullName));
                        if (!dest.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;   // never outside
                        if (e.FullName.EndsWith("/")) { Directory.CreateDirectory(dest); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(dest));
                        using (var src = e.Open())
                        using (var dst = new FileStream(dest, FileMode.Create, FileAccess.Write))
                        {
                            int n;
                            while ((n = src.Read(buf, 0, buf.Length)) > 0)
                            {
                                dst.Write(buf, 0, n);
                                done += n;
                            }
                        }
                        long d = done;
                        form.BeginInvoke((Action)(() =>
                        {
                            bar.Value = (int)Math.Min(1000, d * 1000 / total);
                            detail.Text = string.Format("{0} / {1} MB", d >> 20, total >> 20);
                        }));
                    }
                }
                File.WriteAllText(Path.Combine(tmp, ".build"), buildId);
                // swap in the new version; the old one may still be running
                if (Directory.Exists(old)) TryDelete(old);
                if (Directory.Exists(appDir))
                {
                    try { Directory.Move(appDir, old); }
                    catch (IOException)
                    {
                        throw new IOException(T("Duplicate Image Finder is still running. Close it and start this exe again.",
                                                "Duplicate Image Finder 仍在執行中。請先關閉它，再重新啟動此執行檔。"));
                    }
                }
                Directory.Move(tmp, appDir);
                TryDelete(old);
            }
            catch (Exception e) { error = e; }
            finally
            {
                try { form.BeginInvoke((Action)(() => form.Close())); } catch (Exception) { }
            }
        }) { IsBackground = true };

        form.FormClosing += (s, e) =>
        {
            if (worker.IsAlive && e.CloseReason == CloseReason.UserClosing) canceled = true;
        };
        form.Shown += (s, e) => worker.Start();
        Application.EnableVisualStyles();
        Application.Run(form);
        worker.Join();

        if (canceled) { TryDelete(tmp); return false; }
        if (error != null)
        {
            TryDelete(tmp);
            MessageBox.Show(T("Could not prepare the app:\n\n", "無法準備程式：\n\n") + error.Message,
                            "Duplicate Image Finder", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
        return true;
    }

    static void TryDelete(string dir)
    {
        try { if (Directory.Exists(dir)) Directory.Delete(dir, true); } catch (Exception) { }
    }
}

/// Read-only window [offset, offset+length) of another stream (the zip inside the exe).
class SubStream : Stream
{
    readonly Stream s; readonly long off, len; long pos;
    public SubStream(Stream s, long off, long len) { this.s = s; this.off = off; this.len = len; }
    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return len; } }
    public override long Position { get { return pos; } set { pos = value; } }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count)
    {
        long left = len - pos;
        if (left <= 0) return 0;
        if (count > left) count = (int)left;
        s.Seek(off + pos, SeekOrigin.Begin);
        int n = s.Read(buffer, offset, count);
        pos += n;
        return n;
    }
    public override long Seek(long offset, SeekOrigin origin)
    {
        pos = origin == SeekOrigin.Begin ? offset : origin == SeekOrigin.Current ? pos + offset : len + offset;
        return pos;
    }
    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] b, int o, int c) { throw new NotSupportedException(); }
}
