#!/usr/bin/env python3
import sys
def patch_perm():
    path = "KernelSU-Next/kernel/supercall/perm.c"
    with open(path, "r") as f: c = f.read()
    if "ADB_SHELL" in c: print("[-] perm already patched"); return True
    old = "bool allowed_for_su(void)\n{"
    new = "bool allowed_for_su(void)\n{\n\t/* ADB_SHELL: always allow ADB shell uid 2000 */\n\tif (current_uid().val == 2000) return true;"
    if old not in c: print("[!] perm anchor missing"); return False
    c = c.replace(old, new, 1)
    with open(path, "w") as f: f.write(c)
    print("[+] ADB root OK"); return True
def patch_exec_ksud():
    path = "fs/exec.c"
    with open(path, "r") as f: c = f.read()
    if "KSUD_ROOT_HOOK" in c: print("[-] exec already patched"); return True
    anchor = "ksu_handle_execveat_sucompat(&fd, &filename, NULL, NULL, NULL);"
    hook = anchor + "\n\t/* KSUD_ROOT_HOOK: give root to /data/adb/ksud */\n\tif (filename && filename->name && strncmp(filename->name, \"/data/adb/ksud\", 15) == 0) {\n\t\tstruct cred *kc = prepare_creds();\n\t\tif (kc) {\n\t\t\tkc->uid.val = 0; kc->gid.val = 0; kc->euid.val = 0; kc->egid.val = 0;\n\t\t\tkc->suid.val = 0; kc->sgid.val = 0;\n\t\t\tcommit_creds(kc);\n\t\t}\n\t}"
    if anchor not in c: print("[!] exec anchor missing"); return False
    c = c.replace(anchor, hook, 1)
    with open(path, "w") as f: f.write(c)
    print("[+] ksud root hook OK"); return True
if __name__ == "__main__":
    ok = patch_perm() and patch_exec_ksud()
    if not ok: sys.exit(1)
    print("[+] BOTH PATCHES APPLIED!")
