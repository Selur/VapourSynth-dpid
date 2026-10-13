#!/usr/bin/env python3
"""Functional tests for the dpid VapourSynth plugin (API 4).

Usage: python test/test_dpid.py [path/to/dpid plugin]

Without an argument the plugin is expected to be autoloaded (e.g. from the installed wheel).
The output is compared with a Python reference of the algorithm (float rounding may differ by one step).
"""
import ctypes
import math
import struct
import sys

import vapoursynth as vs

core = vs.core
FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
        print("FAIL: " + msg)
        return
    print("ok  ", msg)


def expect_error(fn, msg, contains):
    try:
        fn()
    except vs.Error as e:
        check(contains in str(e), "%s (%s)" % (msg, str(e).strip().splitlines()[-1]))
    else:
        check(False, "no error raised: " + msg)


def pattern(w, h, peak):
    rows = []
    state = (w * 7919 + h * 104729) & 0xFFFFFFFF
    for y in range(h):
        row = []
        for x in range(w):
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            value = 128 + ((x * 5 + y * 3) % 100) - 50 + (state >> 16) % 41 - 20
            if (x // 6 + y // 5) % 4 == 0:
                value = 230 if (x + y) % 3 else 25
            row.append(max(0, min(255, value)) * peak / 255.0)
        rows.append(row)
    return rows


def gray_clip(fmt, w, h):
    info = core.get_video_format(fmt)
    flt = info.sample_type == vs.FLOAT
    peak = 1.0 if flt else (1 << info.bits_per_sample) - 1
    code = "f" if flt else ("B" if info.bytes_per_sample == 1 else "H")
    rows = pattern(w, h, peak)
    blank = core.std.BlankClip(width=w, height=h, format=fmt, length=1)

    def fill(n, f):
        fout = f.copy()
        ptr = fout.get_write_ptr(0)
        ptr = ptr.value if hasattr(ptr, "value") else ptr
        stride = fout.get_stride(0)
        for y, row in enumerate(rows):
            data = struct.pack("<%d%s" % (w, code), *[(v if flt else int(v)) for v in row])
            ctypes.memmove(ptr + y * stride, data, len(data))
        return fout

    return core.std.ModifyFrame(blank, blank, fill), rows, flt


def values(clip):
    f = clip.get_frame(0)
    info = clip.format
    code = "f" if info.sample_type == vs.FLOAT else ("B" if info.bytes_per_sample == 1 else "H")
    data = bytes(f[0])
    flat = struct.unpack("<%d%s" % (len(data) // info.bytes_per_sample, code), data)
    return [list(flat[y * clip.width:(y + 1) * clip.width]) for y in range(clip.height)]


def reference(src, down, src_w, src_h, dst_w, dst_h, lam, flt):
    """DpidRaw on one plane, same order of operations as the plugin."""
    scale_x, scale_y = src_w / dst_w, src_h / dst_h
    out = []
    for oy in range(dst_h):
        row = []
        for ox in range(dst_w):
            avg = 0.0
            for iy in (-1, 0, 1):
                for ix in (-1, 0, 1):
                    y = min(max(oy + iy, 0), dst_h - 1)
                    x = min(max(ox + ix, 0), dst_w - 1)
                    avg += down[y][x] * (2 - abs(iy)) * (2 - abs(ix))
            avg /= 16.0
            sx, ex = min(max(ox * scale_x, 0.0), src_w), min(max((ox + 1) * scale_x, 0.0), src_w)
            sy, ey = min(max(oy * scale_y, 0.0), src_h), min(max((oy + 1) * scale_y, 0.0), src_h)
            sum_pixel = sum_weight = 0.0
            for iy in range(math.floor(sy), math.ceil(ey)):
                for ix in range(math.floor(sx), math.ceil(ex)):
                    pixel = src[iy][ix]
                    weight = abs(avg - pixel) ** lam
                    if ix < sx:
                        weight *= 1.0 - (sx - ix)
                    if ix + 1.0 > ex:
                        weight *= ex - ix
                    if iy < sy:
                        weight *= 1.0 - (sy - iy)
                    if iy + 1.0 > ey:
                        weight *= ey - iy
                    sum_pixel += weight * pixel
                    sum_weight += weight
            result = avg if sum_weight == 0.0 else sum_pixel / sum_weight
            row.append(result if flt else int(result))
        out.append(row)
    return out


def main():
    if len(sys.argv) > 1:
        core.std.LoadPlugin(sys.argv[1])
    check(hasattr(core, "dpid"), "plugin loaded (namespace dpid)")

    for fmt, tolerance in ((vs.GRAY8, 1), (vs.GRAY16, 1), (vs.GRAYS, 1e-5)):
        name = core.get_video_format(fmt).name
        for dst_w, dst_h, lam in ((16, 12, 1.0), (11, 7, 0.5), (16, 12, 2.0)):
            src, rows, flt = gray_clip(fmt, 48, 36)
            res = core.dpid.Dpid(src, width=dst_w, height=dst_h, **{"lambda": lam})
            check(res.width == dst_w and res.height == dst_h and res.format.id == src.format.id,
                  "%s %dx%d lambda %.1f: size and format" % (name, dst_w, dst_h, lam))
            down = values(core.resize.Bilinear(src, dst_w, dst_h))
            expected = reference(rows if flt else [[int(v) for v in r] for r in rows], down, 48, 36, dst_w, dst_h, lam, flt)
            got = values(res)
            worst = max(abs(a - b) for ra, rb in zip(expected, got) for a, b in zip(ra, rb))
            check(worst <= tolerance, "%s %dx%d lambda %.1f: matches the reference (max difference %g)" % (name, dst_w, dst_h, lam, worst))

    yuv = core.std.BlankClip(width=320, height=240, format=vs.YUV420P10, color=[400, 300, 700], length=2)
    res = core.dpid.Dpid(yuv, width=0, height=120)
    check(res.width == 160 and res.height == 120 and res.num_frames == 2, "width 0 keeps the aspect ratio")
    f = res.get_frame(0)
    check(all(set(struct.unpack("<%dH" % (len(bytes(f[p])) // 2), bytes(f[p]))) == {v} for p, v in enumerate((400, 300, 700))),
          "flat YUV420P10 stays flat")

    src, _, _ = gray_clip(vs.GRAY8, 48, 36)
    down = core.resize.Point(src, 16, 12)
    raw = core.dpid.DpidRaw(src, down)
    check(raw.width == 16 and raw.height == 12, "DpidRaw takes the size of clip2")
    rgb = core.std.BlankClip(width=64, height=48, format=vs.RGB24, color=[10, 200, 90], length=1)
    rgb_down = core.std.BlankClip(width=32, height=24, format=vs.RGB24, color=[1, 2, 3], length=1)
    part = core.dpid.DpidRaw(rgb, rgb_down, planes=[0])
    fp = part.get_frame(0)
    check(set(bytes(fp[1])) == {2} and set(bytes(fp[2])) == {3}, "DpidRaw copies unprocessed planes from clip2")

    expect_error(lambda: core.dpid.Dpid(src), "same size rejected", "identical to input")
    expect_error(lambda: core.dpid.Dpid(src, width=0, height=0), "width and height 0 rejected", "can not be equal to 0")
    expect_error(lambda: core.dpid.Dpid(src.resize.Point(format=vs.GRAYH), width=16, height=12), "half float rejected", "only constant format")
    expect_error(lambda: core.dpid.Dpid(src, width=16, height=12, **{"lambda": [1.0, 2.0]}), "too many lambda values rejected", "more \"lambda\"")
    expect_error(lambda: core.dpid.DpidRaw(src, down.resize.Point(format=vs.GRAY16)), "DpidRaw format mismatch rejected", "same format")
    expect_error(lambda: core.dpid.DpidRaw(src, down, planes=[1]), "plane index out of range rejected", "out of range")

    if FAILURES:
        raise SystemExit("%d check(s) failed" % len(FAILURES))
    print("all tests passed")


if __name__ == "__main__":
    main()
