#!/usr/bin/env python3
"""v10 ZYGOTE DELAY: fix Zygisk Next's missing zygote injection.

Diagnosis (boot log, kernel timestamps):
  5.107  init: starting service 'zygote'...
  5.226  zn-daemon64: execve hook installed   (armed AFTER zygote exec!)
  -> zygote exec missed by the inline hooks in init
  -> `zygiskd64 status` shows zygote_states:0, Injected Processes: 0
  -> HMA-OSS zygisk never activates ("System service not running").

Fix: block init's SERIAL action queue for 1s in the `on post-fs-data`
section of the kernel-merged KSU rc (these appends run FIRST in the
post-fs-data queue - empirically ksu_pfsd starts before the imported
rc post-fs-data actions), delaying the zygote start until after zn
hooks are armed. Guarded by test -d so boots without Zimin's Zygisk
module only pause init for a no-op shell exit.
"""

OLD_SEQ = \
	'\t"on post-fs-data\\n"\n' \
	'\t"    start logd\\n"\n' \
	'\t"    start ksu_pfsd\\n"\n'

NEW_SEQ = \
	'\t"on post-fs-data\\n"\n' \
	'\t"    start logd\\n"\n' \
	'\t"    start ksu_pfsd\\n"\n' \
	'\t// v10 ZYGOTE DELAY: zn-daemon arms init hooks ~300ms after the\n' \
	'\t// post-fs-data trigger; init execs the zygote ~250ms in -> race lost.\n' \
	'\t// here - block the serial queue 1s when Zygisk Next is installed.\n' \
	'\t"    exec u:r:" KERNEL_SU_DOMAIN ":s0 root -- /system/bin/sh -c \\"test -d /data/adb/modules/zygisksu && /system/bin/sleep 1\\"\\n"\n'


def patch():
    path = "KernelSU-Next/kernel/runtime/ksud_integration.c"
    with open(path, "r") as f:
        content = f.read()

    if "ZYGOTE DELAY" in content:
        print("[-] zygote delay already present")
        return True

    if OLD_SEQ not in content:
        print("[!] PATCH FAILED - post-fs-data start sequence not found "
              "(run ksu_fix_init_rc.py first!)")
        return False

    content = content.replace(OLD_SEQ, NEW_SEQ, 1)
    with open(path, "w") as f:
        f.write(content)

    print("[+] v10 ZYGOTE DELAY added: post-fs-data queue blocks 1s when "
          "/data/adb/modules/zygisksu exists")
    return True


if __name__ == "__main__":
    if not patch():
        import sys
        sys.exit(1)
