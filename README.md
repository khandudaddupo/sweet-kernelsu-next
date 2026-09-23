# sweet-kernelsu-next

Redmi Note 10 Pro (`sweet` / `sweetin`, M2101K6P) custom kernel:
stock Xiaomi `sweet-r-oss` (`sweet_user_defconfig`, 4.14) + KernelSU-Next (default `v3.4.0`).

## Build

Manual trigger with custom KSU tag: Actions → "Build sweet KernelSU-Next" → Run workflow → set `ksu_tag`.

Auto-builds on push to `main`. Artifact: `sweet-kernelsu-next-<tag>` with
`Image.gz` (or `Image`), `dtb*`, `dtbo.img` (if produced), `kernel_config_used`,
`kernel_commit.txt`, `build-info.txt`, `build.log` (14-day retention).

## Flash (after verifying artifact)

Built kernel is NOT a flashable boot.img yet. Repack with the stock
V14.0.1.0.TKFINXM ramdisk (verified `stock_boot_V14.0.1.0.TKFINXM.img`,
sha `2316fbd3…`) via `mkbootimg`, then `fastboot flash boot` from bootloader.
Keep the stock boot.img backup; a bad kernel = bootloop → reflash stock.
