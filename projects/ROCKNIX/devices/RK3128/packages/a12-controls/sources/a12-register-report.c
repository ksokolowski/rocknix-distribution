// SPDX-License-Identifier: GPL-2.0-or-later
/* Read-only RK3128 snapshots, including GPIO outputs not owned by a driver. */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static int report_bank(int fd, uint32_t base, const char *name,
		       const unsigned int *offsets, size_t count)
{
	volatile uint32_t *registers;
	size_t i;

	registers = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, base);
	if (registers == MAP_FAILED) {
		fprintf(stderr, "%s: %s\n", name, strerror(errno));
		return 1;
	}
	printf("%s (0x%08x):\n", name, base);
	for (i = 0; i < count; i++)
		printf("%03x: %08x\n", offsets[i], registers[offsets[i] / 4]);
	munmap((void *)registers, 4096);
	return 0;
}

int main(void)
{
	/* GPIO v1: output latch, direction (1 = output), physical input. */
	static const unsigned int gpio_offsets[] = { 0x000, 0x004, 0x050 };
	static const uint32_t gpio_bases[] = {
		0x2007c000, 0x20080000, 0x20084000, 0x20088000
	};
	/* CRU: DPLL, PLL mode, DDR/bus clock selection, gates and resets.
	 * RK2928_PLL_CON(4..6), MODE_CON and CLKSEL_CON(26) independently
	 * expose firmware DDR changes without relying on cached clock rates.
	 */
	static const unsigned int cru_offsets[] = {
		0x010, 0x014, 0x018, 0x040, 0x0ac,
		0x044, 0x084, 0x088, 0x08c, 0x090, 0x094, 0x098,
		0x0d0, 0x0d4, 0x0d8, 0x0dc, 0x0e0, 0x0e4,
		0x0e8, 0x0ec, 0x0f0, 0x0f4, 0x0f8, 0x0fc,
		0x110, 0x114, 0x118, 0x11c, 0x120, 0x124
	};
	/* I2S control/status only; never read the receive FIFO data register. */
	static const unsigned int i2s_offsets[] = {
		0x000, 0x004, 0x008, 0x00c, 0x010, 0x01c
	};
	/* Firmware DDR geometry: RK3128 U-Boot reads OS_REG1 and OS_REG2.
	 * These software scratch registers are not a physical RAM size test.
	 */
	static const unsigned int grf_ddr_offsets[] = {
		0x1c8, 0x1cc, 0x1d0, 0x1d4, 0x1d8, 0x1dc, 0x1e0, 0x1e4
	};
	/* VOP (RK3036 layout): SYS_CTRL, DSP_CTRL0/1 (out_mode, dither, pin
	 * polarity), AXI_BUS_CTRL (rgb/lvds enable and dclk polarity), window 0,
	 * display timings, CFG_DONE and VERSION_INFO.
	 */
	static const unsigned int vop_offsets[] = {
		0x000, 0x004, 0x008, 0x02c, 0x030, 0x034, 0x038, 0x03c,
		0x06c, 0x070, 0x074, 0x078, 0x090, 0x094
	};
	int fd, result = 0;
	size_t i;
	char name[16];

	fd = open("/dev/mem", O_RDONLY | O_SYNC | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "/dev/mem: %s\n", strerror(errno));
		return 1;
	}
	for (i = 0; i < sizeof(gpio_bases) / sizeof(gpio_bases[0]); i++) {
		snprintf(name, sizeof(name), "GPIO%zu", i);
		result |= report_bank(fd, gpio_bases[i], name, gpio_offsets,
				      sizeof(gpio_offsets) / sizeof(gpio_offsets[0]));
	}
	result |= report_bank(fd, 0x20000000, "CRU", cru_offsets,
			      sizeof(cru_offsets) / sizeof(cru_offsets[0]));
	result |= report_bank(fd, 0x10200000, "I2S", i2s_offsets,
			      sizeof(i2s_offsets) / sizeof(i2s_offsets[0]));
	result |= report_bank(fd, 0x20008000, "GRF DDR metadata", grf_ddr_offsets,
			      sizeof(grf_ddr_offsets) / sizeof(grf_ddr_offsets[0]));
	result |= report_bank(fd, 0x1010e000, "VOP", vop_offsets,
			      sizeof(vop_offsets) / sizeof(vop_offsets[0]));
	close(fd);
	return result;
}
