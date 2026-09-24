#!/usr/bin/env python3
"""Patch: ADB shell root + auto-enforce SELinux after 30s"""
import sys

def patch_perm():
    path = "KernelSU-Next/kernel/supercall/perm.c"
    with open(path, "r") as f:
        c = f.read()
    if "ADB_SHELL" in c:
        print("[-] perm already patched"); return True
    old = "bool allowed_for_su(void)\n{"
    new = "bool allowed_for_su(void)\n{\n\t/* ADB_SHELL: always allow ADB shell uid 2000 */\n\tif (current_uid().val == 2000) return true;"
    if old not in c:
        print("[!] perm anchor not found"); return False
    c = c.replace(old, new, 1)
    with open(path, "w") as f: f.write(c)
    print("[+] ADB shell root OK"); return True

def patch_init():
    path = "KernelSU-Next/kernel/core/init.c"
    with open(path, "r") as f:
        c = f.read()
    if "AUTO_ENFORCE" in c:
        print("[-] init already patched"); return True
    # Use KSU's own getenforce/setenforce (defined in selinux/selinux.c)
    work = """
/* AUTO_ENFORCE: enforce SELinux 30s after boot for UPI safety */
static void ksu_enforce_work_fn(struct work_struct *w);
static DECLARE_DELAYED_WORK(ksu_enforce_work, ksu_enforce_work_fn);
static void ksu_enforce_work_fn(struct work_struct *w)
{
\tif (!getenforce()) {
\t\tpr_info("KernelSU: AUTO_ENFORCE enforcing SELinux now\\n");
\t\tsetenforce(true);
\t}
}
"""
    anchor = "int __init kernelsu_init(void)"
    if anchor not in c:
        print("[!] init anchor not found"); return False
    c = c.replace(anchor, work + "\n" + anchor, 1)
    # Add schedule call in built-in path (else block)
    sched = "\n\t\t/* AUTO_ENFORCE: schedule SELinux enforcement in 30 seconds */\n\t\tschedule_delayed_work(&ksu_enforce_work, msecs_to_jiffies(30000));"
    insert = "ksu_file_wrapper_init();"
    if insert not in c:
        print("[!] file_wrapper_init not found"); return False
    c = c.replace(insert, insert + sched, 1)
    with open(path, "w") as f: f.write(c)
    print("[+] Auto-enforce SELinux OK"); return True

if __name__ == "__main__":
    ok = patch_perm() and patch_init()
    if not ok: sys.exit(1)
    print("[+] BOTH PATCHES APPLIED!")
