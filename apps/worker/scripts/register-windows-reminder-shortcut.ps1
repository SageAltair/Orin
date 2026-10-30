# Explicit, per-user Windows toast identity registration. No API credentials are used.
# This is an opt-in developer utility, not an autostart or service installer.
[CmdletBinding(SupportsShouldProcess = $true, DefaultParameterSetName = 'Install')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Install')]
    [switch]$Install,

    [Parameter(Mandatory = $true, ParameterSetName = 'Remove')]
    [switch]$Remove,

    [Parameter(Mandatory = $true, ParameterSetName = 'Install')]
    [string]$PythonPath,

    [string]$AppId = 'Oddly.Orin.Reminders',

    # Override only for isolated CI testing. Normal users should omit this.
    [string]$AppDataRoot = $env:APPDATA
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'Windows toast registration requires Windows.'
}
if ($AppId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$') {
    throw 'Invalid Windows AppUserModelID.'
}
if ([string]::IsNullOrWhiteSpace($AppDataRoot) -or
    -not [IO.Path]::IsPathRooted($AppDataRoot)) {
    throw 'An absolute APPDATA root is required.'
}

$programs = Join-Path $AppDataRoot 'Microsoft\Windows\Start Menu\Programs'
$shortcutPath = Join-Path $programs 'Orin Task Reminders.lnk'
$arguments = '-m orin_worker.windows_reminders'

function Get-ShortcutIdentity {
    param([string]$Path)
    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.Namespace((Split-Path -Parent $Path))
    if ($null -eq $folder) { throw 'Start Menu folder is unavailable.' }
    $item = $folder.ParseName((Split-Path -Leaf $Path))
    if ($null -eq $item) { throw 'Start Menu shortcut is unavailable.' }
    return [string]$item.ExtendedProperty('System.AppUserModel.ID')
}

function Assert-OwnedShortcut {
    param([string]$Path, [string]$ExpectedId)
    $registered = Get-ShortcutIdentity -Path $Path
    if ($registered -cne $ExpectedId) {
        throw 'Existing shortcut has a different AppUserModelID; refusing to overwrite or remove it.'
    }
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    if ($link.Arguments -cne $arguments) {
        throw 'Existing shortcut is not an Orin reminder launcher; refusing to modify it.'
    }
    return $link
}

if ($Remove) {
    if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
        Write-Output 'No Orin reminder shortcut exists; nothing to remove.'
        return
    }
    $null = Assert-OwnedShortcut -Path $shortcutPath -ExpectedId $AppId
    if ($PSCmdlet.ShouldProcess($shortcutPath, 'Remove Orin reminder identity shortcut')) {
        Remove-Item -LiteralPath $shortcutPath -ErrorAction Stop
        Write-Output 'Orin reminder identity shortcut removed. No service or user data was changed.'
    }
    return
}

if (-not [IO.Path]::IsPathRooted($PythonPath) -or
    [IO.Path]::GetExtension($PythonPath) -ine '.exe' -or
    -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'PythonPath must be an existing absolute .exe path from the installed worker environment.'
}
$PythonPath = (Get-Item -LiteralPath $PythonPath).FullName

if (Test-Path -LiteralPath $shortcutPath) {
    $existing = Assert-OwnedShortcut -Path $shortcutPath -ExpectedId $AppId
    if ($existing.TargetPath -ine $PythonPath) {
        throw 'Orin reminder shortcut points to a different Python executable; refusing to overwrite it.'
    }
    Write-Output 'Matching Orin reminder identity shortcut already exists; no changes made.'
    return
}
if (-not $PSCmdlet.ShouldProcess($shortcutPath, 'Register per-user Orin reminder toast identity')) {
    return
}

# ShellLink exposes IPropertyStore; WScript.Shell alone cannot set AUMID.
# Property key from Microsoft's PKEY_AppUserModel_ID specification.
$source = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Orin.Windows {
    [ComImport, Guid("00021401-0000-0000-C000-000000000046"),
     ClassInterface(ClassInterfaceType.None)]
    internal class ShellLinkObject { }

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IShellLinkW {
        void GetPath(StringBuilder file, int maxPath, IntPtr data, uint flags);
        void GetIDList(out IntPtr list);
        void SetIDList(IntPtr list);
        void GetDescription(StringBuilder description, int maxName);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string description);
        void GetWorkingDirectory(StringBuilder directory, int maxPath);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string directory);
        void GetArguments(StringBuilder arguments, int maxPath);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string arguments);
        void GetHotkey(out short hotkey);
        void SetHotkey(short hotkey);
        void GetShowCmd(out int command);
        void SetShowCmd(int command);
        void GetIconLocation(StringBuilder path, int maxPath, out int icon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int icon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string relative, int reserved);
        void Resolve(IntPtr window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    internal struct PropertyKey {
        public Guid FormatId;
        public uint PropertyId;
    }

    // Native PROPVARIANT is 24 bytes on x64 (16 on x86). Allocate the
    // larger representation to prevent IPropertyStore from reading past
    // the managed buffer on 64-bit Windows; pointer offset is 8 on both.
    [StructLayout(LayoutKind.Explicit, Size = 24)]
    internal struct PropVariant {
        [FieldOffset(0)] public ushort VariantType;
        [FieldOffset(8)] public IntPtr Value;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IPropertyStore {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IPersistFile {
        void GetClassID(out Guid classId);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string path, uint mode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string path,
                  [MarshalAs(UnmanagedType.Bool)] bool remember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string path);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string path);
    }

    public static class ShortcutRegistration {
        public static void Create(string python, string path, string appId) {
            object link = new ShellLinkObject();
            try {
                var shell = (IShellLinkW)link;
                shell.SetPath(python);
                shell.SetArguments("-m orin_worker.windows_reminders");
                shell.SetDescription("Orin task reminder companion (manual opt-in)");
                var store = (IPropertyStore)link;
                var key = new PropertyKey {
                    FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
                    PropertyId = 5
                };
                var value = new PropVariant {
                    VariantType = 31, // VT_LPWSTR
                    Value = Marshal.StringToCoTaskMemUni(appId)
                };
                try {
                    store.SetValue(ref key, ref value);
                    store.Commit();
                } finally {
                    Marshal.FreeCoTaskMem(value.Value);
                }
                ((IPersistFile)link).Save(path, true);
            } finally {
                Marshal.ReleaseComObject(link);
            }
        }
    }
}
'@

New-Item -ItemType Directory -Path $programs -Force | Out-Null
# Stage a uniquely named .lnk and move it into place without overwriting.
# This prevents concurrent installations from replacing an unrelated shortcut
# created after the initial existence check.
$temporaryPath = Join-Path $programs ('.orin-reminder-' + [guid]::NewGuid().ToString('N') + '.lnk')
try {
    Add-Type -TypeDefinition $source -Language CSharp -ErrorAction Stop
    [Orin.Windows.ShortcutRegistration]::Create($PythonPath, $temporaryPath, $AppId)
    $null = Assert-OwnedShortcut -Path $temporaryPath -ExpectedId $AppId
    [IO.File]::Move($temporaryPath, $shortcutPath) # Fails if destination now exists.
    $null = Assert-OwnedShortcut -Path $shortcutPath -ExpectedId $AppId
    Write-Output 'Orin reminder identity registered. No reminder was sent or companion started.'
    Write-Output ('ORIN_WINDOWS_REMINDERS_APP_ID=' + $AppId)
    Write-Output ('ORIN_WINDOWS_REMINDERS_SHORTCUT=' + $shortcutPath)
} finally {
    # Never remove the final destination on error: it might belong to another
    # process. Only our private staging file is eligible for cleanup.
    if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryPath -ErrorAction SilentlyContinue
    }
}
