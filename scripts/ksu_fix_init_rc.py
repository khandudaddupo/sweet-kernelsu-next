#!/usr/bin/env python3
"""FIX the injected init.rc for KernelSU-Next manual-hook builds.

Upstream KERNEL_SU_RC uses blocking `exec u:r:ksu:s0 root -- ksud ...` lines.
On this device blocking exec made init wait forever (MI logo hang), so a
previous fix sed-replaced `exec u:r:` with `exec_start u:r:` — but Android
init's `exec_start` takes a SERVICE NAME, not a command, so those lines are
a silent no-op: ksud NEVER starts at boot even when it exists.

Proper async fix: define oneshot services (non-blocking `start`), so init
never waits on ksud, and ksud actually runs when /data/adb/ksu/bin/ksud
exists (installed by the manager or manually). The kernel-side crown does
not depend on ksud; this restores allowlist load + boot events + module
mounting on every boot.
"""

import sys

OLD_RC_HEAD = '''static const char KERNEL_SU_RC[] =
	"\\n"

	"on post-fs-data\\n"
	"    start logd\\n"
	// We should wait for the post-fs-data finish
	"    exec_start u:r:" KERNEL_SU_DOMAIN ":s0 root -- " KSUD_PATH " post-fs-data\\n"
	"\\n"

	"on nonencrypted\\n"
	"    exec_start u:r:" KERNEL_SU_DOMAIN ":s0 root -- " KSUD_PATH " services\\n"
	"\\n"

	"on property:vold.decrypt=trigger_restart_framework\\n"
	"    exec_start u:r:" KERNEL_SU_DOMAIN ":s0 root -- " KSUD_PATH " services\\n"
	"\\n"

	"on property:sys.boot_completed=1\\n"
	"    exec_start u:r:" KERNEL_SU_DOMAIN ":s0 root -- " KSUD_PATH " boot-completed\\n"
	"\\n"

	"\\n";
'''

NEW_RC = '''static const char KERNEL_SU_RC[] =
	"\\n"

	"service ksu_pfsd " KSUD_PATH " post-fs-data\\n"
	"    user root\\n"
	"    seclabel u:r:" KERNEL_SU_DOMAIN ":s0\\n"
	"    oneshot\\n"
	"    disabled\\n"
	"\\n"

	"service ksu_svcs " KSUD_PATH " services\\n"
	"    user root\\n"
	"    seclabel u:r:" KERNEL_SU_DOMAIN ":s0\\n"
	"    oneshot\\n"
	"    disabled\\n"
	"\\n"

	"service ksu_bcomp " KSUD_PATH " boot-completed\\n"
	"    user root\\n"
	"    seclabel u:r:" KERNEL_SU_DOMAIN ":s0\\n"
	"    oneshot\\n"
	"    disabled\\n"
	"\\n"

	"on post-fs-data\\n"
	"    start logd\\n"
	"    start ksu_pfsd\\n"
	"\\n"

	"on nonencrypted\\n"
	"    start ksu_svcs\\n"
	"\\n"

	"on property:vold.decrypt=trigger_restart_framework\\n"
	"    start ksu_svcs\\n"
	"\\n"

	"on property:sys.boot_completed=1\\n"
	"    start ksu_bcomp\\n"
	"\\n"

	"\\n";
'''


def patch():
    path = "KernelSU-Next/kernel/runtime/ksud_integration.c"
    with open(path, "r") as f:
        content = f.read()

    if "ksu_pfsd" in content:
        print("[-] RC already fixed")
        return True

    if OLD_RC_HEAD not in content:
        print("[!] PATCH FAILED - KERNEL_SU_RC (exec_start form) not found!")
        return False

    content = content.replace(OLD_RC_HEAD, NEW_RC, 1)
    with open(path, "w") as f:
        f.write(content)

    print("[+] KERNEL_SU_RC fixed: async service definitions (non-blocking start)")
    return True


if __name__ == "__main__":
    if not patch():
        sys.exit(1)
