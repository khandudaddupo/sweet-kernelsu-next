#!/usr/bin/env python3
"""Bootstrap patches for KSU-Next v3.4.0-legacy (manual-hook builds).

Ported from the PROVEN September Vantom build (patch_manager_bootstrap.py +
patch_getinfo_bootstrap.py), extended to patch BOTH get_info variants
(do_get_info modern + do_get_info_legacy) present in v3.4.0-legacy.

Fixes: manager can't register without root, root needs manager (chicken-and-egg).
First GET_INFO / allowed_for_su caller auto-registers as manager.
Run from the kernel source root (KernelSU-Next lives next to kernel files).
Idempotent.
"""
import sys

BASE = "KernelSU-Next/kernel/supercall"

def patch_file(path, patches):
    try:
        c = open(path).read()
    except FileNotFoundError:
        print(f"[!] MISSING: {path}")
        return False
    ok = True
    for anchor, repl, desc in patches:
        if repl in c:
            print(f"[-] already patched: {desc}")
            continue
        if anchor not in c:
            print(f"[!] anchor not found for {desc} in {path}")
            ok = False
            continue
        c = c.replace(anchor, repl, 1)
        print(f"[+] patched: {desc}")
    if ok:
        open(path, "w").write(c)
    return ok

def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "KernelSU-Next/kernel/supercall"
    # ---- 1. perm.c: allowed_for_su bootstrap ----
    old_p = (
        "bool allowed_for_su(void)\n"
        "{\n"
        "\tbool is_allowed = is_manager() || ksu_is_allow_uid_for_current(current_uid().val);\n"
        "\treturn is_allowed;\n"
        "}"
    )
    new_p = (
        "bool allowed_for_su(void)\n"
        "{\n"
        "\tbool is_allowed = is_manager() || ksu_is_allow_uid_for_current(current_uid().val);\n"
        "\tif (is_allowed) return true;\n"
        "\t/* BOOTSTRAP: first caller becomes manager when none registered */\n"
        "\tif (!ksu_is_manager_appid_valid()) {\n"
        "\t\tksu_set_manager_appid(current_uid().val % KSU_PER_USER_RANGE);\n"
        "\t\tpr_info(\"KernelSU: bootstrap: auto-registered uid=%d as manager\\n\", current_uid().val);\n"
        "\t\treturn true;\n"
        "\t}\n"
        "\treturn false;\n"
        "}"
    )
    ok = patch_file(f"{base}/perm.c", [(old_p, new_p, "perm.c allowed_for_su bootstrap")])

    # ---- 2. dispatch.c: GET_INFO bootstrap (modern, 4-space style) ----
    old_g1 = (
        "    if (is_manager()) {\n"
        "        cmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n"
        "    }\n"
    )
    new_g1 = (
        "    /* BOOTSTRAP_GET_INFO: auto-register first caller as manager */\n"
        "    if (!ksu_is_manager_appid_valid()) {\n"
        "        ksu_set_manager_appid(current_uid().val % KSU_PER_USER_RANGE);\n"
        "        pr_info(\"KernelSU: bootstrap: GET_INFO auto-registered uid=%d\\n\", current_uid().val);\n"
        "    }\n"
        "    if (is_manager()) {\n"
        "        cmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n"
        "    }\n"
    )
    ok = patch_file(f"{base}/dispatch.c", [(old_g1, new_g1, "dispatch.c do_get_info bootstrap")]) and ok

    # ---- 3. dispatch.c: GET_INFO legacy (tab style) ----
    old_g2 = (
        "\tif (is_manager()) {\n"
        "\t\tcmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n"
        "\t}\n"
    )
    new_g2 = (
        "\t/* BOOTSTRAP_GET_INFO_LEGACY: auto-register first caller as manager */\n"
        "\tif (!ksu_is_manager_appid_valid()) {\n"
        "\t\tksu_set_manager_appid(current_uid().val % KSU_PER_USER_RANGE);\n"
        "\t\tpr_info(\"KernelSU: bootstrap: GET_INFO_LEGACY auto-registered uid=%d\\n\", current_uid().val);\n"
        "\t}\n"
        "\tif (is_manager()) {\n"
        "\t\tcmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n"
        "\t}\n"
    )
    ok = patch_file(f"{base}/dispatch.c", [(old_g2, new_g2, "dispatch.c do_get_info_legacy bootstrap")]) and ok

    if not ok:
        print("BOOTSTRAP PATCH FAILED")
        sys.exit(1)
    print("all KSU bootstrap patches applied")

if __name__ == "__main__":
    main()
