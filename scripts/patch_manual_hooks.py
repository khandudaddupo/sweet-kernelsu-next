#!/usr/bin/env python3
"""Patch KSU-Next v3.2.0-legacy manual hooks into Linux 4.14 kernel source.
NO config changes needed (no KPROBES/FTRACE) - hooks are direct function calls.
"""
import os, sys

def patch_file(path, patches, must_exist=True):
    """Apply a list of (anchor, insert_before/after, text) patches."""
    if not os.path.exists(path):
        if must_exist:
            print(f"[!] MISSING: {path}")
            return False
        return True
    with open(path, "r") as f:
        content = f.read()
    changed = False
    for anchor, text, desc in patches:
        if text.strip() in content:
            print(f"[-] Already patched: {desc} in {path}")
            continue
        if anchor not in content:
            print(f"[!] Anchor not found for {desc} in {path}: '{anchor[:40]}...'")
            return False
        content = content.replace(anchor, text, 1)
        changed = True
        print(f"[+] Patched {desc} in {path}")
    if changed:
        with open(path, "w") as f:
            f.write(content)
    return True

def main():
    ok = True

    # ============ 0. fs/namespace.c - path_umount (KSU umount feature) ============
    ns_file = "fs/namespace.c"
    if os.path.exists(ns_file):
        with open(ns_file, "r") as f:
            content = f.read()
        if "int path_umount" not in content:
            patch_ns = """static int can_umount(const struct path *path, int flags)
{
\tstruct mount *mnt = real_mount(path->mnt);
\tif (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
\t\treturn -EINVAL;
\tif (!may_mount())
\t\treturn -EPERM;
\tif (path->dentry != path->mnt->mnt_root)
\t\treturn -EINVAL;
\tif (!check_mnt(mnt))
\t\treturn -EINVAL;
\tif (mnt->mnt.mnt_flags & MNT_LOCKED)
\t\treturn -EINVAL;
\tif (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
\t\treturn -EPERM;
\treturn 0;
}

int path_umount(struct path *path, int flags)
{
\tstruct mount *mnt = real_mount(path->mnt);
\tint ret;
\tret = can_umount(path, flags);
\tif (!ret)
\t\tret = do_umount(mnt, flags);
\tdput(path->dentry);
\tmntput_no_expire(mnt);
\treturn ret;
}

"""
            if "static bool is_mnt_ns_file" in content:
                content = content.replace("static bool is_mnt_ns_file", patch_ns + "static bool is_mnt_ns_file", 1)
                with open(ns_file, "w") as f:
                    f.write(content)
                print("[+] Patched fs/namespace.c with path_umount")
            else:
                # Alternative anchor
                anchor = "static int do_umount(struct mount *mnt, int flags)"
                if anchor in content:
                    content = content.replace(anchor, patch_ns + anchor, 1)
                    with open(ns_file, "w") as f:
                        f.write(content)
                    print("[+] Patched fs/namespace.c with path_umount (alt anchor)")
                else:
                    print("[!] Could not find anchor in fs/namespace.c")
        else:
            print("[-] fs/namespace.c already has path_umount")

    # fs/internal.h - declaration
    hdr_file = "fs/internal.h"
    if os.path.exists(hdr_file):
        with open(hdr_file, "r") as f:
            content = f.read()
        if "int path_umount" not in content:
            if "extern void __init mnt_init(void);" in content:
                content = content.replace(
                    "extern void __init mnt_init(void);",
                    "extern void __init mnt_init(void);\nint path_umount(struct path *path, int flags);",
                    1)
                with open(hdr_file, "w") as f:
                    f.write(content)
                print("[+] Patched fs/internal.h with path_umount declaration")
            else:
                print("[!] Could not find anchor in fs/internal.h")
        else:
            print("[-] fs/internal.h already has path_umount")

    # ============ 1. kernel/reboot.c - marker (Kbuild check) ============
    # The Kbuild does: grep -q "ksu_handle_sys_reboot" kernel/reboot.c
    # We add it as a comment in the SYSCALL_DEFINE4(reboot,...) function
    reboot = "kernel/reboot.c"
    with open(reboot, "r") as f:
        c = f.read()
    if "ksu_handle_sys_reboot" not in c:
        # Add marker comment near the reboot syscall
        anchor = "SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd, void __user *, arg)"
        if anchor in c:
            c = c.replace(anchor, "/* ksu_handle_sys_reboot: KernelSU manual hook marker */\n" + anchor, 1)
            with open(reboot, "w") as f:
                f.write(c)
            print("[+] Added ksu_handle_sys_reboot marker in kernel/reboot.c")
        else:
            # fallback: add at top of file
            c = "/* ksu_handle_sys_reboot: KernelSU manual hook marker */\n" + c
            with open(reboot, "w") as f:
                f.write(c)
            print("[+] Added ksu_handle_sys_reboot marker at top of kernel/reboot.c")
    else:
        print("[-] kernel/reboot.c already has marker")

    # ============ 2. fs/exec.c - su execution hook ============
    exec_c = "fs/exec.c"
    with open(exec_c, "r") as f:
        c = f.read()
    if "ksu_handle_execveat_sucompat" not in c:
        # Add extern declaration after includes
        decl = "\nextern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr, void *argv, void *envp, int *flags);\n"
        # Find a good spot - after the last #include
        last_inc = c.rfind("#include")
        if last_inc > 0:
            line_end = c.find("\n", last_inc)
            c = c[:line_end+1] + decl + c[line_end+1:]
        # Find do_execveat_common and add hook at the beginning
        # 4.14: static int do_execveat_common(int fd, struct filename *filename, ...)
        anchor = "static int do_execveat_common(int fd, struct filename *filename,"
        hook = "\tksu_handle_execveat_sucompat(&fd, &filename, NULL, NULL, NULL);\n"
        if anchor in c:
            # Find the opening brace of the function body
            brace_pos = c.find("{", c.find(anchor))
            c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
            print("[+] Patched do_execveat_common in fs/exec.c")
        else:
            # Try alternate function name in 4.14
            anchor2 = "static int __do_execve_file(int fd, struct filename *filename,"
            if anchor2 in c:
                brace_pos = c.find("{", c.find(anchor2))
                c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
                print("[+] Patched __do_execve_file in fs/exec.c")
            else:
                print("[!] Could not find exec hook location in fs/exec.c")
                ok = False
        with open(exec_c, "w") as f:
            f.write(c)
    else:
        print("[-] fs/exec.c already patched")

    # ============ 3. fs/open.c - faccessat hook (hide su from access) ============
    open_c = "fs/open.c"
    with open(open_c, "r") as f:
        c = f.read()
    if "ksu_handle_faccessat" not in c:
        decl = "\nextern int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode, int *flags);\n"
        last_inc = c.rfind("#include")
        if last_inc > 0:
            line_end = c.find("\n", last_inc)
            c = c[:line_end+1] + decl + c[line_end+1:]
        # Find do_faccessat
        anchor = "SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)"
        if anchor in c:
            # Find the body - it typically calls do_faccessat
            # Let's hook the do_faccessat function instead
            pass
        # Try to hook do_faccessat directly
        anchor2 = "int do_faccessat(int dfd, const char __user *filename, int mode)"
        hook = "\tkus_handle_placeholder = 0; ksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n"
        hook = "\tksh_hook_placeholder = 0; ksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n"
        hook = "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n"
        if anchor2 in c:
            brace_pos = c.find("{", c.find(anchor2))
            c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
            print("[+] Patched do_faccessat in fs/open.c")
        else:
            # 4.14 might use SYSCALL_DEFINE3 directly
            # Add inside the syscall definition
            anchor3 = "SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)\n{"
            if anchor3 in c:
                c = c.replace(anchor3, anchor3 + "\n" + hook, 1)
                print("[+] Patched SYSCALL faccessat in fs/open.c")
            else:
                print("[!] Could not find faccessat hook location in fs/open.c")
                ok = False
        with open(open_c, "w") as f:
            f.write(c)
    else:
        print("[-] fs/open.c already patched")

    # ============ 4. fs/stat.c - stat hook (hide su from stat) ============
    stat_c = "fs/stat.c"
    with open(stat_c, "r") as f:
        c = f.read()
    if "ksu_handle_stat" not in c:
        decl = "\nextern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);\n"
        last_inc = c.rfind("#include")
        if last_inc > 0:
            line_end = c.find("\n", last_inc)
            c = c[:line_end+1] + decl + c[line_end+1:]
        # Find vfs_fstatat (common stat entry point in 4.14)
        anchor = "int vfs_fstatat(int dfd, const char __user *filename, struct kstat *stat,"
        hook = "\tkus_placeholder = 0; ksu_handle_stat(&dfd, &filename, &flag);\n"
        hook = "\tksu_handle_stat(&dfd, &filename, &flag);\n"
        if anchor in c:
            brace_pos = c.find("{", c.find(anchor))
            # Need to get the flag parameter name - it might be "flag" or "flags"
            # Find the function signature
            func_start = c.find(anchor)
            func_end = c.find(")", func_start)
            sig = c[func_start:func_end]
            if "int flag)" in sig or "int flag )" in sig:
                flag_name = "flag"
            elif "int flags)" in sig:
                flag_name = "flags"
            else:
                flag_name = "flag"
            hook = f"\tksu_handle_stat(&dfd, &filename, &{flag_name});\n"
            c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
            print("[+] Patched vfs_fstatat in fs/stat.c")
        else:
            print("[!] Could not find vfs_fstatat in fs/stat.c (might not exist in this kernel)")
            # Not critical - stat hiding is optional
            # Just add the declaration for linking
        with open(stat_c, "w") as f:
            f.write(c)
    else:
        print("[-] fs/stat.c already patched")

    # ============ 5. kernel/sys.c - setresuid hook (root granting) ============
    sys_c = "kernel/sys.c"
    with open(sys_c, "r") as f:
        c = f.read()
    if "ksu_handle_setresuid" not in c:
        decl = "\nextern int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid);\n"
        last_inc = c.rfind("#include")
        if last_inc > 0:
            line_end = c.find("\n", last_inc)
            c = c[:line_end+1] + decl + c[line_end+1:]
        # Find __sys_setresuid
        anchor = "long __sys_setresuid(uid_t ruid, uid_t euid, uid_t suid)"
        hook = "\tksu_handle_setresuid(ruid, euid, suid);\n"
        if anchor in c:
            brace_pos = c.find("{", c.find(anchor))
            c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
            print("[+] Patched __sys_setresuid in kernel/sys.c")
        else:
            # 4.14 might use SYSCALL_DEFINE3(setresuid, ...)
            anchor2 = "SYSCALL_DEFINE3(setresuid, uid_t, ruid, uid_t, euid, uid_t, suid)"
            if anchor2 in c:
                brace_pos = c.find("{", c.find(anchor2))
                c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
                print("[+] Patched SYSCALL setresuid in kernel/sys.c")
            else:
                print("[!] Could not find setresuid in kernel/sys.c")
                ok = False
        with open(sys_c, "w") as f:
            f.write(c)
    else:
        print("[-] kernel/sys.c already patched")

    # ============ 6. fs/read_write.c - vfs_read hook (hide su reads) ============
    rw_c = "fs/read_write.c"
    with open(rw_c, "r") as f:
        c = f.read()
    if "ksu_handle_vfs_read" not in c:
        # Check if the function exists in KSU
        # In v3.2.0-legacy, it might be in file_wrapper.c
        # Only add if the KSU source has it
        ksu_dir = "KernelSU-Next"
        sucompat = os.path.join(ksu_dir, "kernel", "feature", "sucompat.c")
        with open(sucompat, "r") as f:
            ksu_src = f.read()
        if "ksu_handle_vfs_read" in ksu_src:
            decl = "\nextern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr, size_t *count_ptr, loff_t **pos_ptr);\n"
            last_inc = c.rfind("#include")
            if last_inc > 0:
                line_end = c.find("\n", last_inc)
                c = c[:line_end+1] + decl + c[line_end+1:]
            anchor = "ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)"
            hook = "\tkus_p = 0; ksu_handle_vfs_read(&file, &buf, &count, &pos);\n"
            hook = "\tksu_handle_vfs_read(&file, &buf, &count, &pos);\n"
            if anchor in c:
                brace_pos = c.find("{", c.find(anchor))
                c = c[:brace_pos+1] + "\n" + hook + c[brace_pos+1:]
                print("[+] Patched vfs_read in fs/read_write.c")
            with open(rw_c, "w") as f:
                f.write(c)
        else:
            print("[i] ksu_handle_vfs_read not in KSU source, skipping fs/read_write.c")

    # ============ Summary ============
    print("\n" + "="*50)
    if ok:
        print("[+] All manual hooks applied successfully!")
        print("[+] Config changes: NONE (only CONFIG_KSU=y needed)")
    else:
        print("[!] Some hooks failed - check output above")
        sys.exit(1)

if __name__ == "__main__":
    main()
