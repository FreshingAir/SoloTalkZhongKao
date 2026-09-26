# -*- coding: utf-8 -*-
"""Windows 徽标键 / Alt+Tab 屏蔽（模考全屏期间使用）。

通过低级键盘钩子拦截 Win / Alt / Tab 组合，避免考生切出考试界面。
非 Windows 平台不会被调用。
"""

import ctypes


def _wintype(name, fallback):
    return getattr(ctypes.wintypes, name, fallback)


_LRESULT = _wintype("LRESULT", ctypes.c_ssize_t)
_WPARAM = _wintype("WPARAM", ctypes.c_size_t)
_LPARAM = _wintype("LPARAM", ctypes.c_ssize_t)
_HHOOK = _wintype("HHOOK", ctypes.c_void_p)
_DWORD = _wintype("DWORD", ctypes.c_uint32)
_BOOL = _wintype("BOOL", ctypes.c_int)
_ULONG_PTR = ctypes.c_size_t


class WindowsKeyBlocker:
    _VK_LWIN = 0x5B
    _VK_RWIN = 0x5C
    _VK_MENU = 0x12
    _VK_TAB = 0x09
    _WH_KEYBOARD_LL = 13
    _BLOCK_KEYS = (_VK_LWIN, _VK_RWIN, _VK_MENU, _VK_TAB)

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", _DWORD), ("scanCode", _DWORD), ("flags", _DWORD),
            ("time", _DWORD), ("dwExtraInfo", ctypes.POINTER(_ULONG_PTR)),
        ]

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._user32.SetWindowsHookExW.restype = _HHOOK
        self._user32.UnhookWindowsHookEx.restype = _BOOL
        self._user32.UnhookWindowsHookEx.argtypes = [_HHOOK]
        self._user32.CallNextHookEx.restype = _LRESULT
        self._user32.CallNextHookEx.argtypes = [_HHOOK, ctypes.c_int, _WPARAM, _LPARAM]
        self._hook = None
        self._proc = None

    def _callback(self, nCode, wParam, lParam):
        try:
            if nCode == 0:
                kbd = ctypes.cast(lParam, ctypes.POINTER(self.KBDLLHOOKSTRUCT)).contents
                if kbd.vkCode in self._BLOCK_KEYS:
                    return 1
        except Exception:
            pass
        return self._user32.CallNextHookEx(None, nCode, wParam, lParam)

    def install(self):
        if self._hook:
            return
        self._proc = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, _WPARAM, _LPARAM)(self._callback)
        self._hook = self._user32.SetWindowsHookExW(self._WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            raise ctypes.WinError()

    def uninstall(self):
        if self._hook:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._proc = None
