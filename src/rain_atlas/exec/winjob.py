"""Windows Job Objects: memory cap, process-count cap and whole-tree kill.

The child is created suspended, assigned to the job, then resumed, so no
instruction of the skill ever runs outside the job's limits.
"""

from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll")
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_kernel32.QueryInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
_ntdll.NtResumeProcess.restype = ctypes.c_long


def _check(ok: int, what: str) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error(), what)


class Job:
    def __init__(self, *, memory_mb: int, max_processes: int | None):
        self.handle = _kernel32.CreateJobObjectW(None, None)
        _check(self.handle, "CreateJobObjectW")
        info = _ExtendedLimits()
        flags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_JOB_MEMORY
            | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        )
        if max_processes is not None:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.ActiveProcessLimit = max_processes
        info.BasicLimitInformation.LimitFlags = flags
        info.JobMemoryLimit = memory_mb * 1024 * 1024
        _check(
            _kernel32.SetInformationJobObject(
                self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS, ctypes.byref(info), ctypes.sizeof(info)
            ),
            "SetInformationJobObject",
        )

    def start(self, args: list[str], **popen_kwargs) -> subprocess.Popen:
        """Start *args* suspended, assign it to the job, then resume it."""

        flags = popen_kwargs.pop("creationflags", 0) | CREATE_SUSPENDED | CREATE_NO_WINDOW
        proc = subprocess.Popen(args, creationflags=flags, **popen_kwargs)
        try:
            _check(_kernel32.AssignProcessToJobObject(self.handle, int(proc._handle)), "AssignProcessToJobObject")
            status = _ntdll.NtResumeProcess(int(proc._handle))
            if status != 0:
                raise OSError(f"NtResumeProcess failed with status {status:#x}")
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        return proc

    def peak_memory_mb(self) -> float | None:
        info = _ExtendedLimits()
        ok = _kernel32.QueryInformationJobObject(
            self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS, ctypes.byref(info), ctypes.sizeof(info), None
        )
        return info.PeakJobMemoryUsed / (1024 * 1024) if ok else None

    def kill(self) -> None:
        _kernel32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None
