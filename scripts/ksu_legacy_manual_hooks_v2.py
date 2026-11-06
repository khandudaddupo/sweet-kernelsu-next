#!/usr/bin/env python3
"""Insert KernelSU-Next legacy manual hooks into the 4.14 kernel source.

v2 — matches the PROVEN working pattern from the earlier Vantom build:
  * kernel/reboot.c  -> ksu_handle_sys_reboot (supercall channel; required by Kbuild)
  * fs/exec.c        -> ONLY ksu_handle_execveat_sucompat with NULL argv/envp/flags
  * fs/open.c        -> ksu_handle_faccessat in SYSCALL_DEFINE3(faccessat)
  * fs/stat.c        -> ksu_handle_stat in SYSCALL_DEFINE4(newfstatat)
  * kernel/sys.c     -> ksu_handle_setresuid(ruid, euid) in SYSCALL_DEFINE3(setresuid)

REMOVED vs v1 (the bootloop suspects):
  * fs/read_write.c fops-proxy / init.rc injection hook  (v3.4.0-legacy
    ksu_handle_sys_read rewrites init.rc reads via an fops proxy — removed)
  * ksu_handle_execveat / ksu_handle_execveat_ksud stage-2 hook (removed)
Run from the kernel source root. Idempotent (KSU_LEGACY_MANUAL_HOOK2 marker).
"""
import re
import sys

def decl_tail(path, decl):
    """Insert `decl` right after the last #include line in path's content."""
    s = open(path).read()
    pos = s.rfind("#include")
    if pos < 0:
        return None
    e = s.find("\n", pos)
    if e < 0:
        e = len(s)
    return s[:e + 1] + decl + s[e + 1:]

HOOKS = [
    # 1. reboot — supercall channel (Kbuild greps ksu_handle_sys_reboot here)
    {
        "file": "kernel/reboot.c",
        "decl": "extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg);\n",
        "matches": r"SYSCALL_DEFINE4\(reboot, int, magic1, int, magic2, unsigned int, cmd,",
    },
    # 2. exec — ONLY sucompat, NULL (argv, envp, flags) — PROVEN pattern
    {
        "file": "fs/exec.c",
        "decl": "extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr, void *argv, void *envp, int *flags);\n",
        "matches": r"static int do_execveat_common\((?:int )?(?:fd|dfd), struct filename \*filename,",
    },
    # 3. faccessat
    {
        "file": "fs/open.c",
        "decl": "extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode, int *flags);\n",
        "matches": r"SYSCALL_DEFINE3\(faccessat, int, dfd, const char __user \*, filename, int, mode\)",
    },
    # 4. stat
    {
        "file": "fs/stat.c",
        "decl": "extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);\n",
        "matches": r"SYSCALL_DEFINE4\(newfstatat, int, dfd, const char __user \*, filename,",
    },
    # 5. setresuid (root-grant path)
    {
        "file": "kernel/sys.c",
        "decl": "extern int ksu_handle_setresuid(uid_t old_uid, uid_t new_uid);\n",
        "matches": r"SYSCALL_DEFINE3\(setresuid, uid_t, ruid, uid_t, euid, uid_t, suid\)",
    },
]

CALLS = {
    "kernel/reboot.c": "\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);\n",
    "fs/exec.c": "\tksu_handle_execveat_sucompat(&fd, &filename, NULL, NULL, NULL);\n",
    "fs/open.c": "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n",
    "fs/stat.c": "\tksu_handle_stat(&dfd, &filename, &flag);\n",
    "kernel/sys.c": "\tksu_handle_setresuid(ruid, euid);\n",
}

# Clean up v1 leftovers if the v1 script ever ran on this tree
V1_MARKER_FILES = ["fs/read_write.c"]
V1_FUNC_BLOCK = re.compile(
    r"#ifdef CONFIG_KSU\nextern bool ksu_vfs_read_hook __read_mostly;\n"
    r"extern void ksu_handle_sys_read\(unsigned int fd\);\n#endif\n")

MARK = "/* KSU_LEGACY_MANUAL_HOOK2 */"

def clean_v1():
    for f in V1_MARKER_FILES:
        try:
            src = open(f).read()
        except FileNotFoundError:
            continue
        if "KSU_LEGACY_MANUAL_HOOK" in src:
            print(f"[v1] leftover patch found in {f} — leaving file untouched (hook script removed it automatically only by full checkout)")

def process(h):
    path = h["file"]
    try:
        s = open(path).read()
    except FileNotFoundError:
        return f"{path}: file not found"
    if MARK in s:
        print(f"[skip] {path}: already patched (v2)")
        return None
    m = re.search(h["matches"], s)
    if not m:
        return f"{path}: function signature not found"
    brace = s.find("{", m.end())
    if brace < 0:
        return f"{path}: opening brace not found"
    decl = h["decl"]
    new = s[:m.start()] + decl + s[m.start():brace + 1] + "\n" + MARK + "\n" + CALLS[path] + s[brace + 1:]
    open(path, "w").write(new)
    print(f"[ok]   {path}")
    return None

def main():
    clean_v1()
    failures = []
    for h in HOOKS:
        err = process(h)
        if err:
            failures.append(err)
    if failures:
        print("MANUAL HOOK PATCH v2 FAILED:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("all v2 legacy KSU manual hooks inserted (PROVEN pattern)")

if __name__ == "__main__":
    main()
