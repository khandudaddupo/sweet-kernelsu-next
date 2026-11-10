#!/usr/bin/env python3
"""Baked-crown patch (v15): kernel init writes the manager appid for the
user's spoofed KernelSU-Next manager APK. Zero I/O, zero race — the crown
exists from the moment the kernel boots, no throne/scan needed.
(kernelsu-Next v3.4.0-legacy: ksu_manager_appid global + inline setter in
manager/manager_identity.h; supercall.c already includes that header.)"""
import sys

Baked = 10296

def main():
    path = sys.argv[0] if False else "KernelSU-Next/kernel/supercall/supercall.c"
    c = open(path).read()
    anchor = (
        "void __init ksu_supercalls_init(void)\n"
        "{\n"
        "\tint i;\n"
    )
    repl = (
        "void __init ksu_supercalls_init(void)\n"
        "{\n"
        f"\t/* BAKED_CROWN v15: crown the spoofed manager (uid appid {Baked}) at kernel init */\n"
        f"\tksu_set_manager_appid({Baked});\n"
        "\tint i;\n"
    )
    if "BAKED_CROWN v15" in c:
        print("[-] already patched: baked crown")
        return
    if anchor not in c:
        print("[!] anchor not found in supercall.c")
        sys.exit(1)
    c = c.replace(anchor, repl, 1)
    open(path, "w").write(c)
    print(f"[+] BAKED_CROWN v15: ksu_set_manager_appid({Baked}) added to ksu_supercalls_init")

if __name__ == "__main__":
    main()
