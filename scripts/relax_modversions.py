#!/usr/bin/env python3
"""Let stock MIUI vendor .ko modules load on a kernel rebuilt from Xiaomi's public source.

The public sweet-r-oss tree yields different modversions CRCs (e.g. module_layout) than
Xiaomi's internal build, so every vendor module (audio, wlan, fingerprint) is refused with
"disagrees about version of symbol". This accepts CRC mismatches with a warning, and adds a
guard that still refuses any module whose struct module size differs from this kernel's,
which is the layout mismatch that would actually corrupt memory.
Run from the kernel source root. Exits non-zero if an anchor is missing.
"""
import sys

f = "kernel/module.c"
s = open(f).read()
MARK = "/* RELAX_MODVERSIONS */"
if MARK in s:
    print("already patched"); sys.exit(0)

old_bad = ('bad_version:\n\tpr_warn("%s: disagrees about version of symbol %s\\n",\n'
           '\t       info->name, symname);\n\treturn 0;\n}')
new_bad = ('bad_version:\n\t' + MARK + '\n\tpr_warn("%s: disagrees about version of symbol %s (accepted)\\n",\n'
           '\t       info->name, symname);\n\treturn 1;\n}')
if old_bad not in s:
    print("bad_version anchor NOT FOUND"); sys.exit(1)
s = s.replace(old_bad, new_bad, 1)

old_mod = ('\t/* This is temporary: point mod into copy of data. */\n'
           '\tmod = (void *)info->sechdrs[info->index.mod].sh_addr;\n')
guard = (old_mod +
         '\tif (info->sechdrs[info->index.mod].sh_size != sizeof(struct module)) {\n'
         '\t\tpr_err("%s: struct module size %llu != kernel %zu, refusing\\n",\n'
         '\t\t       info->name ?: "?",\n'
         '\t\t       (unsigned long long)info->sechdrs[info->index.mod].sh_size,\n'
         '\t\t       sizeof(struct module));\n'
         '\t\treturn ERR_PTR(-ENOEXEC);\n'
         '\t}\n')
if s.count(old_mod) != 1:
    print("this_module anchor count != 1:", s.count(old_mod)); sys.exit(1)
s = s.replace(old_mod, guard, 1)
open(f, "w").write(s)
print("modversions relaxed + struct module size guard added")
