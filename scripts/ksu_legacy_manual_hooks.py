#!/usr/bin/env python3
"""Insert KernelSU-Next legacy manual hooks into the 4.14 kernel source.

Based on the official KernelSU-Next "integrate for non-GKI" manual hook guide,
adapted to the v3.4.0-legacy driver API surface (which is what Kbuild checks
when CONFIG_KSU_MANUAL_HOOK=y). Run from the kernel source root. Idempotent.
Exits non-zero if any hook site is not found.
"""
import re
import sys

HOOKS = [
    {
        "file": "fs/exec.c",
        "func": r"static int do_execveat_common\(int fd, struct filename \*filename,",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,\n"
            "\t\t\t\tvoid *argv, void *envp, int *flags);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);\n"
            "#endif\n"
        ),
    },
    {
        "file": "fs/open.c",
        "func": r"SYSCALL_DEFINE3\(faccessat, int, dfd, const char __user \*, filename, int, mode\)",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,\n"
            "\t\t\t\tint *mode, int *flags);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n"
            "#endif\n"
        ),
    },
    {
        "file": "fs/stat.c",
        "func": r"SYSCALL_DEFINE4\(newfstatat, int, dfd, const char __user \*, filename,\n"
        r"\t+struct stat __user \*, statbuf, int, flag\)",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern int ksu_handle_stat(int *dfd, const char __user **filename_user,\n"
            "\t\t\t   int *flags);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tksu_handle_stat(&dfd, &filename, &flag);\n"
            "#endif\n"
        ),
    },
    {
        "file": "fs/read_write.c",
        "func": r"SYSCALL_DEFINE3\(read, unsigned int, fd, char __user \*, buf, size_t, count\)",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern bool ksu_vfs_read_hook __read_mostly;\n"
            "extern void ksu_handle_sys_read(unsigned int fd);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tif (unlikely(ksu_vfs_read_hook))\n"
            "\t\tksu_handle_sys_read(fd);\n"
            "#endif\n"
        ),
    },
    {
        "file": "kernel/reboot.c",
        "func": r"SYSCALL_DEFINE4\(reboot, int, magic1, int, magic2, unsigned int, cmd,\n"
        r"\t+void __user \*, arg\)",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd,\n"
            "\t\t\t\t void __user **arg);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);\n"
            "#endif\n"
        ),
    },
]

MARK = "/* KSU_LEGACY_MANUAL_HOOK */"
failed = []
patched = []
for h in HOOKS:
    path = h["file"]
    try:
        src = open(path).read()
    except FileNotFoundError:
        failed.append(f"{path}: file not found")
        continue
    if MARK in src:
        print(f"[skip] {path}: already patched")
        patched.append(path)
        continue
    m = re.search(h["func"], src)
    if not m:
        failed.append(f"{path}: function signature not found")
        continue
    brace = src.find("{", m.end())
    if brace < 0:
        failed.append(f"{path}: opening brace not found")
        continue
    src = (src[:m.start()] + h["decl"] + src[m.start():brace + 1]
           + "\n" + MARK + "\n" + h["body"] + src[brace + 1:])
    open(path, "w").write(src)
    patched.append(path)
    print(f"[ok]   {path}")

if failed:
    print("MANUAL HOOK PATCH FAILED:\n  " + "\n  ".join(failed))
    sys.exit(1)
print("all legacy KSU manual hooks inserted")
