"""Folder picker that allows selecting several folders at once.

Windows: the system "Select Folder" dialog (IFileOpenDialog with FOS_PICKFOLDERS |
FOS_ALLOWMULTISELECT) through ctypes, so it looks like every other Windows app.
Elsewhere, or if that fails: Qt's own dialog with multi-selection enabled.
"""

import ctypes
import os
import sys
import uuid
from ctypes import POINTER, byref, c_uint, c_ulong, c_void_p, c_wchar_p, wintypes

from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QListView, QTreeView


def pick_folders(parent, title, start=""):
    """List of chosen folder paths ([] when canceled)."""
    if sys.platform == "win32":
        try:
            return _pick_windows(int(parent.winId()) if parent else 0, title, start)
        except Exception:
            pass
    return _pick_qt(parent, title, start)


# ------------------------------------------------------------------ Windows (COM)
class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    def __init__(self, s):
        super().__init__()
        ctypes.memmove(self.data, uuid.UUID(s).bytes_le, 16)


_CLSID_FileOpenDialog = "{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}"
_IID_IFileOpenDialog = "{d57c7288-d4ad-4768-be02-9d969532d960}"
_IID_IShellItem = "{43826d1e-e718-42ee-bc55-a1e261c37bfe}"
_FOS_PICKFOLDERS, _FOS_FORCEFILESYSTEM, _FOS_ALLOWMULTISELECT, _FOS_PATHMUSTEXIST = 0x20, 0x40, 0x200, 0x800
_SIGDN_FILESYSPATH = 0x80058000
_ERROR_CANCELLED = 0x800704C7
_HR = ctypes.c_long


def _call(obj, index, *args, argtypes=()):
    """Call method number `index` of the COM object's vtable; returns the HRESULT."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(_HR, c_void_p, *argtypes)(vtbl[index])
    return fn(obj, *args) & 0xFFFFFFFF


def _check(hr):
    if hr & 0x80000000:
        raise OSError(f"COM call failed: 0x{hr:08X}")


def _release(obj):
    if obj:
        _call(obj, 2)


def _pick_windows(hwnd, title, start):
    ole32, shell32 = ctypes.OleDLL("ole32"), ctypes.WinDLL("shell32")
    try:
        ctypes.windll.ole32.CoInitialize(None)   # Qt already initialized COM: harmless
    except OSError:
        pass
    dlg = c_void_p()
    _check(ole32.CoCreateInstance(byref(_GUID(_CLSID_FileOpenDialog)), None, 1,   # CLSCTX_INPROC_SERVER
                                  byref(_GUID(_IID_IFileOpenDialog)), byref(dlg)) & 0xFFFFFFFF)
    items = c_void_p()
    try:
        opts = c_uint()
        _check(_call(dlg, 10, byref(opts), argtypes=(POINTER(c_uint),)))                     # GetOptions
        _check(_call(dlg, 9, c_uint(opts.value | _FOS_PICKFOLDERS | _FOS_FORCEFILESYSTEM
                                    | _FOS_ALLOWMULTISELECT | _FOS_PATHMUSTEXIST),
                     argtypes=(c_uint,)))                                                     # SetOptions
        if title:
            _call(dlg, 17, c_wchar_p(title), argtypes=(c_wchar_p,))                          # SetTitle
        if start and os.path.isdir(start):
            folder = c_void_p()
            shell32.SHCreateItemFromParsingName.restype = _HR
            if shell32.SHCreateItemFromParsingName(c_wchar_p(start), None, byref(_GUID(_IID_IShellItem)),
                                                   byref(folder)) == 0:
                _call(dlg, 12, folder, argtypes=(c_void_p,))                                  # SetFolder
                _release(folder)
        hr = _call(dlg, 3, wintypes.HWND(hwnd), argtypes=(wintypes.HWND,))                    # Show
        if hr == _ERROR_CANCELLED:
            return []
        _check(hr)
        _check(_call(dlg, 27, byref(items), argtypes=(POINTER(c_void_p),)))                  # GetResults
        count = c_ulong()
        _check(_call(items, 7, byref(count), argtypes=(POINTER(c_ulong),)))                  # GetCount
        out = []
        for i in range(count.value):
            item = c_void_p()
            if _call(items, 8, c_ulong(i), byref(item), argtypes=(c_ulong, POINTER(c_void_p))) != 0:  # GetItemAt
                continue
            name = c_wchar_p()
            if _call(item, 5, c_uint(_SIGDN_FILESYSPATH), byref(name),
                     argtypes=(c_uint, POINTER(c_wchar_p))) == 0 and name.value:            # GetDisplayName
                out.append(name.value)
                ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(name, c_void_p))
            _release(item)
        return out
    finally:
        _release(items)
        _release(dlg)


# ------------------------------------------------------------------ Qt fallback
def _pick_qt(parent, title, start):
    dlg = QFileDialog(parent, title, start)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)   # native one can't multi-select here
    for view in dlg.findChildren(QListView) + dlg.findChildren(QTreeView):
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    if dlg.exec():
        return [f for f in dlg.selectedFiles() if os.path.isdir(f)]
    return []
