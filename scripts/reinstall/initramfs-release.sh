#!/bin/sh
# Run first in init-bottom, before switch-root can hide the ISO source mount.
case " $(cat /proc/cmdline) " in *" spring-reset-release "*) ;; *) exit 0 ;; esac
case " $(cat /proc/cmdline) " in *" toram "*) ;; *) exit 1 ;; esac
fail() {
    echo reset_initramfs_media_release_FAIL >&2
    reboot -f
    exit 1
}
awk -v nextroot="${rootmnt:-/root}/cdrom" '
    ($2 == "/cdrom" || $2 == nextroot) && $3 == "tmpfs" { found=1 }
    END { exit !found }
' /proc/mounts || fail
for backing in /sys/block/loop*/loop/backing_file; do
    test -r "$backing" || continue
    case "$(cat "$backing")" in
        /isodevice/*)
            name=${backing#/sys/block/}; name=${name%%/*}
            losetup -d "/dev/$name" || fail
            ;;
    esac
done
if awk '$2 == "/isodevice" { found=1 } END { exit !found }' /proc/mounts; then
    umount /isodevice || fail
fi
echo reset_initramfs_media_release_PASS
printf 'PASS\n' >/run/reset-initramfs-release
