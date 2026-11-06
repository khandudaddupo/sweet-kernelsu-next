#!/usr/bin/env python3
"""SELINUX EARLY SETUP for manual-hook KSU-Next builds (4.14).

Problem: upstream runs apply_kernelsu_rules() + cache_sid() + setup_ksu_cred()
from the execve-based /system/bin/init second-stage detection
(ksu_initialize_selinux_tw_func in ksu_handle_execveat_ksud). Manual-hook
builds on this device must NOT hook execveat_ksud (crash), so that path never
runs: ksu_cred keeps the initial kernel SID and the KSU SELinux rules are
never injected. Consequences:
  - throne search (track_throne -> filp_open /data/system/packages.list,
    iterate /data/app) under override_creds(ksu_cred) is denied by SELinux,
    so the manager is never crowned, the setresuid hook never installs the
    driver fd, and the manager stays seccomp-blocked ("Unsupported").
  - allowlist load and module rc read would be denied the same way.

Fix: init reads /system/etc/init/hw/init.rc AFTER selinux_load_policy() and
BEFORE any app is spawned. Hook that exact moment (manual-hook builds only,
non-atomic context) and run the same three setup calls in the same order
upstream uses, so ksu_cred becomes u:r:ksu:s0 on a live loaded policy.
"""

import sys


def patch():
    path = "KernelSU-Next/kernel/runtime/ksud_integration.c"
    with open(path, "r") as f:
        content = f.read()

    if "SELINUX_EARLY_SETUP" in content:
        print("[-] Already patched")
        return True

    old = (
        "    rc_hooked = true;\n"
        "\n"
        "    // now we can sure that the init process is reading\n"
    )

    new = (
        "    rc_hooked = true;\n"
        "\n"
        "#ifndef KSU_KPROBES_HOOK\n"
        "    /* SELINUX_EARLY_SETUP: manual-hook builds have no execve-based\n"
        "     * second-stage detection, so apply_kernelsu_rules/cache_sid/\n"
        "     * setup_ksu_cred would never run and ksu_cred would keep the\n"
        "     * initial kernel SID - every ksu_cred file access (throne\n"
        "     * search, allowlist load) would be denied by SELinux. init\n"
        "     * reads init.rc after the policy is loaded and before any app\n"
        "     * is spawned, so set the KSU SELinux state up here. */\n"
        "    apply_kernelsu_rules();\n"
        "    cache_sid();\n"
        "    setup_ksu_cred();\n"
        "#endif\n"
        "\n"
        "    // now we can sure that the init process is reading\n"
    )

    if old not in content:
        print("[!] PATCH FAILED - anchor not found!")
        return False

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)

    print("[+] SELinux early setup patch applied!")
    return True


if __name__ == "__main__":
    if not patch():
        sys.exit(1)
