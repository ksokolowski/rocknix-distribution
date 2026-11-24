// SPDX-License-Identifier: GPL-2.0+
/*
 * DRAM bank fixup based on arch/arm/mach-rockchip/sdram.c:
 * Copyright (C) 2017 Rockchip Electronics Co., Ltd.
 */

#include <config.h>
#include <dm.h>
#include <log.h>
#include <asm/cache.h>
#include <asm/global_data.h>
#include <asm/system.h>
#include <asm/u-boot.h>
#include <linux/errno.h>
#include <linux/sizes.h>
#include <power/regulator.h>

DECLARE_GLOBAL_DATA_PTR;

/*
 * rk3126_tee_ta_v2.01.bin reserves this range on the 256 MiB revision A.
 * These boundaries were read from the working vendor bootloader's Linux
 * handoff. Keep the rk3128-blobs version pinned when using this layout.
 */
#define A12_TEE_START	0x68400000UL
#define A12_TEE_END	0x69210000UL

int rockchip_dram_init_banksize_fixup(struct bd_info *bd)
{
	phys_addr_t top = CFG_SYS_SDRAM_BASE + gd->ram_size;

	if (gd->ram_size != SZ_256M) {
		log_err("A12 revision A requires 256 MiB DRAM\n");
		return -EINVAL;
	}

	bd->bi_dram[0].start = CFG_SYS_SDRAM_BASE;
	bd->bi_dram[0].size = A12_TEE_START - CFG_SYS_SDRAM_BASE;
	bd->bi_dram[1].start = A12_TEE_END;
	bd->bi_dram[1].size = top - A12_TEE_END;

	return 0;
}

void dram_bank_mmu_setup(int bank)
{
	phys_addr_t start, end;
	unsigned int section;

	if (!(gd->flags & GD_FLG_RELOC))
		return;
	start = gd->bd->bi_dram[bank].start;
	end = start + gd->bd->bi_dram[bank].size;

	/*
	 * Map complete sections inside each usable bank. The second bank is
	 * not section-aligned: truncating its size omits the final MiB, where
	 * U-Boot relocates, leaving it execute-never when the MMU is enabled.
	 * Round the start up to keep the TEE's final 64 KiB uncached and XN.
	 */
	for (section = (start + MMU_SECTION_SIZE - 1) >> MMU_SECTION_SHIFT;
	     section < (end >> MMU_SECTION_SHIFT); section++)
		set_section_dcache(section, DCACHE_DEFAULT_OPTION);
}

int rk_board_late_init(void)
{
	struct udevice *dev;
	int ret;

	ret = regulator_get_by_platname("pm-enable", &dev);
	if (ret)
		return ret;

	/* The regulator's post-probe hook already enables this boot-on rail. */
	ret = regulator_set_enable(dev, true);
	return ret == -EALREADY ? 0 : ret;
}
