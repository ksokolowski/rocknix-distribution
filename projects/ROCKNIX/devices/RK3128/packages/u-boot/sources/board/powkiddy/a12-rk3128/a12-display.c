// SPDX-License-Identifier: GPL-2.0+
/*
 * Powkiddy A12 revision A: RK3128 VOP (RK3036-family "VOP lite") on the
 * RGB666 panel through the TTL video PHY, for a logo before Linux (B3).
 *
 * DRAFT, NOT VERIFIED ON HARDWARE. Built only with CONFIG_A12_DISPLAY
 * (powkiddy-a12-display-rk3128_defconfig); the normal A12 U-Boot does not
 * contain it. Sources of each value:
 * - VOP registers and the enable order: Linux v7.1 rockchip_vop_reg.c
 *   (rk3036_*, rk3126_output) and rockchip_drm_vop.c vop_crtc_atomic_enable.
 * - RGB clock edge 0, P666 output with RGB888->RGB666 dithering: ROCKNIX
 *   kernel patches 0003 and 0008 (A12 panel samples on the rising edge).
 * - Mode: panel-a12 60-hblank timing (patch 0013), 54 MHz = GPLL 594 / 11.
 * - Panel power/reset timing: panel-a12 a12_prepare()/a12_enable().
 * - TTL PHY writes: a12-ttl-phy a12_ttl_power_on() (from the Rockchip
 *   vendor inno video combo PHY driver, Copyright (c) 2018 Rockchip
 *   Electronics Co. Ltd., GPL-2.0).
 * - CRU fields: Linux clk-rk3128.c (dclk_vop mux/div, gates).
 */

#include <dm.h>
#include <backlight.h>
#include <log.h>
#include <video.h>
#include <asm/gpio.h>
#include <asm/io.h>
#include <asm/arch-rockchip/cru_rk3128.h>
#include <asm/arch-rockchip/hardware.h>
#include <dm/ofnode.h>
#include <linux/bitops.h>
#include <linux/delay.h>
#include <linux/err.h>

#define A12_XRES	1024
#define A12_YRES	600

/* 60-hblank mode (panel-a12, patch 0013); negative H/V sync. */
#define A12_HSYNC_START	1184
#define A12_HSYNC_END	1194
#define A12_HTOTAL	1395
#define A12_VSYNC_START	612
#define A12_VSYNC_END	622
#define A12_VTOTAL	645
#define A12_DCLK_DIV	11	/* GPLL 594 MHz / 11 = 54 MHz */

/* RK3036-family VOP registers (Linux rockchip_vop_reg.h RK3036_*). */
#define VOP_SYS_CTRL		0x00
#define VOP_DSP_CTRL0		0x04
#define VOP_DSP_CTRL1		0x08
#define VOP_ALPHA_CTRL		0x14
#define VOP_WIN0_YRGB_MST	0x20
#define VOP_AXI_BUS_CTRL	0x2c
#define VOP_WIN0_VIR		0x30
#define VOP_WIN0_ACT_INFO	0x34
#define VOP_WIN0_DSP_INFO	0x38
#define VOP_WIN0_DSP_ST		0x3c
#define VOP_WIN0_SCL_FACTOR	0x40
#define VOP_HTOTAL_HS_END	0x6c
#define VOP_HACT_ST_END		0x70
#define VOP_VTOTAL_VS_END	0x74
#define VOP_VACT_ST_END		0x78
#define VOP_REG_CFG_DONE	0x90

#define SYS_WIN0_EN		BIT(0)
#define SYS_WIN0_FMT_MASK	(7 << 3)	/* 0 = ARGB8888 */
#define SYS_WIN0_RB_SWAP	BIT(15)
#define SYS_STANDBY		BIT(30)
#define CTRL0_OUT_MODE_MASK	0xf
#define CTRL0_OUT_MODE_P666	1		/* ROCKCHIP_OUT_MODE_P666 */
#define CTRL0_PIN_POL_MASK	(0xf << 4)	/* H/V sync positive bits: 0 here */
#define CTRL0_DITHER_MODE_666	BIT(10)		/* RGB888_TO_RGB666 */
#define CTRL0_DITHER_EN		BIT(11)
#define CTRL0_DITHER_SEL	BIT(27)		/* 0 = allegro */
#define CTRL1_DSP_BLANK		BIT(24)
#define AXI_HDMI_EN		BIT(22)
#define AXI_RGB_EN		BIT(24)
#define AXI_RGB_DCLK_POL	BIT(25)
#define AXI_MIPI_EN		BIT(28)
#define SCL_FACTOR_1		0x1000

/* TTL PHY (a12-ttl-phy.c): PHY block and DSI host offsets. */
#define PHY_ANALOG0		0x000
#define PHY_LVDS_RESET		0x380
#define PHY_LVDS_ENABLE		0x384
#define PHY_LVDS_MODE		0x38c
#define PHY_LVDS_POWER		0x3ac
#define HOST_DSI_PHY_RSTZ	0x0a0

struct a12_display_priv {
	void __iomem *vop;
};

static void a12_clocks(struct rk3128_cru *cru)
{
	/* dclk_vop: mux GPLL (1), divider 11 (clksel27 [1:0], [15:8]). The
	 * mainline clk driver would reprogram CPLL instead; leave CPLL alone. */
	rk_clrsetreg(&cru->cru_clksel_con[27], 0x3 | 0xff << 8, 1 | (A12_DCLK_DIV - 1) << 8);
	/* Ungate hclk_vio (gate0.11), aclk_vio0/dclk_vop (gate3.0/1), the PHY
	 * 24 MHz reference (gate2.15), pclk_mipiphy (gate5.0), aclk/hclk_lcdc0
	 * (gate6.0/1) and pclk_mipi (gate9.6). A set gate bit disables. */
	rk_clrreg(&cru->cru_clkgate_con[0], BIT(11));
	rk_clrreg(&cru->cru_clkgate_con[2], BIT(15));
	rk_clrreg(&cru->cru_clkgate_con[3], BIT(0) | BIT(1));
	rk_clrreg(&cru->cru_clkgate_con[5], BIT(0));
	rk_clrreg(&cru->cru_clkgate_con[6], BIT(0) | BIT(1));
	rk_clrreg(&cru->cru_clkgate_con[9], BIT(6));
}

static int a12_ttl_phy_on(void)
{
	ofnode node = ofnode_by_compatible(ofnode_null(), "powkiddy,a12-rev-a-ttl-phy");
	void __iomem *phy, *host;

	if (!ofnode_valid(node))
		return -ENODEV;
	phy = (void __iomem *)ofnode_get_addr_index(node, 0);
	host = (void __iomem *)ofnode_get_addr_index(node, 1);
	if (phy == (void __iomem *)FDT_ADDR_T_NONE || host == (void __iomem *)FDT_ADDR_T_NONE)
		return -EINVAL;

	/* Bandgap and analog block on, TTL output selected, then enable. */
	clrsetbits_le32(phy + PHY_ANALOG0, BIT(7) | GENMASK(1, 0), 1);
	clrsetbits_le32(phy + PHY_LVDS_MODE, GENMASK(2, 0), BIT(2));
	clrbits_le32(phy + PHY_LVDS_RESET, BIT(2));
	udelay(1);
	setbits_le32(phy + PHY_LVDS_RESET, BIT(2));
	setbits_le32(phy + PHY_LVDS_ENABLE, BIT(7));
	setbits_le32(phy + PHY_LVDS_POWER, GENMASK(7, 3));
	setbits_le32(host + HOST_DSI_PHY_RSTZ, BIT(2));
	return 0;
}

static int a12_panel_on(ofnode panel)
{
	struct gpio_desc enable, reset;
	int ret;

	ret = gpio_request_by_name_nodev(panel, "enable-gpios", 0, &enable, GPIOD_IS_OUT);
	if (ret)
		return ret;
	ret = gpio_request_by_name_nodev(panel, "reset-gpios", 0, &reset, GPIOD_IS_OUT);
	if (ret)
		return ret;
	/* a12_prepare(): enable, 100 ms, reset pulse 60 ms, 1 s settle. */
	dm_gpio_set_value(&enable, 1);
	mdelay(100);
	dm_gpio_set_value(&reset, 1);
	mdelay(60);
	dm_gpio_set_value(&reset, 0);
	mdelay(1000);
	return 0;
}

static void a12_vop_start(void __iomem *vop, ulong fb)
{
	const u32 hsync_len = A12_HSYNC_END - A12_HSYNC_START;
	const u32 hact_st = A12_HTOTAL - A12_HSYNC_START;
	const u32 vsync_len = A12_VSYNC_END - A12_VSYNC_START;
	const u32 vact_st = A12_VTOTAL - A12_VSYNC_START;

	setbits_le32(vop + VOP_SYS_CTRL, SYS_STANDBY);

	clrsetbits_le32(vop + VOP_DSP_CTRL0,
			CTRL0_OUT_MODE_MASK | CTRL0_PIN_POL_MASK | CTRL0_DITHER_SEL,
			CTRL0_OUT_MODE_P666 | CTRL0_DITHER_MODE_666 | CTRL0_DITHER_EN);
	clrbits_le32(vop + VOP_DSP_CTRL1, CTRL1_DSP_BLANK);
	clrsetbits_le32(vop + VOP_AXI_BUS_CTRL, AXI_HDMI_EN | AXI_MIPI_EN | AXI_RGB_DCLK_POL, AXI_RGB_EN);

	writel(A12_HTOTAL << 16 | hsync_len, vop + VOP_HTOTAL_HS_END);
	writel(hact_st << 16 | (hact_st + A12_XRES), vop + VOP_HACT_ST_END);
	writel(A12_VTOTAL << 16 | vsync_len, vop + VOP_VTOTAL_VS_END);
	writel(vact_st << 16 | (vact_st + A12_YRES), vop + VOP_VACT_ST_END);

	writel((A12_YRES - 1) << 16 | (A12_XRES - 1), vop + VOP_WIN0_ACT_INFO);
	writel((A12_YRES - 1) << 16 | (A12_XRES - 1), vop + VOP_WIN0_DSP_INFO);
	writel(vact_st << 16 | hact_st, vop + VOP_WIN0_DSP_ST);
	writel(SCL_FACTOR_1 << 16 | SCL_FACTOR_1, vop + VOP_WIN0_SCL_FACTOR);
	writel(A12_XRES, vop + VOP_WIN0_VIR);	/* stride in 32-bit words */
	writel(fb, vop + VOP_WIN0_YRGB_MST);
	clrbits_le32(vop + VOP_ALPHA_CTRL, BIT(0));

	clrsetbits_le32(vop + VOP_SYS_CTRL, SYS_WIN0_FMT_MASK | SYS_WIN0_RB_SWAP | SYS_STANDBY,
			SYS_WIN0_EN);
	writel(1, vop + VOP_REG_CFG_DONE);
}

static int a12_display_probe(struct udevice *dev)
{
	struct video_uc_plat *plat = dev_get_uclass_plat(dev);
	struct video_priv *uc_priv = dev_get_uclass_priv(dev);
	struct a12_display_priv *priv = dev_get_priv(dev);
	struct rk3128_cru *cru;
	struct udevice *backlight;
	ofnode panel, node;
	int ret;

	priv->vop = dev_read_addr_ptr(dev);
	node = ofnode_by_compatible(ofnode_null(), "rockchip,rk3128-cru");
	cru = (struct rk3128_cru *)ofnode_get_addr(node);
	panel = ofnode_by_compatible(ofnode_null(), "powkiddy,a12-rev-a-panel");
	if (!priv->vop || cru == (void *)FDT_ADDR_T_NONE || !ofnode_valid(panel))
		return -ENODEV;

	a12_clocks(cru);
	ret = a12_ttl_phy_on();
	if (ret)
		return log_msg_ret("phy", ret);
	ret = a12_panel_on(panel);
	if (ret)
		return log_msg_ret("panel", ret);

	uc_priv->xsize = A12_XRES;
	uc_priv->ysize = A12_YRES;
	uc_priv->bpix = VIDEO_BPP32;
	video_set_flush_dcache(dev, true);
	a12_vop_start(priv->vop, plat->base);
	mdelay(150);	/* a12_enable() */

	node = ofnode_parse_phandle(panel, "backlight", 0);
	if (ofnode_valid(node) &&
	    !uclass_get_device_by_ofnode(UCLASS_PANEL_BACKLIGHT, node, &backlight))
		backlight_enable(backlight);
	return 0;
}

static int a12_display_bind(struct udevice *dev)
{
	struct video_uc_plat *plat = dev_get_uclass_plat(dev);

	plat->size = A12_XRES * A12_YRES * 4;
	return 0;
}

static const struct udevice_id a12_display_ids[] = {
	{ .compatible = "rockchip,rk3126-vop" },
	{ }
};

U_BOOT_DRIVER(a12_display) = {
	.name		= "a12_display",
	.id		= UCLASS_VIDEO,
	.of_match	= a12_display_ids,
	.bind		= a12_display_bind,
	.probe		= a12_display_probe,
	.priv_auto	= sizeof(struct a12_display_priv),
	.flags		= DM_FLAG_PRE_RELOC,
};
