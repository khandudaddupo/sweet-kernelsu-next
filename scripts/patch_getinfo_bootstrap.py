#!/usr/bin/env python3
"""Patch GET_INFO handler to bootstrap manager registration.
The manager calls GET_INFO first (always_allow perm), which returns
is_manager() status. If no manager registered → shows "Unsupported"
and never reaches GRANT_ROOT. Fix: auto-register in GET_INFO too.
"""
import sys

def patch_get_info():
    path = "KernelSU-Next/kernel/supercall/dispatch.c"
    with open(path, "r") as f:
        content = f.read()

    if "BOOTSTRAP_GET_INFO" in content:
        print("[-] Already patched")
        return True

    # Find do_get_info and add bootstrap before is_manager check
    old_code = (
        "\tif (is_manager()) {\n"
        "\t\tcmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n"
        "\t}"
    )

    new_code = (
        "\t/* BOOTSTRAP_GET_INFO: auto-register first caller as manager */\n"
        "\tif (!ksu_is_manager_appid_valid()) {\n"
        "\t\tksu_set_manager_appid(current_uid().val % KSU_PER_USER_RANGE);\n"
        "\t\tpr_info(\"KernelSU: bootstrap: GET_INFO auto-registered uid=%d\\n\", current_uid().val);\n"
        "\t}\n"
        "\tif (is_manager()) {\n"
        "\t\tcmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n"
        "\t}"
    )

    if old_code not in content:
        print("[!] GET_INFO patch FAILED - code not found!")
        return False

    content = content.replace(old_code, new_code, 1)

    with open(path, "w") as f:
        f.write(content)

    print("[+] GET_INFO bootstrap patch applied!")
    return True

if __name__ == "__main__":
    if not patch_get_info():
        sys.exit(1)
