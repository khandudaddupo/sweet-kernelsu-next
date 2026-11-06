#!/usr/bin/env python3
"""Backport path_umount (upstream 5.9) into 4.14 fs/namespace.c. Idempotent."""
import sys

f = "fs/namespace.c"
s = open(f).read()
if "int path_umount(" in s:
    print("path_umount already present")
    sys.exit(0)
anchor = "SYSCALL_DEFINE2(umount"
if anchor not in s:
    print("umount anchor NOT FOUND"); sys.exit(1)
code = """
static int can_umount(const struct path *path, int flags)
{
	struct mount *mnt = real_mount(path->mnt);

	if (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
		return -EINVAL;
	if (!may_mount())
		return -EPERM;
	if (path->dentry != path->mnt->mnt_root)
		return -EINVAL;
	if (!check_mnt(mnt))
		return -EINVAL;
	if (mnt->mnt.mnt_flags & MNT_LOCKED)
		return -EINVAL;
	if (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
		return -EPERM;
	return 0;
}

int path_umount(struct path *path, int flags)
{
	struct mount *mnt = real_mount(path->mnt);
	int ret;

	ret = can_umount(path, flags);
	if (!ret)
		ret = do_umount(mnt, flags);

	dput(path->dentry);
	mntput_no_expire(mnt);
	return ret;
}

"""
i = s.index(anchor)
open(f, "w").write(s[:i] + code + s[i:])
print("path_umount backported")
