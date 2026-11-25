"""按 MOD 的 desktop.pet.entry 声明拉起桌宠子进程（最小实现）。

只做三件事：扫描已启用 MOD 的声明、在 Web 服务就绪后拉起、宿主退出时收掉。
不做托盘、不写偏好、不做开关、不守护重启、不做单实例窗口复用；
桌宠进程自己退出或崩溃都不会被再次拉起。

生命周期绑定：Windows 下把桌宠挂进一个 KILL_ON_JOB_CLOSE 的 Job Object，
宿主进程无论正常退出、走 os._exit 还是被 TerminateProcess，句柄一关内核就会
把桌宠一起收掉，不依赖 Python 的 finally / atexit。
"""

import atexit
import os
import subprocess
import sys
import threading
import time

_PROCS = []
_LOCK = threading.Lock()
_LAUNCHED = False
_STOPPED = False

# ---------------- 宿主生命周期绑定 ----------------

_JOB = None              # (kernel32, handle)，进程存活期间一直持有，绝不主动关闭
_JOB_FAILED = False
_JOB_WARNED = False

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _job_structs():
    import ctypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    return ctypes, JOBOBJECT_EXTENDED_LIMIT_INFORMATION


def _ensure_job():
    """创建并持有 KILL_ON_JOB_CLOSE 的 Job；失败返回 None（退回主动收尾）。"""
    global _JOB, _JOB_FAILED
    if os.name != "nt" or _JOB is not None or _JOB_FAILED:
        return _JOB
    try:
        ctypes, extended_info = _job_structs()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = extended_info()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject.restype = ctypes.c_int
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32
        ]
        ok = kernel32.SetInformationJobObject(
            ctypes.c_void_p(handle),
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        _JOB = (kernel32, handle)
    except Exception as error:
        _JOB_FAILED = True
        _JOB = None
        print("[SimChat] 桌宠生命周期作业创建失败，退回宿主退出时主动收尾：%s" % error)
    return _JOB


def _bind_to_job(proc):
    """把刚拉起的桌宠挂进宿主的 Job；失败只记一次日志，不影响拉起。"""
    global _JOB_WARNED
    if os.name != "nt":
        return False
    job = _ensure_job()
    if not job:
        return False
    kernel32, handle = job
    try:
        import ctypes

        kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        ok = kernel32.AssignProcessToJobObject(
            ctypes.c_void_p(handle), ctypes.c_void_p(int(proc._handle))
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return True
    except Exception as error:
        if not _JOB_WARNED:
            _JOB_WARNED = True
            print("[SimChat] 桌宠未能加入宿主生命周期作业：%s" % error)
        return False


def _resolve_script(package_dir, rel_path):
    """把包内相对路径解析成真实文件；越界或不存在返回 None。"""
    base = os.path.realpath(package_dir)
    target = os.path.realpath(os.path.join(base, rel_path))
    try:
        inside = os.path.commonpath([target, base]) == base
    except ValueError:
        return None
    if not inside or not os.path.isfile(target):
        return None
    return target


def discover(mods_dir=None):
    """返回 [(mod_id, script_path, package_dir)]，只取已启用且声明有效的条目。"""
    from simchat.runtime import mods_index

    found = []
    for item in mods_index.scan(mods_dir):
        if not item.get("enabled") or item.get("status") == "err":
            continue
        desktop = item.get("desktop") or {}
        pet = desktop.get("pet") or {}
        entry = pet.get("entry")
        if not isinstance(entry, str) or not entry:
            continue
        script = _resolve_script(item["path"], entry)
        if script:
            found.append((item.get("id"), script, item["path"]))
    return found


def _spawn(script, package_dir):
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW：不弹控制台
    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=package_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs
    )
    _bind_to_job(proc)
    return proc


def launch_enabled(mods_dir=None):
    """为每个声明了 desktop.pet.entry 的已启用 MOD 拉起一个子进程。

    每个宿主进程只执行一次；重复调用返回空列表。
    """
    global _LAUNCHED
    with _LOCK:
        if _LAUNCHED:
            return []
        _LAUNCHED = True

    launched = []
    for mod_id, script, package_dir in discover(mods_dir):
        with _LOCK:
            if _STOPPED:
                break
        try:
            proc = _spawn(script, package_dir)
        except Exception as error:
            print("[SimChat] 桌宠启动失败（%s）：%s" % (mod_id, error))
            continue
        with _LOCK:
            if _STOPPED:
                # 服务恰好在拉起过程中退出：立刻收掉，避免竞态留下孤儿
                proc.terminate()
                break
            _PROCS.append(proc)
        launched.append((mod_id, proc))
    if launched:
        atexit.register(stop_all)
    return launched


def stop_all():
    """终止本轮拉起的全部桌宠进程；可重复调用。"""
    global _STOPPED
    with _LOCK:
        _STOPPED = True
        procs = list(_PROCS)
        _PROCS.clear()
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    deadline = time.monotonic() + 3.0
    for proc in procs:
        try:
            proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
