#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""rk312x codec: DAPM's bias OFF must not power the DAC down mid-stream (test 59).

The driver powers playback with its own register lists in startup(); DAPM
never sees the path as active, so after rk312x_delay_workq() forced the bias
OFF -> STANDBY at boot, DAPM later dropped it to OFF while ES was playing:
the BIAS_OFF branch cleared the DAC reference/current bits (0xa0 0x7b -> 0x3a,
0xa4 0xff -> 0xf8, 0x18 0x32 -> 0x22) and the speaker stayed silent until
every stream closed. Run the real set_bias_level() against a register mock.
"""
import pathlib
import re
import subprocess
import tempfile

src = (pathlib.Path(__file__).resolve().parents[1]
       / "packages/rk3128-hardware/sources/rk312x_codec.c").read_text()
hdr = (pathlib.Path(__file__).resolve().parents[1]
       / "packages/rk3128-hardware/sources/rk312x_codec.h").read_text()
func = re.search(r"static int rk312x_set_bias_level\(.*?\n}\n", src, re.S)[0]

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define DBG(...) do {} while (0)
enum snd_soc_bias_level { SND_SOC_BIAS_OFF, SND_SOC_BIAS_STANDBY, SND_SOC_BIAS_PREPARE, SND_SOC_BIAS_ON };
struct snd_soc_component { int dummy; };
struct snd_soc_dapm_context { enum snd_soc_bias_level level; };
static struct snd_soc_dapm_context dapm;
static unsigned int regs[0x200];
static struct snd_soc_dapm_context *snd_soc_component_to_dapm(struct snd_soc_component *c) { (void)c; return &dapm; }
static enum snd_soc_bias_level snd_soc_dapm_get_bias_level(struct snd_soc_dapm_context *d) { return d->level; }
static int snd_soc_component_update_bits(struct snd_soc_component *c, unsigned int r, unsigned int m, unsigned int v)
{ (void)c; regs[r] = (regs[r] & ~m) | (v & m); return 0; }
static int regmap_write(void *map, unsigned int r, unsigned int v) { (void)map; regs[r] = v; return 0; }
struct rk312x_codec_priv { void *regmap; int playback_active; int capture_active; };
static struct rk312x_codec_priv priv, *rk312x_priv = &priv;
'''
MAIN = r'''
int main(void)
{
	struct snd_soc_component c;
	/* Playback powered by startup(): the values after the power-up list. */
	regs[0x18] = 0x32; regs[0xa0] = 0x7b; regs[0xa4] = 0xff;
	priv.playback_active = 1;
	dapm.level = SND_SOC_BIAS_STANDBY;
	rk312x_set_bias_level(&c, SND_SOC_BIAS_OFF);
	assert(regs[0x18] == 0x32 && regs[0xa0] == 0x7b && regs[0xa4] == 0xff);
	/* Idle codec: bias OFF still powers down. */
	priv.playback_active = 0;
	rk312x_set_bias_level(&c, SND_SOC_BIAS_OFF);
	assert(regs[0x18] == 0x22 && regs[0xa0] != 0x7b && regs[0xa4] != 0xff);
	puts("codec bias off: ok");
	return 0;
}
'''
defines = "\n".join(l for l in hdr.splitlines() if l.startswith("#define"))
with tempfile.TemporaryDirectory() as tmp:
    c = pathlib.Path(tmp) / "t.c"
    c.write_text(HARNESS + "#define RK312x_CODEC_BASE 0\n" + defines + "\n" + func + MAIN)
    subprocess.run(["gcc", "-w", "-o", str(pathlib.Path(tmp) / "t"), str(c)], check=True)
    subprocess.run([str(pathlib.Path(tmp) / "t")], check=True)
