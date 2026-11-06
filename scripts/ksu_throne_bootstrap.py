#!/usr/bin/env python3
"""THRONE BOOTSTRAP for built-in KSU-Next v3.4.0-legacy onboarding (4.14).

Problem: in built-in (non-LKM) mode the manager is crowned only when
/data/system/packages.list CHANGES (fsnotify pkg_observer) or when root ksud
reports boot events. On a phone where the manager APK was installed BEFORE
this kernel first booted (and /data/adb/ksu/bin/ksud does not exist), neither
ever happens -> manager never crowned -> ksu_manager_appid stays invalid ->
setresuid hook never installs the driver fd -> manager logs
"KernelSU driver install syscall was blocked by seccomp" and shows Unsupported.

Fix (belt & suspenders, kernel-side, no data/adb setup needed):
 1. boot_event.c on_post_fs_data(): run track_throne(false) once at zygote
    exec (after /data is mounted, before any app spawns) so every boot
    searches /data/app and crowns the signature-matching manager APK.
 2. hook/setuid_hook.c ksu_handle_setresuid(): while no manager is
    registered, retry the bounded search on app spawns. The spawn that IS
    the manager is crowned and immediately gets its driver fd + seccomp
    disable in the same call.
"""

import sys


def patch_boot_event():
    path = "KernelSU-Next/kernel/runtime/boot_event.c"
    with open(path, "r") as f:
        content = f.read()

    if "THRONE_BOOTSTRAP" in content:
        print("[-] boot_event.c already patched")
        return True

    old = (
        "\tksu_load_allow_list();\n"
        "\tksu_observer_init();\n"
        "\t// sanity check, this may influence the performance\n"
        "\tksu_stop_input_hook_runtime();\n"
    )

    new = (
        "\tksu_load_allow_list();\n"
        "\tksu_observer_init();\n"
        "\t/* THRONE_BOOTSTRAP: crown the manager on every boot - built-in mode\n"
        "\t * only gets packages.list change events, which never happen for an\n"
        "\t * APK installed before this kernel booted, and root ksud may not\n"
        "\t * exist on fresh data. */\n"
        "\ttrack_throne(false);\n"
        "\t// sanity check, this may influence the performance\n"
        "\tksu_stop_input_hook_runtime();\n"
    )

    if old not in content:
        print("[!] boot_event.c patch FAILED - anchor not found!")
        return False

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)

    print("[+] boot_event.c throne bootstrap applied!")
    return True


def patch_setuid_hook():
    path = "KernelSU-Next/kernel/hook/setuid_hook.c"
    with open(path, "r") as f:
        content = f.read()

    if "THRONE_BOOTSTRAP" in content:
        print("[-] setuid_hook.c already patched")
        return True

    old_inc = '#include "manager/manager_identity.h"\n'
    new_inc = (
        '#include "manager/manager_identity.h"\n'
        '#include "manager/throne_tracker.h"\n'
    )
    if old_inc not in content:
        print("[!] setuid_hook.c include anchor not found!")
        return False
    content = content.replace(old_inc, new_inc, 1)

    old = (
        "int ksu_handle_setresuid(uid_t old_uid, uid_t new_uid)\n"
        "{\n"
        "    // we rely on the fact that zygote always call setresuid(3) with same uids\n"
        "\n"
        "    pr_info(\"handle_setresuid from %d to %d\\n\", old_uid, new_uid);\n"
        "\n"
    )

    new = (
        "int ksu_handle_setresuid(uid_t old_uid, uid_t new_uid)\n"
        "{\n"
        "    // we rely on the fact that zygote always call setresuid(3) with same uids\n"
        "\n"
        "    pr_info(\"handle_setresuid from %d to %d\\n\", old_uid, new_uid);\n"
        "\n"
        "    /* THRONE_BOOTSTRAP: no manager registered yet (fresh install, built-in\n"
        "     * driver, no ksud on /data/adb). Bounded search-and-crown on app\n"
        "     * spawns; the spawn that is the manager is crowned and gets its\n"
        "     * driver fd in the same call below. */\n"
        "    static int throne_tries = 0;\n"
        "    if (unlikely(!ksu_is_manager_appid_valid()) && throne_tries < 10) {\n"
        "        throne_tries++;\n"
        "        track_throne(false);\n"
        "    }\n"
        "\n"
    )

    if old not in content:
        print("[!] setuid_hook.c function anchor not found!")
        return False

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)

    print("[+] setuid_hook.c throne bootstrap applied!")
    return True


if __name__ == "__main__":
    ok = patch_boot_event() and patch_setuid_hook()
    if not ok:
        sys.exit(1)
