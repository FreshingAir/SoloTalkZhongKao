# -*- coding: utf-8 -*-
"""运行环境与资源路径。

本模块在 **导入时** 就完成一次性的进程级准备工作：

1. 注册 DLL 搜索目录（onnxruntime 等）；
2. 把 stdout / stderr 复制一份写入诊断日志；
3. 安装全局异常钩子与 faulthandler；
4. 打印启动横幅；
5. 把工作目录切到程序根目录（保证 recordings/ history/ 等相对目录稳定）。

因此它应当是程序中最先被导入的模块，其它模块直接从本模块 import 路径常量即可。
"""

import os
import sys
import ctypes
import datetime
import threading

# ========== 路径 & DLL 注册 ==========
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
    if hasattr(sys, "_MEIPASS"):
        _BASE_DIR = sys._MEIPASS
    if os.path.basename(_BASE_DIR) == "_internal":
        _BASE_DIR = os.path.dirname(_BASE_DIR)
else:
    # 源码运行：本包位于项目根目录下，故根目录 = 包目录的上一级
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = _BASE_DIR
SCRIPT_DIR = _BASE_DIR
INTERNAL_DIR = os.path.join(_BASE_DIR, "_internal")

if sys.platform == "win32":
    try:
        ctypes.windll.kernel32.AddDllDirectory(SCRIPT_DIR)
    except Exception:
        pass
    if getattr(sys, "frozen", False) and os.path.isdir(INTERNAL_DIR):
        try:
            ctypes.windll.kernel32.AddDllDirectory(INTERNAL_DIR)
        except Exception:
            pass
        _ort_dll_dir = os.path.join(INTERNAL_DIR, "onnxruntime", "capi")
        if os.path.isdir(_ort_dll_dir):
            try:
                ctypes.windll.kernel32.AddDllDirectory(_ort_dll_dir)
            except Exception:
                pass


# ========== 诊断日志 ==========
def _pick_log_path():
    if not getattr(sys, "frozen", False):
        return os.path.join(SCRIPT_DIR, "_solo_diag.log")
    exe_log = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_solo_diag.log")
    try:
        with open(exe_log, "a", encoding="utf-8"):
            pass
        return exe_log
    except Exception:
        return os.path.join(os.path.expanduser("~"), "_solo_diag.log")


DIAG_LOG_PATH = _pick_log_path()


class _ConsoleTee:
    """把控制台输出按行旁路写入诊断日志的流包装器。"""

    def __init__(self, stream, log_path, is_error=False):
        self._stream = stream
        self._log_path = log_path
        self._is_error = is_error
        self._buf = []
        self._lock = threading.Lock()

    def write(self, data):
        if not data:
            return
        try:
            if self._stream is not None:
                self._stream.write(data)
                self._stream.flush()
        except Exception:
            pass
        with self._lock:
            self._buf.append(data)
            joined = "".join(self._buf)
            parts = joined.split("\n")
            self._buf = [parts[-1]] if parts[-1] else []
            for line in parts[:-1]:
                self._flush_line(line)

    def flush(self):
        try:
            if self._stream is not None:
                self._stream.flush()
        except Exception:
            pass

    def _flush_line(self, line):
        if not line:
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = "STDERR" if self._is_error else "OUT"
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}][{tag}] {line}\n")
        except Exception:
            pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")

    def fileno(self):
        return -1

    def writable(self):
        return True


def install_console_tee():
    sys.stdout = _ConsoleTee(sys.stdout, DIAG_LOG_PATH)
    sys.stderr = _ConsoleTee(sys.stderr, DIAG_LOG_PATH, is_error=True)


# ========== 全局异常钩子 ==========
def log_exception(exc_type, exc_value, exc_tb):
    try:
        import traceback
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        tb_text = f"{exc_type}: {exc_value}"
    msg = f"\n[EXCEPTION] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{tb_text}"
    try:
        with open(DIAG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    if exc_type is not SystemExit:
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass


def install_exception_hook():
    sys.excepthook = log_exception


def install_faulthandler():
    try:
        import faulthandler
        _fh_path = (os.path.join(os.path.expanduser("~"), "_solo_diag.log")
                    if getattr(sys, "frozen", False)
                    else os.path.join(SCRIPT_DIR, "_solo_diag.log"))
        _fh_file = open(_fh_path, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_fh_file, all_threads=True)
    except Exception:
        pass


# ========== 资源定位 ==========
def resolve_model_dir(name):
    """在 根目录 / _internal / 当前工作目录 中查找模型目录。"""
    for base in (BASE_DIR, INTERNAL_DIR, os.getcwd()):
        p = os.path.join(base, name)
        if os.path.isdir(p):
            return p
    return os.path.join(BASE_DIR, name)


def resolve_resource_file(name):
    """在 根目录 / _internal / 当前工作目录 中查找单个资源文件，找不到返回 None。"""
    for base in (BASE_DIR, INTERNAL_DIR, os.getcwd()):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    return None


def chdir_to_script_dir():
    if os.getcwd() != SCRIPT_DIR:
        try:
            os.chdir(SCRIPT_DIR)
        except Exception:
            pass


def log_startup_banner():
    print("=== SoloTalk 中考版 startup ===")
    print(f"log_path={DIAG_LOG_PATH}")
    print(f"frozen={getattr(sys, 'frozen', False)}")
    print(f"BASE_DIR={BASE_DIR}")


# 导入本模块即完成环境准备（顺序与重构前保持一致）
install_console_tee()
install_exception_hook()
install_faulthandler()
log_startup_banner()
chdir_to_script_dir()
