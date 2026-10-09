#!/usr/bin/env python3
"""Insert KernelSU-Next v1.0.9 manual hooks into MiCode sweet-r-oss (4.14).

Used instead of kprobes: stock MIUI kernel has CONFIG_KPROBES off, and enabling it
changes struct module, which breaks loading of the stock vendor .ko modules.
Run from the kernel source root. Exits non-zero if any hook site is not found.
"""
import re
import sys

HOOKS = [
    {
        "file": "fs/exec.c",
        "func": r"static int do_execveat_common\(int fd, struct filename \*filename,",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern bool ksu_execveat_hook __read_mostly;\n"
            "extern int ksu_handle_execveat_ksud(int *fd, struct filename **filename_ptr,\n"
            "\t\t\t\t    struct user_arg_ptr *argv, struct user_arg_ptr *envp, int *flags);\n"
            "extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,\n"
            "\t\t\t\t\tvoid *argv, void *envp, int *flags);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tif (unlikely(ksu_execveat_hook))\n"
            "\t\tksu_handle_execveat_ksud(&fd, &filename, &argv, &envp, &flags);\n"
            "\tksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);\n"
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
        "func": r"int vfs_statx\(int dfd, const char __user \*filename, int flags,",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tksu_handle_stat(&dfd, &filename, &flags);\n"
            "#endif\n"
        ),
    },
    {
        "file": "fs/read_write.c",
        "func": r"ssize_t vfs_read\(struct file \*file, char __user \*buf, size_t count, loff_t \*pos\)",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern bool ksu_vfs_read_hook __read_mostly;\n"
            "extern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,\n"
            "\t\t\t       size_t *count_ptr, loff_t **pos);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tif (unlikely(ksu_vfs_read_hook))\n"
            "\t\tksu_handle_vfs_read(&file, &buf, &count, &pos);\n"
            "#endif\n"
        ),
    },
    {
        "file": "drivers/input/input.c",
        "func": r"static void input_handle_event\(struct input_dev \*dev,",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern bool ksu_input_hook __read_mostly;\n"
            "extern int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code,\n"
            "\t\t\t\t\t int *value);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tif (unlikely(ksu_input_hook))\n"
            "\t\tksu_handle_input_handle_event(&type, &code, &value);\n"
            "#endif\n"
        ),
    },
    {
        "file": "fs/devpts/inode.c",
        "func": r"void \*devpts_get_priv\(struct dentry \*dentry\)",
        "decl": (
            "#ifdef CONFIG_KSU\n"
            "extern int ksu_handle_devpts(struct inode *inode);\n"
            "#endif\n"
        ),
        "body": (
            "#ifdef CONFIG_KSU\n"
            "\tksu_handle_devpts(dentry->d_inode);\n"
            "#endif\n"
        ),
    },
]

MARK = "/* KSU_V109_MANUAL_HOOK */"
failed = []
for h in HOOKS:
    path = h["file"]
    src = open(path).read()
    if MARK in src:
        print(f"[skip] {path}: already patched")
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
    print(f"[ok]   {path}")

if failed:
    print("MANUAL HOOK PATCH FAILED:\n  " + "\n  ".join(failed))
    sys.exit(1)
print("all 6 KSU manual hooks inserted")
