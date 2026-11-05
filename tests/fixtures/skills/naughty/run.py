import time


def run(inputs, ctx):
    mode = inputs["mode"]
    if mode == "network":
        import socket

        socket.create_connection(("example.com", 80), timeout=2)
    elif mode == "subprocess":
        import subprocess

        subprocess.run(
            ["cmd", "/c", "echo", "hi"] if __import__("os").name == "nt" else ["echo", "hi"], check=True
        )
    elif mode == "write-outside":
        with open(inputs["target"], "w", encoding="utf-8") as fh:
            fh.write("should never be written")
    elif mode == "read-outside":
        with open(inputs["target"], encoding="utf-8") as fh:
            fh.read()
    elif mode == "sleep":
        time.sleep(120)
    elif mode == "memory":
        hog = []
        while True:
            hog.append(bytearray(64 * 1024 * 1024))
    elif mode == "sqlite-outside":
        import sqlite3

        sqlite3.connect(inputs["target"]).close()
    elif mode == "sqlite-read-outside":
        import sqlite3

        sqlite3.connect(f"file:{inputs['target']}?mode=ro", uri=True).close()
    elif mode == "sqlite-extension":
        import sqlite3

        sqlite3.connect(":memory:").enable_load_extension(True)
    elif mode == "sqlite-inside":
        import os
        import sqlite3

        for database in (":memory:", os.path.join(ctx.output_dir, "scratch.sqlite")):
            con = sqlite3.connect(database)
            con.execute("create table t (x)")
            con.close()
    elif mode == "xattr-outside":
        import os

        os.setxattr(inputs["target"], "user.atlas", b"x")
    elif mode == "large-output":
        # Small while running; converting and serializing the result is the peak.
        return {"done": True, "padding": [0] * inputs["count"]}
    elif mode == "allocate":
        # Touch every page: zero-filled allocations may never become resident.
        block = bytearray(inputs["megabytes"] * 1024 * 1024)
        block[::4096] = b"\x01" * len(block[::4096])
        return {"done": bool(block[0])}
    elif mode == "native-subprocess":
        # Bypasses the audit hooks entirely; only the OS process limit can stop it.
        import ctypes
        from ctypes import wintypes

        class STARTUPINFO(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        si, pi = STARTUPINFO(), PROCESS_INFORMATION()
        si.cb = ctypes.sizeof(si)
        cmdline = ctypes.create_unicode_buffer("cmd.exe /c exit 0")
        created = kernel32.CreateProcessW(
            None, cmdline, None, None, False, 0x08000000, None, None, ctypes.byref(si), ctypes.byref(pi)
        )
        if created:
            kernel32.TerminateProcess(pi.hProcess, 1)
            raise RuntimeError("ESCAPED: a native child process was created")
        return {"done": True, "blocked_error": ctypes.get_last_error()}
    return {"done": True}
