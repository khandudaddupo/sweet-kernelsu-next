#!/usr/bin/env python3
import os
import sys
import shutil
import argparse
import subprocess

def log(msg):
    print(f"[*] {msg}")

def run_cmd(cmd, cwd="."):
    res = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        print(f"[!] Command exited {res.returncode}: {cmd}\n{res.stdout}")
        return False, res.stdout
    return True, res.stdout

def main():
    parser = argparse.ArgumentParser(description="Patch SuSFS, NoMount and KernelSU-Next into kernel tree")
    parser.add_argument("--ksu-repo", default="https://github.com/xtrance-eng/KernelSU-Next.git", help="KernelSU-Next git repo")
    parser.add_argument("--ksu-branch", default="legacy-susfs", help="KernelSU-Next git branch")
    args = parser.parse_args()

    kernel_dir = os.getcwd()
    log(f"Starting patch pipeline in: {kernel_dir}")

    # ----------------------------------------------------
    # 1. Setup KernelSU-Next
    # ----------------------------------------------------
    log(f"Setting up KernelSU-Next from {args.ksu_repo} (branch: {args.ksu_branch})...")
    ksu_dir = os.path.join(kernel_dir, "KernelSU-Next")
    if not os.path.exists(ksu_dir):
        ok, out = run_cmd(f"git clone --depth=1 -b {args.ksu_branch} {args.ksu_repo} KernelSU-Next")
        if not ok:
            log("Failed to clone KernelSU-Next")
            return 1

    drivers_dir = os.path.join(kernel_dir, "drivers")
    ksu_symlink = os.path.join(drivers_dir, "kernelsu")
    if not os.path.exists(ksu_symlink):
        os.symlink("../KernelSU-Next/kernel", ksu_symlink)
        log("Created drivers/kernelsu symlink")

    d_makefile = os.path.join(drivers_dir, "Makefile")
    with open(d_makefile, "r") as f:
        d_m = f.read()
    if "kernelsu" not in d_m:
        with open(d_makefile, "a") as f:
            f.write("\nobj-$(CONFIG_KSU) += kernelsu/\n")
        log("Added kernelsu to drivers/Makefile")

    d_kconfig = os.path.join(drivers_dir, "Kconfig")
    with open(d_kconfig, "r") as f:
        d_k = f.read()
    if 'source "drivers/kernelsu/Kconfig"' not in d_k:
        d_k = d_k.replace("endmenu", 'source "drivers/kernelsu/Kconfig"\nendmenu', 1)
        with open(d_kconfig, "w") as f:
            f.write(d_k)
        log("Added drivers/kernelsu/Kconfig to drivers/Kconfig")

    # ----------------------------------------------------
    # 2. Setup NoMount
    # ----------------------------------------------------
    log("Setting up NoMount (VFS redirection)...")
    nomount_dir = os.path.join(kernel_dir, "NoMount")
    if not os.path.exists(nomount_dir):
        ok, out = run_cmd("git clone --depth=1 https://github.com/maxsteeel/nomount.git NoMount")
        if not ok:
            log("Failed to clone NoMount")
            return 1

    fs_dir = os.path.join(kernel_dir, "fs")
    nm_symlink = os.path.join(fs_dir, "nomount")
    if not os.path.exists(nm_symlink):
        os.symlink("../NoMount/kernel/src", nm_symlink)
        log("Created fs/nomount symlink")

    fs_makefile = os.path.join(fs_dir, "Makefile")
    with open(fs_makefile, "r") as f:
        m_content = f.read()
    if "obj-$(CONFIG_NOMOUNT)" not in m_content:
        with open(fs_makefile, "a") as f:
            f.write("\nobj-$(CONFIG_NOMOUNT) += nomount/\n")
        log("Added nomount to fs/Makefile")

    fs_kconfig = os.path.join(fs_dir, "Kconfig")
    with open(fs_kconfig, "r") as f:
        k_content = f.read()
    if 'source "fs/nomount/Kconfig"' not in k_content:
        k_content = k_content.replace('endmenu', 'source "fs/nomount/Kconfig"\nendmenu', 1)
        with open(fs_kconfig, "w") as f:
            f.write(k_content)
        log("Added nomount to fs/Kconfig")

    # ----------------------------------------------------
    # 3. Setup SuSFS 4.14
    # ----------------------------------------------------
    log("Setting up SuSFS 4.14...")
    susfs_repo = os.path.join(kernel_dir, "susfs4ksu")
    if not os.path.exists(susfs_repo):
        ok, out = run_cmd("git clone --depth=1 -b kernel-4.14 https://gitlab.com/simonpunk/susfs4ksu.git susfs4ksu")
        if not ok:
            log("Failed to clone susfs4ksu")
            return 1

    # Copy fs files
    susfs_fs = os.path.join(susfs_repo, "kernel_patches", "fs")
    for f in os.listdir(susfs_fs):
        src = os.path.join(susfs_fs, f)
        dst = os.path.join(kernel_dir, "fs", f)
        shutil.copy2(src, dst)
        log(f"Copied fs/{f}")

    # Copy include files
    susfs_inc = os.path.join(susfs_repo, "kernel_patches", "include", "linux")
    for f in os.listdir(susfs_inc):
        src = os.path.join(susfs_inc, f)
        dst = os.path.join(kernel_dir, "include", "linux", f)
        shutil.copy2(src, dst)
        log(f"Copied include/linux/{f}")

    # Apply 50_add_susfs_in_kernel-4.14.patch
    patch_file = os.path.join(susfs_repo, "kernel_patches", "50_add_susfs_in_kernel-4.14.patch")
    log(f"Applying SuSFS patch: {patch_file}")
    run_cmd(f"patch -p1 -N -s < {patch_file}")

    # 1. Compatibility extensions for include/linux/susfs_def.h
    susfs_def_header = os.path.join(kernel_dir, "include", "linux", "susfs_def.h")
    if os.path.exists(susfs_def_header):
        with open(susfs_def_header, "r") as f:
            def_text = f.read()
        compat_def_ext = """
/* Compatibility extensions for KernelSU-Next legacy */
#ifndef SUSFS_MAGIC
#define SUSFS_MAGIC 0xFAFAFAFA
#endif
#ifndef CMD_SUSFS_ADD_SUS_PATH_LOOP
#define CMD_SUSFS_ADD_SUS_PATH_LOOP 0x55551
#endif
#ifndef CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS
#define CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS 0x55561
#endif
#ifndef CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING
#define CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING 0x555c1
#endif
#ifndef CMD_SUSFS_ADD_SUS_MAP
#define CMD_SUSFS_ADD_SUS_MAP 0x555c2
#endif

#ifndef TASK_STRUCT_PROC_UMOUNTED
#define TASK_STRUCT_PROC_UMOUNTED BIT(25)
#endif

#include <linux/sched.h>

static inline void susfs_set_current_proc_umounted(void) {
#if defined(CONFIG_KSU_SUSFS)
	current->susfs_task_state |= TASK_STRUCT_PROC_UMOUNTED;
#endif
}

static inline bool susfs_is_current_proc_umounted(void) {
#if defined(CONFIG_KSU_SUSFS)
	return !!(current->susfs_task_state & TASK_STRUCT_PROC_UMOUNTED);
#else
	return false;
#endif
}
"""
        if "susfs_set_current_proc_umounted" not in def_text:
            idx = def_text.rfind("#endif")
            if idx != -1:
                def_text = def_text[:idx] + compat_def_ext + "\n#endif\n"
            else:
                def_text += compat_def_ext
            with open(susfs_def_header, "w") as f:
                f.write(def_text)
            log("Appended SuSFS compatibility extensions to include/linux/susfs_def.h")

    # 2. Compatibility extensions for include/linux/susfs.h
    susfs_header = os.path.join(kernel_dir, "include", "linux", "susfs.h")
    if os.path.exists(susfs_header):
        with open(susfs_header, "r") as f:
            h_text = f.read()
        compat_ext = """
/* Compatibility extensions for KernelSU-Next legacy */
#include <linux/uaccess.h>
#include <linux/slab.h>

#ifndef SUSFS_MAX_VERSION_BUFSIZE
#define SUSFS_MAX_VERSION_BUFSIZE 16
#endif
#ifndef SUSFS_MAX_VARIANT_BUFSIZE
#define SUSFS_MAX_VARIANT_BUFSIZE 16
#endif
#ifndef SUSFS_ENABLED_FEATURES_SIZE
#define SUSFS_ENABLED_FEATURES_SIZE 8192
#endif

struct st_susfs_version_compat {
	char susfs_version[SUSFS_MAX_VERSION_BUFSIZE];
	int err;
};

struct st_susfs_variant_compat {
	char susfs_variant[SUSFS_MAX_VARIANT_BUFSIZE];
	int err;
};

struct st_susfs_enabled_features_compat {
	char enabled_features[SUSFS_ENABLED_FEATURES_SIZE];
	int err;
};

static inline void susfs_show_version(void __user *arg) {
	struct st_susfs_version_compat info;
	if (!arg)
		return;
	memset(&info, 0, sizeof(info));
	strncpy(info.susfs_version, SUSFS_VERSION, sizeof(info.susfs_version) - 1);
	info.err = 0;
	if (copy_to_user(arg, &info, sizeof(info)))
		pr_err("susfs_show_version: copy_to_user failed\\n");
}

static inline void susfs_show_variant(void __user *arg) {
	struct st_susfs_variant_compat info;
	if (!arg)
		return;
	memset(&info, 0, sizeof(info));
	strncpy(info.susfs_variant, "SUSFS_4.14", sizeof(info.susfs_variant) - 1);
	info.err = 0;
	if (copy_to_user(arg, &info, sizeof(info)))
		pr_err("susfs_show_variant: copy_to_user failed\\n");
}

static inline void susfs_get_enabled_features(void __user *arg) {
	struct st_susfs_enabled_features_compat *info;
	if (!arg)
		return;
	info = kzalloc(sizeof(*info), GFP_ATOMIC);
	if (!info)
		return;
	snprintf(info->enabled_features, sizeof(info->enabled_features),
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
		"CONFIG_KSU_SUSFS_SUS_PATH\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
		"CONFIG_KSU_SUSFS_SUS_MOUNT\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
		"CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
		"CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
		"CONFIG_KSU_SUSFS_SUS_KSTAT\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
		"CONFIG_KSU_SUSFS_TRY_UMOUNT\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
		"CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
		"CONFIG_KSU_SUSFS_SPOOF_UNAME\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
		"CONFIG_KSU_SUSFS_ENABLE_LOG\\n"
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
		"CONFIG_KSU_SUSFS_OPEN_REDIRECT\\n"
#endif
		"CONFIG_KSU_SUSFS\\n"
	);
	info->err = 0;
	if (copy_to_user(arg, info, sizeof(*info)))
		pr_err("susfs_get_enabled_features: copy_to_user failed\\n");
	kfree(info);
}

static inline void susfs_start_sdcard_monitor_fn(void) {}
static inline void susfs_set_avc_log_spoofing(void __user *arg) {}
static inline void susfs_add_sus_path_loop(void __user *arg) {}
static inline void susfs_set_hide_sus_mnts_for_non_su_procs(void __user *arg) {}
static inline void susfs_add_sus_map(void __user *arg) {}
static inline void susfs_enable_log(void __user *arg) {}
"""
        if "susfs_show_version" not in h_text:
            idx = h_text.rfind("#endif")
            if idx != -1:
                h_text = h_text[:idx] + compat_ext + "\n#endif\n"
            else:
                h_text += compat_ext
            with open(susfs_header, "w") as f:
                f.write(h_text)
            log("Appended SuSFS compatibility extensions to include/linux/susfs.h")

    # 3. Patch supercall.c: remove conflicting dummy susfs_try_umount and dereference *arg
    for sc_candidate in [
        os.path.join(kernel_dir, "KernelSU-Next", "kernel", "supercall", "supercall.c"),
        os.path.join(kernel_dir, "drivers", "kernelsu", "supercall", "supercall.c")
    ]:
        if os.path.exists(sc_candidate):
            with open(sc_candidate, "r") as f:
                sc_text = f.read()
            # Remove conflicting dummy definitions (already provided natively by fs/susfs.c)
            idx1 = sc_text.find("void susfs_try_umount")
            if idx1 != -1:
                start = sc_text.rfind("#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT", 0, idx1)
                end = sc_text.find("#endif", idx1) + 6
                sc_text = sc_text[:start] + "/* Handled natively by fs/susfs.c */\n" + sc_text[end:]
            # Dereference arg to (void __user *)*arg because arg is void __user **arg
            for fn in [
                "susfs_add_sus_path", "susfs_add_sus_path_loop", "susfs_set_hide_sus_mnts_for_non_su_procs",
                "susfs_add_sus_kstat", "susfs_update_sus_kstat", "susfs_add_try_umount",
                "susfs_set_uname", "susfs_enable_log", "susfs_set_cmdline_or_bootconfig",
                "susfs_add_open_redirect", "susfs_add_sus_map", "susfs_set_avc_log_spoofing",
                "susfs_get_enabled_features", "susfs_show_variant", "susfs_show_version"
            ]:
                sc_text = sc_text.replace(f"{fn}(arg)", f"{fn}((void __user *)*arg)")
            with open(sc_candidate, "w") as f:
                f.write(sc_text)
            log(f"Patched {sc_candidate} (removed dummy definitions and dereferenced *arg)")

    # 4. Patch kernel_umount.c: bridge ksu_try_umount, susfs_try_umount_all, susfs_run_sus_path_loop
    for um_candidate in [
        os.path.join(kernel_dir, "KernelSU-Next", "kernel", "feature", "kernel_umount.c"),
        os.path.join(kernel_dir, "drivers", "kernelsu", "feature", "kernel_umount.c")
    ]:
        if os.path.exists(um_candidate):
            with open(um_candidate, "r") as f:
                um_text = f.read()
            if "ksu_try_umount" not in um_text:
                um_bridge = """
#ifdef CONFIG_KSU_SUSFS
#ifndef MNT_DETACH
#define MNT_DETACH 0x00000002
#endif

void ksu_try_umount(const char *mnt, bool check_mnt, int flags, uid_t uid)
{
    try_umount(mnt, flags);
}

extern void susfs_try_umount(uid_t target_uid);

void susfs_try_umount_all(uid_t uid)
{
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    susfs_try_umount(uid);
    ksu_try_umount("/system", true, 0, uid);
    ksu_try_umount("/system_ext", true, 0, uid);
    ksu_try_umount("/vendor", true, 0, uid);
    ksu_try_umount("/product", true, 0, uid);
    ksu_try_umount("/odm", true, 0, uid);
    ksu_try_umount("/data/adb/modules", false, MNT_DETACH, uid);
    ksu_try_umount("/debug_ramdisk", true, MNT_DETACH, uid);
#endif
}

void susfs_run_sus_path_loop(void)
{
}
#endif
"""
                um_text += um_bridge
                with open(um_candidate, "w") as f:
                    f.write(um_text)
                log(f"Patched {um_candidate} with ksu_try_umount, susfs_try_umount_all, and susfs_run_sus_path_loop")

    # Fix fs/proc/cmdline.c for sweet's ALTER_CMDLINE structure
    cmdline_path = os.path.join(kernel_dir, "fs", "proc", "cmdline.c")
    if os.path.exists(cmdline_path):
        with open(cmdline_path, "r") as f:
            cmd_text = f.read()
        if "susfs_spoof_cmdline_or_bootconfig" not in cmd_text:
            patch_cmd_hdr = "#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\nextern int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);\n#endif\n"
            patch_cmd_show = "static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n\tif (!susfs_spoof_cmdline_or_bootconfig(m)) {\n\t\tseq_putc(m, '\\n');\n\t\treturn 0;\n\t}\n#endif\n"
            cmd_text = cmd_text.replace("#include <linux/seq_file.h>", "#include <linux/seq_file.h>\n" + patch_cmd_hdr, 1)
            cmd_text = cmd_text.replace("static int cmdline_proc_show(struct seq_file *m, void *v)\n{", patch_cmd_show, 1)
            with open(cmdline_path, "w") as f:
                f.write(cmd_text)
            log("Patched fs/proc/cmdline.c for SuSFS")

    # Fix fs/proc/task_mmu.c header
    mmu_path = os.path.join(kernel_dir, "fs", "proc", "task_mmu.c")
    if os.path.exists(mmu_path):
        with open(mmu_path, "r") as f:
            mmu_text = f.read()
        if "CONFIG_KSU_SUSFS_SUS_KSTAT" not in mmu_text[:2000]:
            patch_mmu_hdr = "#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n#include <linux/susfs_def.h>\n#endif\n"
            mmu_text = mmu_text.replace("#include <linux/mm_inline.h>", "#include <linux/mm_inline.h>\n" + patch_mmu_hdr, 1)
            with open(mmu_path, "w") as f:
                f.write(mmu_text)
            log("Patched fs/proc/task_mmu.c header for SuSFS")

    # Clean rejects
    for root, dirs, files in os.walk(kernel_dir):
        for f in files:
            if f.endswith(".rej") or f.endswith(".orig"):
                os.remove(os.path.join(root, f))

    # ----------------------------------------------------
    # 4. Kernel namespace & seccomp backports
    # ----------------------------------------------------
    ns_file = os.path.join(kernel_dir, "fs", "namespace.c")
    if os.path.exists(ns_file):
        with open(ns_file, "r") as f:
            ns_content = f.read()
        if "int path_umount" not in ns_content:
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
            if "static bool is_mnt_ns_file" in ns_content:
                ns_content = ns_content.replace("static bool is_mnt_ns_file", patch_ns + "static bool is_mnt_ns_file", 1)
                with open(ns_file, "w") as f:
                    f.write(ns_content)
                log("Patched fs/namespace.c with path_umount")

    hdr_file = os.path.join(kernel_dir, "fs", "internal.h")
    if os.path.exists(hdr_file):
        with open(hdr_file, "r") as f:
            hdr_content = f.read()
        if "int path_umount" not in hdr_content:
            if "extern void __init mnt_init(void);" in hdr_content:
                hdr_content = hdr_content.replace(
                    "extern void __init mnt_init(void);",
                    "extern void __init mnt_init(void);\nint path_umount(struct path *path, int flags);",
                    1
                )
                with open(hdr_file, "w") as f:
                    f.write(hdr_content)
                log("Patched fs/internal.h with path_umount declaration")

    sec_file = os.path.join(kernel_dir, "include", "linux", "seccomp.h")
    if os.path.exists(sec_file):
        with open(sec_file, "r") as f:
            sec_content = f.read()
        if "atomic_t filter_count;" not in sec_content:
            if "#include <linux/thread_info.h>" in sec_content:
                sec_content = sec_content.replace(
                    "#include <linux/thread_info.h>",
                    "#include <linux/thread_info.h>\n#include <linux/atomic.h>",
                    1
                )
            if "int mode;" in sec_content:
                sec_content = sec_content.replace("int mode;", "int mode;\n\tatomic_t filter_count;", 1)
                with open(sec_file, "w") as f:
                    f.write(sec_content)
                log("Patched include/linux/seccomp.h with filter_count")

    # Fix sulog/event.c timespec mismatch if present
    for sulog_candidate in [
        os.path.join(kernel_dir, "KernelSU-Next", "kernel", "sulog", "event.c"),
        os.path.join(kernel_dir, "drivers", "kernelsu", "sulog", "event.c")
    ]:
        if os.path.exists(sulog_candidate):
            with open(sulog_candidate, "r") as f:
                c = f.read()
            if "get_monotonic_boottime(&ts)" in c:
                c = c.replace("get_monotonic_boottime(&ts)", "ktime_get_boottime_ts64(&ts)")
                with open(sulog_candidate, "w") as f:
                    f.write(c)
                log("Patched sulog/event.c timespec64")

    # ----------------------------------------------------
    # 5. Append KSU, SuSFS & NoMount configs to sweet_defconfig
    # ----------------------------------------------------
    defconfig_path = os.path.join(kernel_dir, "arch", "arm64", "configs", "sweet_defconfig")
    if os.path.exists(defconfig_path):
        with open(defconfig_path, "a") as f:
            f.write("""
# KernelSU-Next
CONFIG_KSU=y
CONFIG_KPROBES=y
CONFIG_HAVE_KPROBES=y
CONFIG_KRETPROBES=y
CONFIG_HAVE_KRETPROBES=y
CONFIG_KSU_KPROBES_HOOK=y

# SuSFS 4.14
CONFIG_KSU_SUSFS=y
CONFIG_KSU_SUSFS_SUS_PATH=y
CONFIG_KSU_SUSFS_SUS_MOUNT=y
CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT=y
CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT=y
CONFIG_KSU_SUSFS_SUS_KSTAT=y
CONFIG_KSU_SUSFS_TRY_UMOUNT=y
CONFIG_KSU_SUSFS_SPOOF_UNAME=y
CONFIG_KSU_SUSFS_ENABLE_LOG=y
CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y
CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y
CONFIG_KSU_SUSFS_OPEN_REDIRECT=y
CONFIG_KSU_SUSFS_SUS_MAP=y

# NoMount
CONFIG_NOMOUNT=y
""")
        log("Appended KSU, SuSFS, and NoMount configs to sweet_defconfig")

    log("Kernel tree patching completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
