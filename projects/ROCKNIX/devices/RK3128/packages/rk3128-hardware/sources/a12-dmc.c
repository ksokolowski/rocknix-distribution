// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2016, Fuzhou Rockchip Electronics Co., Ltd
 * Author: Lin Huang <hl@rock-chips.com>
 *
 * RK3128 SIP_V2 ABI adapted from KNULLI kernel 72498e26:
 * drivers/devfreq/rockchip_dmc.c, drivers/clk/rockchip/clk-ddr.c and
 * drivers/firmware/rockchip_sip.c. This A12 driver leaves clock switching,
 * CPU rendezvous and DRAM training to the retained Rockchip TEE firmware.
 */
#include <linux/arm-smccc.h>
#include <linux/clk.h>
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/devfreq.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_opp.h>
#include <linux/regulator/consumer.h>
#include <drm/drm_connector.h>
#include <drm/drm_crtc.h>
#include <drm/drm_device.h>
#include <drm/drm_drv.h>
#include <drm/drm_modeset_lock.h>

#define SIP_DRAM_CONFIG	0x82000008
#define SIP_SHARE_MEM	0x82000009
#define SIP_SIP_VERSION	0x8200000a
#define SIP_IMPLEMENT_V2	2
#define SECURE_REG_WR	1
#define SHARE_DDR	2
#define DRAM_INIT	0
#define DRAM_SET_RATE	1
#define DRAM_ROUND_RATE	2
#define DRAM_GET_RATE	5
#define SIP_RATE_TIMEOUT	(-6)
#define TIMING_OFFSET	4096
#define SHARE_SIZE	8192
#define SCREEN_LVDS	2

/* Field order is part of the firmware ABI, including the unused fields. */
struct a12_dram_params {
	u32 hz;
	u32 lcdc_type;
	u32 vop;
	u32 vop_dclk_mode;
	u32 sr_idle_en;
	u32 addr_mcu_el3;
	u32 wait_flag1;
	u32 wait_flag0;
	u32 complt_hwirq;
};

static const char * const timing_names[] = {
	"ddr3_speed_bin", "pd_idle", "sr_idle", "auto_pd_dis_freq",
	"auto_sr_dis_freq", "ddr3_dll_dis_freq", "lpddr2_dll_dis_freq",
	"phy_dll_dis_freq", "ddr3_odt_dis_freq", "phy_ddr3_odt_disb_freq",
	"ddr3_drv", "ddr3_odt", "phy_ddr3_clk_drv", "phy_ddr3_cmd_drv",
	"phy_ddr3_dqs_drv", "phy_ddr3_odt", "lpddr2_drv",
	"phy_lpddr2_clk_drv", "phy_lpddr2_cmd_drv", "phy_lpddr2_dqs_drv",
	"ddr_2t",
};

struct a12_dmc {
	void __iomem *shared;
	struct clk *dpll;
	struct clk *cpu_clk;
	u32 min_cpu_freq;
	struct drm_device *drm;
	struct devfreq_dev_profile profile;
};

static int dram_call(u32 command, unsigned long *value)
{
	struct arm_smccc_res res;

	/* Flush shared-memory writes before handing control to secure firmware. */
	wmb();
	arm_smccc_smc(SIP_DRAM_CONFIG, SHARE_DDR, 0, command,
		      0, 0, 0, 0, &res);
	if (value)
		*value = res.a1;
	return (s32)res.a0;
}

static int a12_dmc_get_rate(struct device *dev, unsigned long *freq)
{
	struct a12_dmc *dmc = dev_get_drvdata(dev);
	int ret = dram_call(DRAM_GET_RATE, freq);

	if (ret || !*freq)
		return -EIO;
	/* DPLL is firmware-owned. Refresh its CCF descendants after a switch. */
	/* Rockchip exposes a mode mux as "dpll" and the PLL as its parent. */
	clk_get_rate(clk_get_parent(dmc->dpll));
	return 0;
}

/* Called with modeset locks held so a switch cannot race a display modeset. */
static u32 a12_lcdc_type(struct drm_device *drm)
{
	struct drm_connector_list_iter iter;
	struct drm_connector *connector;
	u32 type = 0;

	drm_connector_list_iter_begin(drm, &iter);
	drm_for_each_connector_iter(connector, &iter) {
		struct drm_crtc *crtc;

		if (!connector->state)
			continue;
		crtc = connector->state->crtc;
		if (crtc && crtc->state && crtc->state->active &&
		    (connector->connector_type == DRM_MODE_CONNECTOR_LVDS ||
		     connector->connector_type == DRM_MODE_CONNECTOR_DPI)) {
			/* Vendor ABI maps both DPI and LVDS to SCREEN_LVDS. */
			type = SCREEN_LVDS;
			break;
		}
	}
	drm_connector_list_iter_end(&iter);
	return type;
}

static int a12_dmc_switch(struct device *dev, unsigned long rate,
			  unsigned long *result)
{
	struct a12_dmc *dmc = dev_get_drvdata(dev);
	struct a12_dram_params __iomem *p = dmc->shared;
	struct cpufreq_policy *policy;
	struct freq_qos_request cpu_min = { };
	int ret;

	/* Vendor target blocks CPU hotplug and raises CPU to at least 600 MHz.
	 * A temporary QoS vote also covers schedutil; CCF exclusivity prevents
	 * asynchronous CPU PLL changes throughout the firmware rendezvous.
	 */
	*result = 0;
	cpus_read_lock();
	policy = cpufreq_cpu_get(0);
	if (!policy) {
		ret = -EPROBE_DEFER;
		goto out_cpus;
	}
	ret = freq_qos_add_request(&policy->constraints, &cpu_min,
				   FREQ_QOS_MIN, dmc->min_cpu_freq);
	if (ret < 0)
		goto out_policy;
	cpufreq_update_limits(0);
	down_write(&policy->rwsem);
	ret = clk_rate_exclusive_get(dmc->cpu_clk);
	if (ret)
		goto out_rwsem;
	/* Respect thermal/user maxima instead of switching with a slow CPU. */
	if (clk_get_rate(dmc->cpu_clk) < (unsigned long)dmc->min_cpu_freq * 1000) {
		dev_err(dev, "CPU below %u kHz; refusing DDR transition\n",
			dmc->min_cpu_freq);
		ret = -EBUSY;
		goto out_clock;
	}
	drm_modeset_lock_all(dmc->drm);
	writel(rate, &p->hz);
	writel(a12_lcdc_type(dmc->drm), &p->lcdc_type);
	writel(1, &p->wait_flag1);
	writel(1, &p->wait_flag0);
	ret = dram_call(DRAM_SET_RATE, result);
	drm_modeset_unlock_all(dmc->drm);
out_clock:
	clk_rate_exclusive_put(dmc->cpu_clk);
out_rwsem:
	up_write(&policy->rwsem);
	freq_qos_remove_request(&cpu_min);
out_policy:
	cpufreq_cpu_put(policy);
out_cpus:
	cpus_read_unlock();
	return ret;
}

static int a12_dmc_target(struct device *dev, unsigned long *freq, u32 flags)
{
	struct a12_dmc *dmc = dev_get_drvdata(dev);
	struct a12_dram_params __iomem *p = dmc->shared;
	struct dev_pm_opp *opp;
	unsigned long requested, actual, previous, result;
	int ret;

	opp = devfreq_recommended_opp(dev, freq, flags);
	if (IS_ERR(opp))
		return PTR_ERR(opp);
	dev_pm_opp_put(opp);
	requested = *freq;
	/* Only rates documented on the owner's working revision A are allowed. */
	if (requested != 300000000 && requested != 456000000)
		return -EINVAL;
	ret = a12_dmc_get_rate(dev, &actual);
	if (ret || actual == requested)
		return ret;
	previous = actual;

	writel(requested, &p->hz);
	ret = dram_call(DRAM_ROUND_RATE, &result);
	if (ret || result != requested) {
		dev_err(dev, "firmware cannot supply DDR %lu Hz (status %d, rate %lu)\n",
			requested, ret, result);
		return -EIO;
	}

	ret = a12_dmc_switch(dev, requested, &result);
	if (ret == -EPROBE_DEFER)
		return ret;
	/* RK3128 has no vendor completion IRQ. Never treat its timeout as success. */
	if (ret || (s32)result == SIP_RATE_TIMEOUT) {
		dev_err(dev, "DDR switch failed: firmware status %d, result %ld\n",
			ret, (long)(s32)result);
		return -EIO;
	}
	ret = a12_dmc_get_rate(dev, &actual);
	if (ret || actual != requested) {
		dev_err(dev, "DDR readback failed: requested %lu Hz, actual %lu Hz\n",
			requested, ret ? 0 : actual);
		return -EIO;
	}
	*freq = actual;
	dev_info(dev, "DDR %lu -> %lu Hz verified by firmware\n",
		 previous, actual);
	return 0;
}

static void a12_drm_put(void *data)
{
	drm_dev_put(data);
}

static int a12_dmc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct a12_dram_params __iomem *p;
	struct platform_device *display;
	struct device_node *np;
	struct regulator *supply;
	struct arm_smccc_res res;
	struct devfreq *df;
	struct a12_dmc *dmc;
	u32 timings[ARRAY_SIZE(timing_names) + 1], mode;
	unsigned int i;
	int ret;

	static_assert(sizeof(struct a12_dram_params) == 9 * sizeof(u32));
	dmc = devm_kzalloc(dev, sizeof(*dmc), GFP_KERNEL);
	if (!dmc)
		return -ENOMEM;
	platform_set_drvdata(pdev, dmc);
	dmc->dpll = devm_clk_get(dev, "dpll");
	if (IS_ERR(dmc->dpll))
		return dev_err_probe(dev, PTR_ERR(dmc->dpll), "DPLL unavailable\n");
	dmc->cpu_clk = devm_clk_get(dev, "cpu");
	if (IS_ERR(dmc->cpu_clk))
		return dev_err_probe(dev, PTR_ERR(dmc->cpu_clk), "CPU clock unavailable\n");
	ret = of_property_read_u32(dev->of_node, "min-cpu-freq", &dmc->min_cpu_freq);
	if (ret || dmc->min_cpu_freq != 600000)
		return dev_err_probe(dev, -EINVAL, "A12 DDR requires 600 MHz CPU during switching\n");
	supply = devm_regulator_get(dev, "center");
	if (IS_ERR(supply))
		return dev_err_probe(dev, PTR_ERR(supply), "logic supply unavailable\n");
	/* Shared with GPU. Retain the board's 1.2 V floor, allow GPU's higher vote. */
	ret = regulator_set_voltage(supply, 1200000, 1400000);
	if (ret)
		return dev_err_probe(dev, ret, "cannot maintain DDR voltage floor\n");

	np = of_parse_phandle(dev->of_node, "rockchip,display", 0);
	display = of_find_device_by_node(np);
	of_node_put(np);
	if (!display)
		return -EPROBE_DEFER;
	device_lock(&display->dev);
	dmc->drm = platform_get_drvdata(display);
	if (dmc->drm && dmc->drm->registered)
		drm_dev_get(dmc->drm);
	else
		dmc->drm = NULL;
	device_unlock(&display->dev);
	put_device(&display->dev);
	if (!dmc->drm)
		return -EPROBE_DEFER;
	ret = devm_add_action_or_reset(dev, a12_drm_put, dmc->drm);
	if (ret)
		return ret;

	np = of_parse_phandle(dev->of_node, "rockchip,ddr_timing", 0);
	if (!np)
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(timing_names); i++) {
		ret = of_property_read_u32(np, timing_names[i], &timings[i]);
		if (ret)
			break;
	}
	of_node_put(np);
	if (ret)
		return dev_err_probe(dev, ret, "incomplete DDR timings\n");
	timings[ARRAY_SIZE(timing_names)] = 1; /* ABI: available */
	ret = of_property_read_u32(dev->of_node, "vop-dclk-mode", &mode);
	if (ret)
		return ret;
	ret = devm_pm_opp_of_add_table(dev);
	if (ret)
		return ret;

	/* Vendor arch_initcall selects the kernel-4.4 shared-memory ABI in TEE.
	 * Mainline has no equivalent initializer. Never proceed on rejection.
	 */
	dev_info(dev, "selecting Rockchip SIP V2 before DDR initialization\n");
	arm_smccc_smc(SIP_SIP_VERSION, SIP_IMPLEMENT_V2, SECURE_REG_WR, 0,
		      0, 0, 0, 0, &res);
	if ((s32)res.a0)
		return dev_err_probe(dev, -EIO, "SIP V2 selection rejected (%ld)\n",
				     (long)(s32)res.a0);
	dev_info(dev, "SIP V2 selected; requesting DDR shared memory\n");

	arm_smccc_smc(SIP_SHARE_MEM, SHARE_SIZE / 4096, SHARE_DDR, 0,
		      0, 0, 0, 0, &res);
	if ((s32)res.a0 || !res.a1 || !IS_ALIGNED(res.a1, 4096))
		return dev_err_probe(dev, -EIO, "DDR shared memory rejected by firmware\n");
	/* Firmware must return its reserved memory, never Linux-owned pages. */
	if (res.a1 > U32_MAX - SHARE_SIZE ||
	    region_intersects(res.a1, SHARE_SIZE, IORESOURCE_SYSTEM_RAM,
			      IORES_DESC_NONE) != REGION_DISJOINT)
		return dev_err_probe(dev, -EINVAL, "DDR shared memory overlaps system RAM\n");
	dmc->shared = devm_ioremap(dev, res.a1, SHARE_SIZE);
	if (!dmc->shared)
		return -ENOMEM;
	dev_info(dev, "SIP_V2 shared memory at %#lx, A12 timings, VOP mode %u\n",
		 res.a1, mode);
	/* Do not clear firmware-owned fields such as vop or addr_mcu_el3. */
	memcpy_toio(dmc->shared + TIMING_OFFSET, timings, sizeof(timings));
	p = dmc->shared;
	writel(0, &p->hz);
	writel(mode, &p->vop_dclk_mode);
	drm_modeset_lock_all(dmc->drm);
	writel(a12_lcdc_type(dmc->drm), &p->lcdc_type);
	ret = dram_call(DRAM_INIT, NULL);
	drm_modeset_unlock_all(dmc->drm);
	if (ret)
		return dev_err_probe(dev, -EIO, "DDR firmware initialization failed (%d)\n", ret);
	ret = a12_dmc_get_rate(dev, &dmc->profile.initial_freq);
	if (ret)
		return ret;
	if (dmc->profile.initial_freq != 300000000 &&
	    dmc->profile.initial_freq != 456000000)
		return dev_err_probe(dev, -EIO, "unexpected initial DDR rate %lu Hz\n",
				     dmc->profile.initial_freq);
	dmc->profile.target = a12_dmc_target;
	dmc->profile.get_cur_freq = a12_dmc_get_rate;
	/* Like the vendor SYS_STATUS_NORMAL rate: switch to 456 MHz at probe. */
	df = devm_devfreq_add_device(dev, &dmc->profile,
				     DEVFREQ_GOV_PERFORMANCE, NULL);
	return PTR_ERR_OR_ZERO(df);
}

static const struct of_device_id a12_dmc_match[] = {
	{ .compatible = "powkiddy,a12-rev-a-dmc" },
	{ }
};
MODULE_DEVICE_TABLE(of, a12_dmc_match);

static struct platform_driver a12_dmc_driver = {
	.probe = a12_dmc_probe,
	.driver = {
		.name = "a12-dmc",
		.of_match_table = a12_dmc_match,
	},
};
module_platform_driver(a12_dmc_driver);
MODULE_DESCRIPTION("Powkiddy A12 revision A RK3128 firmware DDR devfreq");
MODULE_LICENSE("GPL");
