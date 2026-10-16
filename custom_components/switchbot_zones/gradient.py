"""Expand a few anchor colours into a full per-segment frame."""

from __future__ import annotations

import colorsys
from itertools import pairwise
import math

RGB = tuple[int, int, int]

MODES = ("rgb", "hsv", "oklab", "oklch")


def _to_linear(c: int) -> float:
    v = c / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> int:
    c = min(1.0, max(0.0, c))
    v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return round(v * 255)


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1 / 3), x)


def _to_oklab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in rgb)
    l_ = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _from_oklab(lab: tuple[float, float, float]) -> RGB:
    big_l, a, b = lab
    l_ = (big_l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (big_l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (big_l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _to_srgb(4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_),
        _to_srgb(-1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_),
        _to_srgb(-0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_),
    )


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_hue(h1: float, h2: float, t: float, period: float) -> float:
    d = (h2 - h1) % period
    if d > period / 2:
        d -= period
    return (h1 + d * t) % period


def mix(c1: RGB, c2: RGB, t: float, mode: str = "oklch") -> RGB:
    """Colour at position t (0..1) between c1 and c2."""
    if mode == "rgb":
        return tuple(round(_lerp(a, b, t)) for a, b in zip(c1, c2, strict=True))  # type: ignore[return-value]

    if mode == "hsv":
        h1, s1, v1 = colorsys.rgb_to_hsv(*(c / 255 for c in c1))
        h2, s2, v2 = colorsys.rgb_to_hsv(*(c / 255 for c in c2))
        # Black has neither hue nor saturation and grey has no hue; borrow them
        # from the other end so a fade to off darkens instead of greying out.
        if v1 == 0:
            h1, s1 = h2, s2
        elif s1 == 0:
            h1 = h2
        if v2 == 0:
            h2, s2 = h1, s1
        elif s2 == 0:
            h2 = h1
        r, g, b = colorsys.hsv_to_rgb(
            _lerp_hue(h1, h2, t, 1.0), _lerp(s1, s2, t), _lerp(v1, v2, t)
        )
        return (round(r * 255), round(g * 255), round(b * 255))

    lab1, lab2 = _to_oklab(c1), _to_oklab(c2)
    if mode == "oklab":
        return _from_oklab(
            tuple(_lerp(a, b, t) for a, b in zip(lab1, lab2, strict=True))
        )  # type: ignore[arg-type]

    c1_chroma = math.hypot(lab1[1], lab1[2])
    c2_chroma = math.hypot(lab2[1], lab2[2])
    h1 = math.atan2(lab1[2], lab1[1])
    h2 = math.atan2(lab2[2], lab2[1])
    if c1_chroma < 1e-3:
        h1 = h2
    if c2_chroma < 1e-3:
        h2 = h1
    hue = _lerp_hue(h1, h2, t, 2 * math.pi)
    chroma = _lerp(c1_chroma, c2_chroma, t)
    return _from_oklab(
        (_lerp(lab1[0], lab2[0], t), chroma * math.cos(hue), chroma * math.sin(hue))
    )


def parse_zones(text: str, count: int) -> list[list[int]]:
    """'0-2, 9-11, 18-20' -> [[0, 1, 2], [9, 10, 11], [18, 19, 20]].

    Raises ValueError on anything malformed, overlapping or out of range.
    """
    zones: list[list[int]] = []
    seen: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        lo, sep, hi = part.partition("-")
        start, end = int(lo), int(hi if sep else lo)
        if not 0 <= start <= end < count:
            raise ValueError(f"segment range {part!r} outside 0-{count - 1}")
        segs = list(range(start, end + 1))
        if seen.intersection(segs):
            raise ValueError(f"segment range {part!r} overlaps another zone")
        seen.update(segs)
        zones.append(segs)
    if not zones:
        raise ValueError("no zones given")
    return sorted(zones)


def render(
    anchors: list[tuple[list[int], RGB]], count: int, mode: str = "oklch"
) -> list[RGB]:
    """Full frame of `count` segments: anchor segments get their colour,
    the gaps between neighbouring anchors are blended."""
    ordered = sorted(anchors, key=lambda a: min(a[0]))
    frame: list[RGB | None] = [None] * count
    for segments, color in ordered:
        for seg in segments:
            frame[seg] = color

    for (segs_a, col_a), (segs_b, col_b) in pairwise(ordered):
        start, end = max(segs_a), min(segs_b)
        for seg in range(start + 1, end):
            frame[seg] = mix(col_a, col_b, (seg - start) / (end - start), mode)

    first_segs, first_col = ordered[0]
    last_segs, last_col = ordered[-1]
    for seg in range(min(first_segs)):
        frame[seg] = first_col
    for seg in range(max(last_segs) + 1, count):
        frame[seg] = last_col

    return frame  # type: ignore[return-value]
