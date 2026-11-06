#!/usr/bin/env python3
"""Insert the sys_read (init.rc fops-proxy) manual hook into fs/read_write.c.
This is REQUIRED for the injected KernelSU RC (which starts /data/adb/ksu/bin/ksud
via init.rc) to actually run: ksu_handle_sys_read() triggers read_proxy() when init
reads init.rc.
Idempotent. Marker-free (guards on the call-site text itself).
Run from the kernel source root.
"""
import re
import sys

p = "fs/read_write.c"
try:
    s = open(p).read()
except FileNotFoundError:
    print("[!] fs/read_write.c not found")
    sys.exit(1)

if "ksu_handle_sys_read(fd)" in s:
    print("[skip] read_write.c already has sys_read hook")
    sys.exit(0)

decl = "extern void ksu_handle_sys_read(unsigned int fd);\n"
pos = s.rfind("#include")
if pos < 0:
    print("[!] no #include found"); sys.exit(1)
e = s.find("\n", pos)
if e < 0:
    e = len(s)
s = s[:e + 1] + decl + s[e + 1:]

pattern = r"SYSCALL_DEFINE3\(read, unsigned int, fd, char __user \*, buf, size_t, count\)"
m = re.search(pattern, s)
if not m:
    print("[!] read syscall signature not found"); sys.exit(1)
brace = s.find("{", m.end())
if brace < 0:
    print("[!] opening brace not found"); sys.exit(1)

s = s[:brace + 1] + "\n\tksu_handle_sys_read(fd);\n" + s[brace + 1:]
open(p, "w").write(s)
print("[ok] sys_read hook inserted in fs/read_write.c")
