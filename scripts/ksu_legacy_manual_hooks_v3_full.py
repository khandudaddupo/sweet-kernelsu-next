#!/usr/bin/env python3
"""Insert KernelSU-Next legacy manual hooks into the 4.14 kernel source.

v3 — FULL OFFICIAL FLOW (replicates the PROVEN September Vantom full-hook set,
which booted this exact phone on MIUI 14 with v3.2.0-legacy):
  * kernel/reboot.c   -> ksu_handle_sys_reboot (supercall channel; Kbuild-required)
  * fs/exec.c         -> ksu_handle_execveat_ksud  (init second-stage SELinux rules +
                          zygote detection — feeds the RC/ksud boot chain)
                        + ksu_handle_execveat_sucompat (su->root grant hook)
  * fs/read_write.c   -> ksu_handle_sys_read (init.rc fops proxy -> injects the
                          KernelSU RC that starts /data/adb/ksu/bin/ksud at boot)
  * fs/open.c         -> ksu_handle_faccessat in SYSCALL_DEFINE3(faccessat)
  * fs/stat.c         -> ksu_handle_stat in SYSCALL_DEFINE4(newfstatat)
  * kernel/sys.c      -> ksu_handle_setresuid in SYSCALL_DEFINE3(setresuid)

The earlier bootloops traced to the BUILD PIPELINE (MiCode source), not to these
hooks: BOTH v1 (full hooks) and v2 (partial hooks) looped on the MiCode pipeline,
while v2 boots on the proven PixelOS pipeline. This phone's proven September build
used the FULL hook set.
Run from the kernel source root. Idempotent (KSU_LEGACY_MANUAL_HOOK3 marker).
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

EXEC_DECL = (
    "extern int ksu_handle_execveat_ksud(int *fd, struct filename **filename_ptr, "
    "struct user_arg_ptr *argv, struct user_arg_ptr *envp, int *flags);\n"
    "extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr, "
    "void *argv, void *envp, int *flags);\n"
)

HOOKS = [
    # 1. reboot — supercall channel (Kbuild greps ksu_handle_sys_reboot here)
    {
        "file": "kernel/reboot.c",
        "decl": "extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg);\n",
        "matches": r"SYSCALL_DEFINE4\(reboot, int, magic1, int, magic2, unsigned int, cmd,",
    },
    # 2. exec — FULL flow: ksud stage-2 handler + sucompat
    {
        "file": "fs/exec.c",
        "decl": EXEC_DECL,
        "matches": r"static int do_execveat_common\((?:int )?(?:fd|dfd), struct filename \*filename,",
    },
    # 3. read — init.rc fops proxy (RC injection feeding ksud)
    {
        "file": "fs/read_write.c",
        "decl": "extern void ksu_handle_sys_read(unsigned int fd);\n",
        "matches": r"SYSCALL_DEFINE3\(read, unsigned int, fd, char __user \*, buf, size_t, count\)",
    },
    # 4. faccessat
    {
        "file": "fs/open.c",
        "decl": "extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode, int *flags);\n",
        "matches": r"SYSCALL_DEFINE3\(faccessat, int, dfd, const char __user \*, filename, int, mode\)",
    },
    # 5. stat
    {
        "file": "fs/stat.c",
        "decl": "extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);\n",
        "matches": r"SYSCALL_DEFINE4\(newfstatat, int, dfd, const char __user \*, filename,",
    },
    # 6. setresuid (root-grant path)
    {
        "file": "kernel/sys.c",
        "decl": "extern int ksu_handle_setresuid(uid_t old_uid, uid_t new_uid);\n",
        "matches": r"SYSCALL_DEFINE3\(setresuid, uid_t, ruid, uid_t, euid, uid_t, suid\)",
    },
]

CALLS = {
    "kernel/reboot.c": "\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);\n",
    "fs/exec.c":
        "\tksu_handle_execveat_ksud(&fd, &filename, &argv, &envp, &flags);\n"
        "\tksu_handle_execveat_sucompat(&fd, &filename, NULL, NULL, NULL);\n",
    "fs/read_write.c": "\tksu_handle_sys_read(fd);\n",
    "fs/open.c": "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n",
    "fs/stat.c": "\tksu_handle_stat(&dfd, &filename, &flag);\n",
    "kernel/sys.c": "\tksu_handle_setresuid(ruid, euid);\n",
}

MARK = "/* KSU_LEGACY_MANUAL_HOOK3 */"

# extra anchors for trees whose structure differs (e.g. PixelOS 4.14.357)
HOOK_FALLBACKS = {
    "fs/exec.c": [
        HOOKS[1]["matches"],
        r"static int __do_execve_file\((?:int )?(?:fd|dfd), struct filename \*filename,",
        r"int do_execveat_common\((?:int )?(?:fd|dfd), struct filename \*filename,",
    ],
    "fs/open.c": [
        HOOKS[3]["matches"],
        r"int do_faccessat\((?:int )?(?:dfd|dirfd), const char __user \*filename, int mode",
    ],
    "kernel/sys.c": [
        HOOKS[5]["matches"],
        r"long __sys_setresuid\((?:uid_t )?ruid, (?:uid_t )?euid, (?:uid_t )?suid\)",
    ],
    "fs/read_write.c": [
        HOOKS[2]["matches"],
        r"SYSCALL_DEFINE\(read, unsigned int, fd, char __user \*, buf, size_t, count\)",
    ],
}

def process(h):
    path = h["file"]
    try:
        s = open(path).read()
    except FileNotFoundError:
        return f"{path}: file not found"
    if MARK in s:
        print(f"[skip] {path}: already patched (v3)")
        return None
    m = None
    for pat in HOOK_FALLBACKS.get(path, [h["matches"]]):
        m = re.search(pat, s)
        if m:
            break
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
    failures = []
    for h in HOOKS:
        err = process(h)
        if err:
            failures.append(err)
    if failures:
        print("MANUAL HOOK PATCH v3 FAILED:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("all v3 legacy KSU manual hooks inserted (FULL proven pattern)")

if __name__ == "__main__":
    main()
