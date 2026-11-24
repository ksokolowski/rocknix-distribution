#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""tools/a12-upstream-status: every PR/MR the tracker links, and its state.

The tool reads upstream/TRACKER.md, finds GitHub pull requests and GitLab
merge requests in each row, asks the forge for their state, and marks the
ones whose last comment is not the owner's ("reply?"). Only the parsing and
the marking are tested here; the forge queries need the network.
"""
import importlib.machinery
import importlib.util
import pathlib

root = pathlib.Path(__file__).resolve().parents[5]
path = root / "projects/ROCKNIX/devices/RK3128/tools/a12-upstream-status"
loader = importlib.machinery.SourceFileLoader("upstream_status", str(path))
spec = importlib.util.spec_from_loader("upstream_status", loader)
tool = importlib.util.module_from_spec(spec)
loader.exec_module(tool)

rows = """
| ID | Change | Kind | Target | Status |
|---|---|---|---|---|
| M01 | lima | fix | Mesa | **MR open** [mesa/mesa!45697](https://gitlab.freedesktop.org/mesa/mesa/-/merge_requests/45697) |
| VB02 | idle | perf | beetle | **sent** [#100](https://github.com/libretro/beetle-vb-libretro/pull/100), includes #99 |
| VB04 | snap | perf | beetle | **sent** within [#100](https://github.com/libretro/beetle-vb-libretro/pull/100) |
| D02 | rootpw | fix | sent [#3561](https://github.com/ROCKNIX/distribution/pull/3561) | PR 3 |
| K01 | pl330 | fix | prepared | send |
"""
found = tool.submissions(rows)
assert found == [
    ("M01", "gitlab.freedesktop.org", "mesa/mesa", 45697),
    ("VB02", "github.com", "libretro/beetle-vb-libretro", 100),
    ("D02", "github.com", "ROCKNIX/distribution", 3561),
], found
# The same link in a second row (VB04 within #100) is listed once.

owner = "ksokolowski"
assert tool.needs_reply([], owner) is False
assert tool.needs_reply(["spycat88", owner], owner) is False
assert tool.needs_reply([owner, "hizzlekizzle"], owner) is True
# Bots and CI do not count as a reviewer waiting for an answer.
assert tool.needs_reply([owner, "github-actions[bot]", "marge-bot"], owner) is False

real = tool.submissions((root / "projects/ROCKNIX/devices/RK3128/upstream/TRACKER.md").read_text())
assert ("M01", "gitlab.freedesktop.org", "mesa/mesa", 45697) in real, real
assert len({(h, p, n) for _, h, p, n in real}) == len(real), "each submission once"
print("upstream status: ok")
