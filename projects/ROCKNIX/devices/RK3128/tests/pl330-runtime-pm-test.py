#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Kernel patch 0014: PL330 drops each runtime PM reference exactly once.

TEST_LOG tests 22/27: under combined load dw_mmc terminated its external
PL330 channel and the kernel logged "Runtime PM usage count underflow".
The real pl330_issue_pending(), pl330_tasklet() and pl330_terminate_all()
are extracted from drivers/dma/pl330.c, compiled against mocks that count
pm_runtime get/put, and run through the race: a completion schedules the
tasklet, the client terminates the channel, then the tasklet runs. The
unpatched source must underflow, the patched one must stay balanced.

Needs a Linux source tree: A12_LINUX_SRC=/path/to/linux (7.1.x); skipped
otherwise.
"""
import os
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
patch = root / "projects/ROCKNIX/devices/RK3128/patches/linux/0014-dmaengine-pl330-drop-only-the-runtime-pm-reference-held.patch"
assert "power_down = pch->active;" in patch.read_text()
# DMA is the default since test 56 (patch 0014, combined stress clean);
# A12_SD_DMA=no builds the old PIO tree.
dts = (root / "projects/ROCKNIX/devices/RK3128/linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
sdmmc = dts[dts.index("&sdmmc {"):]
sdmmc = sdmmc[:sdmmc.index("};")]
assert "/delete-property/ dmas;" not in sdmmc and "/delete-property/ dma-names;" not in sdmmc
linux_mk = (root / "projects/ROCKNIX/packages/linux/package.mk").read_text()
assert 'if [ "${DEVICE}" = "RK3128" ] && [ "${A12_SD_DMA}" = "no" ]; then' in linux_mk

src = os.environ.get("A12_LINUX_SRC")
if not src or not (pathlib.Path(src) / "drivers/dma/pl330.c").exists():
    print("note: A12_LINUX_SRC not set; pl330 race replay skipped")
    print("pl330 runtime pm: ok")
    raise SystemExit(0)

MOCKS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
struct list_head { struct list_head *next, *prev; };
#define INIT_LIST_HEAD(l) ((l)->next = (l)->prev = (l))
static int list_empty(const struct list_head *h) { return h->next == h; }
static void __list_del(struct list_head *e) { e->prev->next = e->next; e->next->prev = e->prev; }
static void list_add_tail(struct list_head *n, struct list_head *h)
{ n->prev = h->prev; n->next = h; h->prev->next = n; h->prev = n; }
static void list_move_tail(struct list_head *e, struct list_head *h) { __list_del(e); list_add_tail(e, h); }
static void list_splice_tail_init(struct list_head *l, struct list_head *h)
{ while (!list_empty(l)) list_move_tail(l->next, h); }
#define list_entry(p, t, m) container_of(p, t, m)
#define list_first_entry(h, t, m) list_entry((h)->next, t, m)
#define list_for_each_entry(p, h, m) \
	for (p = list_entry((h)->next, __typeof__(*p), m); &p->m != (h); p = list_entry(p->m.next, __typeof__(*p), m))
#define list_for_each_entry_safe(p, n, h, m) \
	for (p = list_entry((h)->next, __typeof__(*p), m), n = list_entry(p->m.next, __typeof__(*p), m); \
	     &p->m != (h); p = n, n = list_entry(n->m.next, __typeof__(*n), m))
typedef int spinlock_t;
#define spin_lock_irqsave(l, f) ((void)(l), (f) = 0)
#define spin_unlock_irqrestore(l, f) ((void)(l), (void)(f))
#define spin_lock(l) ((void)(l))
#define spin_unlock(l) ((void)(l))
#define WARN_ON(x) ((void)(x))
struct device { int usage; };
static int pm_gets, pm_puts;
static void pm_runtime_get_sync(struct device *d) { d->usage++; pm_gets++; }
static void pm_runtime_put_autosuspend(struct device *d) { d->usage--; pm_puts++; }
static void pm_runtime_mark_last_busy(struct device *d) { (void)d; }
struct tasklet_struct { int scheduled; };
#define from_tasklet(var, t, f) container_of(t, __typeof__(*var), f)
struct dma_chan { int id; };
struct dma_async_tx_descriptor { int cookie; };
struct dmaengine_desc_callback { int valid; };
#define dma_cookie_complete(t) ((void)(t))
#define dma_descriptor_unmap(t) ((void)(t))
#define dmaengine_desc_get_callback(t, cb) ((cb)->valid = 0)
#define dmaengine_desc_callback_valid(cb) ((cb)->valid)
#define dmaengine_desc_callback_invoke(cb, r) ((void)(cb))
enum desc_status { FREE, PREP, BUSY, DONE };
struct pl330_dmac { spinlock_t lock; struct list_head desc_pool; struct { struct device *dev; } ddma; };
struct pl330_thread { struct pl330_dmac *dmac; struct { void *desc; } req[2]; int req_running; };
struct dma_pl330_desc { struct list_head node; enum desc_status status; struct dma_async_tx_descriptor txd; };
struct dma_pl330_chan {
	struct tasklet_struct task; struct dma_chan chan; spinlock_t lock;
	struct list_head submitted_list, work_list, completed_list;
	struct pl330_dmac *dmac; struct pl330_thread *thread; bool active; bool cyclic;
};
#define to_pchan(c) container_of(c, struct dma_pl330_chan, chan)
static void _stop(struct pl330_thread *t) { (void)t; }
static void pl330_start_thread(struct pl330_thread *t) { (void)t; }
static void fill_queue(struct dma_pl330_chan *p) { (void)p; }
'''

MAIN = r'''
int main(void)
{
	static struct device dev;
	static struct pl330_dmac dmac;
	static struct pl330_thread thread;
	static struct dma_pl330_chan pch;
	static struct dma_pl330_desc desc;

	dmac.ddma.dev = &dev;
	INIT_LIST_HEAD(&dmac.desc_pool);
	thread.dmac = &dmac;
	pch.dmac = &dmac;
	pch.thread = &thread;
	INIT_LIST_HEAD(&pch.submitted_list);
	INIT_LIST_HEAD(&pch.work_list);
	INIT_LIST_HEAD(&pch.completed_list);

	/* dw_mmc submits one transfer: the channel takes a reference. */
	desc.status = PREP;
	list_add_tail(&desc.node, &pch.submitted_list);
	pl330_issue_pending(&pch.chan);
	assert(dev.usage == 1 && pch.active);

	/* The transfer completes; the IRQ path marks it and schedules the
	 * tasklet, but before it runs dw_mmc's error path terminates. */
	desc.status = DONE;
	pl330_terminate_all(&pch.chan);
	printf("after terminate %d\n", dev.usage);

	/* Now the scheduled tasklet runs on the empty channel. */
	pl330_tasklet(&pch.task);
	printf("after tasklet %d\n", dev.usage);
	return dev.usage < 0 ? 3 : 0;
}
'''


def function(code, name):
    start = re.search(rf"^static (?:void|int) {name}\(", code, re.M).start()
    depth, i = 0, code.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(code[i], 0)
        i += 1
        if depth == 0:
            return code[start:i] + "\n"


def replay(patched):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "drivers/dma").mkdir(parents=True)
        code = (pathlib.Path(src) / "drivers/dma/pl330.c").read_text()
        (tmp / "drivers/dma/pl330.c").write_text(code)
        if patched and "power_down = pch->active;\n\t\tpch->active = false;\n\t} else {" not in code:
            subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=patch.read_text(), text=True, check=True)
        if not patched and "power_down = pch->active;\n\t\tpch->active = false;\n\t} else {" in code:
            subprocess.run(["patch", "-p1", "-R", "-s", "-d", str(tmp)], input=patch.read_text(), text=True, check=True)
        code = (tmp / "drivers/dma/pl330.c").read_text()
        body = MOCKS + "".join(function(code, n) for n in ("pl330_tasklet", "pl330_terminate_all",
                                                          "pl330_issue_pending")) + MAIN
        (tmp / "t.c").write_text(body)
        subprocess.run(["gcc", "-w", "-o", str(tmp / "t"), str(tmp / "t.c")], check=True)
        r = subprocess.run([str(tmp / "t")], capture_output=True, text=True)
        return r.returncode, r.stdout


rc, out = replay(patched=False)
assert rc == 3 and "after tasklet -1" in out, ("unpatched must underflow", rc, out)
rc, out = replay(patched=True)
assert rc == 0 and "after terminate 0" in out and "after tasklet 0" in out, ("patched must balance", rc, out)
print("pl330 runtime pm: ok")
