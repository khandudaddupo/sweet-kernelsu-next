#!/usr/bin/env python3
"""
KernelSU-Next v3.4.2 -> Linux 4.14 compat patch (sweet / Redmi Note 10 Pro).

Idempotent. Run from anywhere; edits the KernelSU-Next kernel tree in-place.

Fixes:
1. supercall/supercall.c: TWA_RESUME was added in 5.8; on 4.14 task_work_add's
   third param is a plain bool (true == TWA_RESUME semantic: wake on return).
2. selinux/sepolicy.c: add_filename_trans was rewritten 5.7+ style with no
   fallback. Port the proven v1.0.9 three-way guard (>=5.9 / >=5.7 / <5.7).
   4.14 has struct filename_trans {stype,ttype,tclass(u16),name} and
   db->filename_trans is a hashtab pointer, and there is no stypes bitmap in
   the datum -> filename_trans_ttypes route.
"""
import re
import sys

kernel_dir = sys.argv[1] if len(sys.argv) > 1 else "."

# ---------------------------------------------------------------- supercall.c
f = kernel_dir + "/supercall/supercall.c"
s = open(f).read()
changed = False

if "KSU_TWA_RESUME" not in s:
    anchor = "#include <linux/task_work.h>"
    if anchor not in s:
        print("supercall.c: task_work.h include not found!"); sys.exit(1)
    guard = (
        "#include <linux/version.h>\n"
        "\n"
        "// TWA_RESUME was introduced in 5.8; before that task_work_add takes a\n"
        "// plain bool (true = notify on return to userspace, same semantic).\n"
        "#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)\n"
        "#define KSU_TWA_RESUME true\n"
        "#else\n"
        "#define KSU_TWA_RESUME TWA_RESUME\n"
        "#endif\n"
    )
    s = s.replace(anchor, anchor + "\n" + guard, 1)
    changed = True
s2 = s.replace("task_work_add(current, &tw->cb, TWA_RESUME)",
               "task_work_add(current, &tw->cb, KSU_TWA_RESUME)")
if s2 != s:
    changed = True
    s = s2
if changed:
    open(f, "w").write(s)
    print("supercall.c: TWA_RESUME guard applied")
else:
    print("supercall.c: already patched")

# ---------------------------------------------------------------- sulog/event.c
f = kernel_dir + "/sulog/event.c"
s = open(f).read()
if "struct timespec64 ts;" in s and "struct timespec ts;" not in s:
    s = s.replace(
        "    struct timespec64 ts;\n",
        "#if KERNEL_VERSION(4, 19, 0) <= LINUX_VERSION_CODE\n"
        "    struct timespec64 ts;\n"
        "#else\n"
        "    struct timespec ts;  // 4.14: get_monotonic_boottime takes timespec\n"
        "#endif\n",
    )
    open(f, "w").write(s)
    print("sulog/event.c: timespec64 -> guarded timespec fix applied")
else:
    print("sulog/event.c: already patched")

# ---------------------------------------------------------------- separator
f = kernel_dir + "/Kconfig"
s = open(f).read()
if "\tdepends on KPROBES && EXT4_FS" in s:
    # KPROBES stays OFF on this kernel (stock vendor .ko struct match);
    # v3.4.2 hooks work via syscall-table patching + tracepoints, not kprobes.
    s = s.replace(
        "\tdepends on KPROBES && EXT4_FS\n", "\tdepends on EXT4_FS\n", 1
    )
    open(f, "w").write(s)
    print("Kconfig: 'depends on KPROBES' removed from CONFIG_KSU")
else:
    print("Kconfig: already patched")

# ---------------------------------------------------------------- sepolicy.c
f = kernel_dir + "/selinux/sepolicy.c"
s = open(f).read()

start_marker = "static bool add_filename_trans(struct policydb *db, const char *s,"
end_marker = "static bool add_genfscon(struct policydb *db"
first = s.index(start_marker)
defn = s.index(start_marker, first + 1)
end = s.index(end_marker, defn)

new_fn = r'''static bool add_filename_trans(struct policydb *db, const char *s,
                               const char *t, const char *c, const char *d,
                               const char *o)
{
    struct type_datum *src, *tgt, *def;
    struct class_datum *cls;

    src = symtab_search(&db->p_types, s);
    if (src == NULL) {
        pr_warn("source type %s does not exist\n", s);
        return false;
    }
    tgt = symtab_search(&db->p_types, t);
    if (tgt == NULL) {
        pr_warn("target type %s does not exist\n", t);
        return false;
    }
    cls = symtab_search(&db->p_classes, c);
    if (cls == NULL) {
        pr_warn("class %s does not exist\n", c);
        return false;
    }
    def = symtab_search(&db->p_types, d);
    if (def == NULL) {
        pr_warn("default type %s does not exist\n", d);
        return false;
    }

    // 5.7.0 replaced struct filename_trans with filename_trans_key + stypes
    // bitmap; below that, datum is {otype} and db tracks stypes globally.
#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 7, 0)
    struct filename_trans_key key;
    key.ttype = tgt->value;
    key.tclass = cls->value;
    key.name = (char *)o;

    struct filename_trans_datum *last = NULL;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)
    struct filename_trans_datum *trans =
        policydb_filenametr_search(db, &key);
#else
    struct filename_trans_datum *trans =
        hashtab_search(&db->filename_trans, &key);
#endif
    while (trans) {
        if (ebitmap_get_bit(&trans->stypes, src->value - 1)) {
            // Duplicate, overwrite existing data and return
            trans->otype = def->value;
            return true;
        }
        if (trans->otype == def->value)
            break;
        last = trans;
        trans = trans->next;
    }

    if (trans == NULL) {
        trans = (struct filename_trans_datum *)kcalloc(sizeof(*trans), 1,
                                                       GFP_ATOMIC);
        struct filename_trans_key *new_key =
            (struct filename_trans_key *)kmalloc(sizeof(*new_key),
                                                 GFP_ATOMIC);
        if (!trans || !new_key) {
            pr_err("add_filename_trans: alloc failed\n");
            return false;
        }
        *new_key = key;
        new_key->name = kstrdup(key.name, GFP_ATOMIC);
        trans->next = last;
        trans->otype = def->value;
        hashtab_insert(&db->filename_trans, new_key, trans,
                       filenametr_key_params);
    }

    db->compat_filename_trans_count++;
    return ebitmap_set_bit(&trans->stypes, src->value - 1, 1) == 0;
#else /* < 5.7.0 */
    struct filename_trans key;
    key.stype = 0;
    key.ttype = tgt->value;
    key.tclass = cls->value;
    key.name = (char *)o;

    struct filename_trans_datum *trans =
        hashtab_search(db->filename_trans, &key);

    if (trans == NULL) {
        trans = (struct filename_trans_datum *)kcalloc(sizeof(*trans), 1,
                                                       GFP_ATOMIC);
        if (!trans) {
            pr_err("add_filename_trans: Failed to alloc datum\n");
            return false;
        }
        struct filename_trans *new_key =
            (struct filename_trans *)kmalloc(sizeof(*new_key), GFP_ATOMIC);
        if (!new_key) {
            pr_err("add_filename_trans: Failed to alloc new_key\n");
            return false;
        }
        *new_key = key;
        new_key->name = kstrdup(key.name, GFP_ATOMIC);
        trans->otype = def->value;
        hashtab_insert(db->filename_trans, new_key, trans);
    }

    return ebitmap_set_bit(&db->filename_trans_ttypes, src->value - 1, 1) == 0;
#endif
}

'''

if "KERNEL_VERSION(5, 7, 0)" in s and s.count(start_marker) == 2 and end_marker in s:
    print("sepolicy.c: already patched")
    sys.exit(0)

if s.count(start_marker) == 2 and end_marker in s:
    s = s[:defn] + new_fn + s[end:]
    open(f, "w").write(s)
    print("sepolicy.c: add_filename_trans 3-way guard applied")
else:
    print("sepolicy.c: already patched or unexpected layout!")
    sys.exit(1)
