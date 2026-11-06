#!/usr/bin/env python3
"""v9 THRONE RETRY fix for KernelSU-Next legacy onboarding.

dmesg-proven root cause (v8-debug, 2026-11-07):
    track_throne: open /data/system/packages.list failed: -2
PackageManagerService writes /data/system/packages.list SECONDS after the
first app spawns, but the v6 bootstrap burned all 10 tries in the first
second of spawning (ENOENT). The search never ran once the file existed.

Fix:
  * track_throne() now returns int: -ENOENT when packages.list is not there
    yet, 0 otherwise.
  * setresuid bootstrap retries are FREE while the list is missing
    (-ENOENT); only real searches (list existed, manager not found) count
    against a 20-attempt cap.
  * the fsnotify observer is started at the first spawn so manager
    reinstalls re-crown without a reboot.
  * once crowned, the allowlist is loaded from /data/adb/ksu.
"""

import sys


def patch_header():
    path = "KernelSU-Next/kernel/manager/throne_tracker.h"
    with open(path, "r") as f:
        content = f.read()

    if "int track_throne" in content:
        print("[-] throne_tracker.h already patched")
        return True

    old_inline = (
        "static inline void track_throne(bool prune_only)\n"
        "{\n"
        "    (void)prune_only;\n"
        "}\n"
    )
    new_inline = (
        "static inline int track_throne(bool prune_only)\n"
        "{\n"
        "    (void)prune_only;\n"
        "    return 0;\n"
        "}\n"
    )
    if old_inline in content:
        content = content.replace(old_inline, new_inline, 1)

    old_decl = "void track_throne(bool prune_only);\n"
    new_decl = "int track_throne(bool prune_only);\n"
    if old_decl not in content:
        print("[!] throne_tracker.h decl anchor not found!")
        return False
    content = content.replace(old_decl, new_decl, 1)

    with open(path, "w") as f:
        f.write(content)
    print("[+] throne_tracker.h: track_throne now returns int")
    return True


def patch_impl():
    path = "KernelSU-Next/kernel/manager/throne_tracker.c"
    with open(path, "r") as f:
        content = f.read()

    if "int track_throne(bool prune_only)" in content:
        print("[-] throne_tracker.c already patched")
        return True

    old_sig = (
        "void track_throne(bool prune_only)\n"
        "{\n"
        "\tconst struct cred *old_cred = override_creds(ksu_cred);\n"
        "\tstruct file *fp = filp_open(SYSTEM_PACKAGES_LIST_PATH, O_RDONLY, 0);\n"
        "\tif (IS_ERR(fp)) {\n"
        "\t\tpr_err(\"%s: open \" SYSTEM_PACKAGES_LIST_PATH \" failed: %ld\\n\", __func__,\n"
        "\t\t\tPTR_ERR(fp));\n"
        "\t\tgoto out_revert_cred;\n"
        "\t}\n"
    )
    new_sig = (
        "int track_throne(bool prune_only)\n"
        "{\n"
        "\tint ret = 0;\n"
        "\tconst struct cred *old_cred = override_creds(ksu_cred);\n"
        "\tstruct file *fp = filp_open(SYSTEM_PACKAGES_LIST_PATH, O_RDONLY, 0);\n"
        "\tif (IS_ERR(fp)) {\n"
        "\t\tret = PTR_ERR(fp);\n"
        "\t\tpr_err(\"%s: open \" SYSTEM_PACKAGES_LIST_PATH \" failed: %ld\\n\", __func__,\n"
        "\t\t\tPTR_ERR(fp));\n"
        "\t\tgoto out_revert_cred;\n"
        "\t}\n"
    )
    if old_sig not in content:
        print("[!] throne_tracker.c signature anchor not found!")
        return False
    content = content.replace(old_sig, new_sig, 1)

    old_tail = (
        "out_revert_cred:\n"
        "\trevert_creds(old_cred);\n"
        "}\n"
    )
    new_tail = (
        "out_revert_cred:\n"
        "\trevert_creds(old_cred);\n"
        "\treturn ret;\n"
        "}\n"
    )
    if old_tail not in content:
        print("[!] throne_tracker.c tail anchor not found!")
        return False
    content = content.replace(old_tail, new_tail, 1)

    with open(path, "w") as f:
        f.write(content)
    print("[+] throne_tracker.c: returns -ENOENT when packages.list missing")
    return True


def patch_setuid():
    path = "KernelSU-Next/kernel/hook/setuid_hook.c"
    with open(path, "r") as f:
        content = f.read()

    if "THRONE_RETRY_V9" in content:
        print("[-] setuid_hook.c already patched (v9)")
        return True

    old_inc = '#include "manager/throne_tracker.h"\n'
    new_inc = (
        '#include "manager/throne_tracker.h"\n'
        '#include "manager/manager_observer.h"\n'
    )
    if old_inc not in content:
        print("[!] setuid_hook.c include anchor (throne_tracker) not found!")
        return False
    content = content.replace(old_inc, new_inc, 1)

    old_block = (
        "    /* THRONE_BOOTSTRAP: no manager registered yet (fresh install, built-in\n"
        "     * driver, no ksud on /data/adb). Bounded search-and-crown on app\n"
        "     * spawns; the spawn that is the manager is crowned and gets its\n"
        "     * driver fd in the same call below. */\n"
        "    static int throne_tries = 0;\n"
        "    if (unlikely(!ksu_is_manager_appid_valid()) && throne_tries < 10) {\n"
        "        throne_tries++;\n"
        "        track_throne(false);\n"
        "    }\n"
    )
    new_block = (
        "    /* THRONE_BOOTSTRAP + THRONE_RETRY_V9: no manager registered yet\n"
        "     * (fresh install, built-in driver). PackageManagerService writes\n"
        "     * packages.list SECONDS after the first app spawns, so early\n"
        "     * attempts fail with -ENOENT - those are free retries. Only real\n"
        "     * searches (the list existed) count against the cap; the spawn\n"
        "     * that is the manager is crowned and gets its driver fd in the\n"
        "     * same call below. */\n"
        "    static int throne_failures = 0;\n"
        "    static bool observer_started = false;\n"
        "    if (unlikely(!observer_started)) {\n"
        "        observer_started = true;\n"
        "        ksu_observer_init();\n"
        "    }\n"
        "    if (unlikely(!ksu_is_manager_appid_valid()) && throne_failures < 20) {\n"
        "        int terr = track_throne(false);\n"
        "        if (terr != -ENOENT) {\n"
        "            if (!ksu_is_manager_appid_valid())\n"
        "                throne_failures++;\n"
        "            else\n"
        "                ksu_load_allow_list();\n"
        "        }\n"
        "    }\n"
    )
    if old_block not in content:
        print("[!] setuid_hook.c THRONE_BOOTSTRAP block not found!")
        return False
    content = content.replace(old_block, new_block, 1)

    with open(path, "w") as f:
        f.write(content)
    print("[+] setuid_hook.c: ENOENT-free retry + observer init + allowlist load")
    return True


if __name__ == "__main__":
    ok = patch_header() and patch_impl() and patch_setuid()
    if not ok:
        sys.exit(1)
