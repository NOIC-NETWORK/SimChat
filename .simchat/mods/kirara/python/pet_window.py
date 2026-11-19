"""Kirara 桌宠 · Win32 分层窗口（Layered Window，逐像素 alpha）最小实现。

属于 Kirara 行为包自己的可选脚本，由使用者手动运行；SimChat 宿主不启动它，
也不保存任何桌宠偏好。

只验证「真透明」这一件事：直接加载 MOD 里的立绘 PNG，用 UpdateLayeredWindow
把预乘 alpha 的位图交给 DWM，桌面内容从透明像素里透出来，不做任何 WebView 合成。

能力：
    · 无边框、置顶（WS_EX_TOPMOST）、不进任务栏（WS_EX_TOOLWINDOW）
    · 左键拖动移动窗口；透明像素命中测试返回 HTTRANSPARENT，不挡后面的窗口
    · 右键弹出菜单：归位 / 退出

单独运行（只看桌宠）：
    py .simchat/mods/kirara/python/pet_window.py
"""

import ctypes
import os
import threading

import win32api
import win32con
import win32gui
from PIL import Image, ImageChops

_DEFAULT_SPRITE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sprites",
    "characters",
    "kirara",
    "common",
    "kirara-common-default.png",
)

_CLASS_NAME = "SimChatKiraraLayeredPet"

# ---- gdi32 / user32 声明（UpdateLayeredWindow 只有 ctypes 这条路）----


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


_gdi32 = ctypes.windll.gdi32
_user32 = ctypes.windll.user32
_gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
_gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
_gdi32.CreateDIBSection.restype = ctypes.c_void_p
_gdi32.CreateDIBSection.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_BITMAPINFO),
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
    ctypes.c_uint32,
]
_gdi32.SelectObject.restype = ctypes.c_void_p
_gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
_gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
_gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
_gdi32.GetDeviceCaps.restype = ctypes.c_int
_user32.GetDC.restype = ctypes.c_void_p
_user32.GetDC.argtypes = [ctypes.c_void_p]
_user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.UpdateLayeredWindow.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_uint32,
    ctypes.POINTER(_BLENDFUNCTION),
    ctypes.c_uint32,
]


def enable_dpi_awareness():
    """声明 DPI 感知；否则分层位图会被系统按缩放比例拉伸变糊。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _dpi_scale():
    hdc = _user32.GetDC(None)
    try:
        dpi = _gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
    finally:
        _user32.ReleaseDC(None, hdc)
    return (dpi / 96.0) if dpi else 1.0


def _premultiplied_bgra(path, target_height):
    """读 PNG → 预乘 alpha 缩放 → BGRA 字节 + alpha 表。"""
    image = Image.open(path).convert("RGBa")  # RGBa = 预乘 alpha，缩放不会产生白边/黑边
    ratio = float(target_height) / image.height
    width = max(1, int(round(image.width * ratio)))
    image = image.resize((width, target_height), Image.LANCZOS).convert("RGBA")

    r, g, b, a = image.split()
    premultiplied = Image.merge(
        "RGBA",
        (
            ImageChops.multiply(r, a),
            ImageChops.multiply(g, a),
            ImageChops.multiply(b, a),
            a,
        ),
    )
    return premultiplied.tobytes("raw", "BGRA"), a.tobytes(), width, target_height


def _work_area():
    """主屏工作区（排除任务栏）。"""
    rect = _RECT()
    if _user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, 1280, 800


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class LayeredPet:
    """分层窗口桌宠；start() 在后台线程跑消息循环。"""

    def __init__(self, sprite_path=None, height=480):
        self.sprite_path = sprite_path or _DEFAULT_SPRITE
        self.height = height
        self.hwnd = None
        self._size = (0, 0)
        self._alpha = b""
        self._drag = None
        self._home = (0, 0)
        self._ready = threading.Event()

    # ---- 对外 ----

    def is_alive(self):
        return bool(self.hwnd and win32gui.IsWindow(self.hwnd))

    def start(self):
        thread = threading.Thread(target=self._run, name="kirara-layered-pet", daemon=True)
        thread.start()
        self._ready.wait(10)
        return thread

    def close(self):
        if self.hwnd:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)

    # ---- 内部 ----

    def _run(self):
        try:
            self._create()
        except Exception:
            import traceback

            traceback.print_exc()
            self._ready.set()
            return
        win32gui.PumpMessages()
        self.hwnd = None

    def _create(self):
        enable_dpi_awareness()
        target_height = int(round(self.height * _dpi_scale()))
        data, alpha, width, height = _premultiplied_bgra(self.sprite_path, target_height)
        self._size = (width, height)
        self._alpha = alpha

        work_x, work_y, work_w, work_h = _work_area()
        x = work_x + work_w - width - 40
        y = work_y + work_h - height - 20
        self._home = (x, y)

        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = _CLASS_NAME
        wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_HAND)
        wc.lpfnWndProc = {
            win32con.WM_DESTROY: self._on_destroy,
            win32con.WM_LBUTTONDOWN: self._on_lbutton_down,
            win32con.WM_MOUSEMOVE: self._on_mouse_move,
            win32con.WM_LBUTTONUP: self._on_lbutton_up,
            win32con.WM_RBUTTONUP: self._on_rbutton_up,
            win32con.WM_NCHITTEST: self._on_hit_test,
            win32con.WM_CAPTURECHANGED: self._on_capture_changed,
        }
        win32gui.RegisterClass(wc)

        ex_style = win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW
        self.hwnd = win32gui.CreateWindowEx(
            ex_style,
            _CLASS_NAME,
            "Kirara",
            win32con.WS_POPUP,
            x,
            y,
            width,
            height,
            0,
            0,
            wc.hInstance,
            None,
        )
        self._paint(data, width, height)
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNOACTIVATE)
        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            x,
            y,
            0,
            0,
            win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
        print("[pet] 工作区=%s 目标位置=(%d,%d) 实际=%s"
              % ((work_x, work_y, work_w, work_h), x, y, win32gui.GetWindowRect(self.hwnd)))
        self._ready.set()

    def _paint(self, data, width, height):
        """把预乘 BGRA 位图交给 UpdateLayeredWindow（ULW_ALPHA）。"""
        screen_dc = _user32.GetDC(None)
        mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # 负数 = 自上而下
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        bits = ctypes.c_void_p()
        dib = _gdi32.CreateDIBSection(
            mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0
        )
        ctypes.memmove(bits, data, len(data))
        old = _gdi32.SelectObject(mem_dc, dib)

        blend = _BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER / AC_SRC_ALPHA
        dst = (ctypes.c_int * 2)(0, 0)
        size = (ctypes.c_int * 2)(width, height)
        src = (ctypes.c_int * 2)(0, 0)
        _user32.UpdateLayeredWindow(
            self.hwnd,
            screen_dc,
            dst,
            size,
            mem_dc,
            src,
            0,
            ctypes.byref(blend),
            2,  # ULW_ALPHA
        )
        _gdi32.SelectObject(mem_dc, old)
        _gdi32.DeleteObject(dib)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(None, screen_dc)

    # ---- 消息处理 ----

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        self.hwnd = None
        win32gui.PostQuitMessage(0)
        return 0

    def _on_lbutton_down(self, hwnd, msg, wparam, lparam):
        x, y = win32gui.GetCursorPos()
        rect = win32gui.GetWindowRect(hwnd)
        self._drag = (x, y, rect[0], rect[1])
        win32gui.SetCapture(hwnd)
        return 0

    def _on_mouse_move(self, hwnd, msg, wparam, lparam):
        if not self._drag:
            return 0
        x, y = win32gui.GetCursorPos()
        start_x, start_y, win_x, win_y = self._drag
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            win_x + (x - start_x),
            win_y + (y - start_y),
            0,
            0,
            win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
        return 0

    def _on_lbutton_up(self, hwnd, msg, wparam, lparam):
        self._drag = None
        win32gui.ReleaseCapture()
        return 0

    def _on_capture_changed(self, hwnd, msg, wparam, lparam):
        self._drag = None
        return 0

    def _on_hit_test(self, hwnd, msg, wparam, lparam):
        """透明像素不挡点击，交给下层窗口。"""
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        client_x, client_y = win32gui.ScreenToClient(hwnd, (x, y))
        width, height = self._size
        if 0 <= client_x < width and 0 <= client_y < height:
            if self._alpha[client_y * width + client_x] > 8:
                return win32con.HTCLIENT
        return win32con.HTTRANSPARENT

    def _on_rbutton_up(self, hwnd, msg, wparam, lparam):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "归位")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "退出桌宠")
        x, y = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(hwnd)
        command = win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON,
            x,
            y,
            0,
            hwnd,
            None,
        )
        win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)
        if command == 1:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                self._home[0],
                self._home[1],
                0,
                0,
                win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
            )
        elif command == 2:
            win32gui.DestroyWindow(hwnd)
        return 0


if __name__ == "__main__":
    pet = LayeredPet()
    thread = pet.start()
    print("[pet] hwnd=%s size=%s，右键菜单可退出" % (pet.hwnd, pet._size))
    # 等窗口线程结束（窗口销毁后 PumpMessages 返回），主线程随之退出进程
    thread.join()