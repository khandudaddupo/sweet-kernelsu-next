#!/usr/bin/env python3
"""v11 FINAL ZYGOTE DELAY - loop-rebreak: replaces v10's exec-sleep with an
init-BUILTIN `wait`, removing the fork/exec that raced with Zygisk Next's
exec inline-hook arming in init (root cause of the recurring 5-6 bootloops:
init died when a hook commit landed inside a fresh init exec).

Design (all inside the kernel-merged KSU rc `on post-fs-data` section,
which RUNS FIRST in init's serial post-fs-data queue):

  1) BOOTLOOP BREAKER exec (~4.8s, BEFORE zn-daemon arms init hooks):
       sh -c "n=$(cat /data/adb/.loopcnt 2>/dev/null); [ -z "$n" ] && n=0;
              n=$((n+1)); echo $n > /data/adb/.loopcnt;
              if [ $n -ge 8 ]; then for d in /data/adb/modules/*/; do
                  touch $d/disable; done;
                  echo breaker_$n >> /data/adb/.breaker.log; fi"
     Every boot attempt increments .loopcnt; a COMPLETED boot resets it via
     boot-completed.d/02_reset_loopcnt.sh (deploy on device). 8 consecutive
     non-completed boots => all modules get `disable` markers => the next
     boot is clean (root cause module faded out). Manual re-enable after.
     This exec runs BEFORE the hook arming window => no race.

  2) ZYGOTE DELAY wait (init builtin, NO fork/exec at all):
       wait /data/adb/.zn_delay_never 1000
     Blocks init's serial queue ~1s while zygiskd arms its hooks inside
     init (arming happens during the wait, ksudaemon runs concurrently) =>
     the never-exists path guarantees a hard 1.0s delay, zygote exec comes
     after arming with zero exec-window races. Holds for MIUI 13-15.
"""

OLD_SEQ = \
	'\t"on post-fs-data\\n"\n' \
	'\t"    start logd\\n"\n' \
	'\t"    start ksu_pfsd\\n"\n'

BREAKER_C = (
	'\t"    exec u:r:" KERNEL_SU_DOMAIN ":s0 root -- /system/bin/sh -c \\"'
	'n=$(cat /data/adb/.loopcnt 2>/dev/null); '
	'[ -z \\"$n\\" ] && n=0; '
	'n=$((n+1)); '
	'echo $n > /data/adb/.loopcnt; '
	'if [ $n -ge 8 ]; then '
	'for d in /data/adb/modules/*/; do touch $d/disable; done; '
	'echo breaker_fired_$n >> /data/adb/.breaker.log; '
	'fi\\"\\n"\n'
)

WAIT_C = \
	'\t// v11 ZYGOTE DELAY (no-exec): hold init\'s serial post-fs-data queue\n' \
	'\t// 1s via the init `wait` builtin while zn-daemon arms its hooks inside\n' \
	'\t// init. Replaces v10\'s `exec ... sleep 1` (that exec itself raced the\n' \
	'\t// hook arming and crashed init = the recurring bootloops).\n' \
	'\t"    wait /data/adb/.zn_delay_never 1000\\n"\n'


def patch():
    path = "KernelSU-Next/kernel/runtime/ksud_integration.c"
    with open(path, "r") as f:
        content = f.read()

    if "ZYGOTE DELAY V11" in content:
        print("[-] v11 delay already present")
        return True

    if OLD_SEQ not in content:
        print("[!] PATCH FAILED - post-fs-data start sequence not found "
              "(run ksu_fix_init_rc.py first!)")
        return False

    new_seq = OLD_SEQ + \
        '\t// v11 BOOTLOOP BREAKER: count boot attempts; 8 consecutive\n' \
        '\t// non-completed boots => disable all modules (phone boots clean).\n' \
        '\t// Runs BEFORE zn-daemon arms hooks => never races.\n' \
        + BREAKER_C + WAIT_C

    content = content.replace(OLD_SEQ, new_seq, 1)
    with open(path, "w") as f:
        f.write(content)

    print("[+] v11 FINAL delay added: init builtin wait + bootloop breaker")
    return True


if __name__ == "__main__":
    if not patch():
        import sys
        sys.exit(1)
