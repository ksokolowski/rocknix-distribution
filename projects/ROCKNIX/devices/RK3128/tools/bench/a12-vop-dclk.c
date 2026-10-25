// SPDX-License-Identifier: GPL-2.0-or-later
/* Runtime A/B of the RK3126 VOP RGB dclk polarity (AXI_BUS_CTRL bit 25).
 * KNULLI writes 0 for this panel (pixelclk-active = 1); mainline writes 1.
 * Changes last until the next modeset or reboot.
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define VOP_BASE 0x1010e000u
#define AXI_BUS_CTRL 0x2c
#define REG_CFG_DONE 0x90
#define RGB_EN (1u << 24)
#define RGB_DCLK_POL (1u << 25)
#define LVDS_EN (1u << 26)

static void show(const char *when, uint32_t value)
{
	printf("%s AXI_BUS_CTRL=0x%08x rgb_en=%u rgb_dclk_pol=%u lvds_en=%u\n", when, value,
	       !!(value & RGB_EN), !!(value & RGB_DCLK_POL), !!(value & LVDS_EN));
}

int main(int argc, char **argv)
{
	const char *path = "/dev/mem";
	off_t offset = VOP_BASE;
	volatile uint32_t *vop;
	uint32_t value;
	int fd, write_mode;

	if (argc == 4 && !strcmp(argv[2], "--file")) {
		path = argv[3];
		offset = 0;
	} else if (argc != 2) {
		fprintf(stderr, "usage: %s show|normal|invert [--file PATH]\n", argv[0]);
		return 2;
	}
	if (!strcmp(argv[1], "show"))
		write_mode = -1;
	else if (!strcmp(argv[1], "normal"))
		write_mode = 0;
	else if (!strcmp(argv[1], "invert"))
		write_mode = 1;
	else
		return 2;
	fd = open(path, (write_mode < 0 ? O_RDONLY : O_RDWR) | O_SYNC);
	if (fd < 0)
		return perror(path), 1;
	vop = mmap(NULL, 4096, write_mode < 0 ? PROT_READ : PROT_READ | PROT_WRITE,
		   MAP_SHARED, fd, offset);
	if (vop == MAP_FAILED)
		return perror("mmap"), 1;
	value = vop[AXI_BUS_CTRL / 4];
	show("before", value);
	if (write_mode >= 0) {
		value = write_mode ? value | RGB_DCLK_POL : value & ~RGB_DCLK_POL;
		vop[AXI_BUS_CTRL / 4] = value;
		vop[REG_CFG_DONE / 4] = 1;
		show("after ", vop[AXI_BUS_CTRL / 4]);
	}
	munmap((void *)vop, 4096);
	close(fd);
	return 0;
}
