#!/usr/bin/env python3
"""Patch manager bootstrap in KSU-Next perm.c for MANUAL_HOOK mode.
Fixes: manager can't register without root, root needs manager (chicken-and-egg).
Solution: first GRANT_ROOT caller auto-registers as manager.
"""
import sys

def patch():
    path = "KernelSU-Next/kernel/supercall/perm.c"
    with open(path, "r") as f:
        content = f.read()

    if "BOOTSTRAP" in content:
        print("[-] Already patched")
        return True

    old_func = (
        "bool allowed_for_su(void)\n"
        "{\n"
        "\tbool is_allowed = is_manager() || ksu_is_allow_uid_for_current(current_uid().val);\n"
        "\treturn is_allowed;\n"
        "}"
    )

    new_func = (
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

    if old_func not in content:
        print("[!] PATCH FAILED - original function not found!")
        return False

    content = content.replace(old_func, new_func)
    with open(path, "w") as f:
        f.write(content)

    print("[+] Manager bootstrap patch applied!")
    return True

if __name__ == "__main__":
    if not patch():
        sys.exit(1)
