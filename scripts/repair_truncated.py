#!/usr/bin/env python3
"""
Patch a cut-off myepg guide with the last good one (2026-10-31: myepg served the EU guide cut
off mid-file, missing </tv>, for 11+ hours; the last good guide kept running out channel by
channel).

myepg writes all channels first, then programmes grouped by channel, so a cut-off file has every
channel's fresh listings up to the cut and none after it. For each channel this keeps whichever
copy reaches further ahead: the fresh one, or the last good one. Elements are copied byte for byte.
"""
import gzip
import re

PROG_RE = re.compile(rb"<programme\b[^>]*>.*?</programme>", re.S)
ATTR_RE = re.compile(rb'\b(stop|channel)="([^"]*)"')
CHANNEL_RE = re.compile(rb"<channel\b[^>]*>.*?</channel>", re.S)
ID_RE = re.compile(rb'\bid="([^"]*)"')


def _programmes(raw, start):
    """(channel, stop, element) for every complete programme from start on."""
    for m in PROG_RE.finditer(raw, start):
        tag = raw[m.start():raw.index(b">", m.start())]
        a = dict(ATTR_RE.findall(tag))
        yield a.get(b"channel", b""), a.get(b"stop", b"")[:14], m.group(0)


def repair(cut, last_good_path):
    """Merged guide bytes plus stats, or raise ValueError if the two can't be merged safely."""
    with open(last_good_path, "rb") as f:
        old = f.read()
    if old[:2] == b"\x1f\x8b":
        old = gzip.decompress(old)
    if not old.rstrip().endswith(b"</tv>"):
        raise ValueError("last good guide is not complete either")
    p_new, p_old = cut.find(b"<programme"), old.find(b"<programme")
    if p_new < 0 or p_old < 0:
        raise ValueError("no programmes (channel list itself cut off?)")
    tv_open = re.search(rb"<tv\b[^>]*>", cut)
    if not tv_open:
        raise ValueError("no <tv> in the fresh guide")

    # channels: the fresh list (complete: it comes before any programme), plus any last-good
    # channel the fresh list no longer has, so its remaining listings still show
    new_ch = CHANNEL_RE.findall(cut, tv_open.end(), p_new)
    new_ids = {ID_RE.search(c).group(1) for c in new_ch}
    old_ch = [c for c in CHANNEL_RE.findall(old, 0, p_old) if ID_RE.search(c).group(1) not in new_ids]

    reach_new, reach_old = {}, {}
    for cid, stop, _ in _programmes(cut, p_new):
        reach_new[cid] = max(reach_new.get(cid, b""), stop)
    for cid, stop, _ in _programmes(old, p_old):
        reach_old[cid] = max(reach_old.get(cid, b""), stop)
    use_new = {c for c, s in reach_new.items() if s >= reach_old.get(c, b"")}

    out = [cut[:tv_open.end()], b"\n"]
    out += [c + b"\n" for c in new_ch + old_ch]
    n_new = n_old = 0
    for cid, _, el in _programmes(cut, p_new):
        if cid in use_new:
            out.append(el + b"\n")
            n_new += 1
    for cid, _, el in _programmes(old, p_old):
        if cid not in use_new:
            out.append(el + b"\n")
            n_old += 1
    out.append(b"</tv>\n")
    stats = {"channels_fresh": len(use_new), "channels_last_good": len(set(reach_old) - use_new),
             "channels_only_in_last_good": len(old_ch),
             "programmes_fresh": n_new, "programmes_last_good": n_old}
    return b"".join(out), stats
