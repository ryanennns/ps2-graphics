"""Texture painting (style.md section 4): 4x supersampled canvas with bbox-clipped vector shapes,
real-typeface lettering (Canvas.type, via Blender's font engine), metric views (Canvas.frame),
window and masonry painters, correlated weathering, box-filter downsample and no-dither palette
quantization. The 5x7 bitmap FONT / Canvas.led_text is ONLY for genuinely digital displays."""
import math
import numpy as np
import OpenImageIO as oiio

SS = 4  # paint at 4x, box filter down

FONT = {
 'A':[" ### ","#   #","#   #","#####","#   #","#   #","#   #"],
 'B':["#### ","#   #","#   #","#### ","#   #","#   #","#### "],
 'C':[" ### ","#   #","#    ","#    ","#    ","#   #"," ### "],
 'D':["#### ","#   #","#   #","#   #","#   #","#   #","#### "],
 'E':["#####","#    ","#    ","#### ","#    ","#    ","#####"],
 'F':["#####","#    ","#    ","#### ","#    ","#    ","#    "],
 'G':[" ### ","#   #","#    ","# ###","#   #","#   #"," ####"],
 'H':["#   #","#   #","#   #","#####","#   #","#   #","#   #"],
 'I':[" ### ","  #  ","  #  ","  #  ","  #  ","  #  "," ### "],
 'J':["  ###","   # ","   # ","   # ","   # ","#  # "," ##  "],
 'K':["#   #","#  # ","# #  ","##   ","# #  ","#  # ","#   #"],
 'L':["#    ","#    ","#    ","#    ","#    ","#    ","#####"],
 'M':["#   #","## ##","# # #","# # #","#   #","#   #","#   #"],
 'N':["#   #","##  #","# # #","#  ##","#   #","#   #","#   #"],
 'O':[" ### ","#   #","#   #","#   #","#   #","#   #"," ### "],
 'P':["#### ","#   #","#   #","#### ","#    ","#    ","#    "],
 'Q':[" ### ","#   #","#   #","#   #","# # #","#  # "," ## #"],
 'R':["#### ","#   #","#   #","#### ","# #  ","#  # ","#   #"],
 'S':[" ####","#    ","#    "," ### ","    #","    #","#### "],
 'T':["#####","  #  ","  #  ","  #  ","  #  ","  #  ","  #  "],
 'U':["#   #","#   #","#   #","#   #","#   #","#   #"," ### "],
 'V':["#   #","#   #","#   #","#   #","#   #"," # # ","  #  "],
 'W':["#   #","#   #","#   #","# # #","# # #","# # #"," # # "],
 'X':["#   #","#   #"," # # ","  #  "," # # ","#   #","#   #"],
 'Y':["#   #","#   #"," # # ","  #  ","  #  ","  #  ","  #  "],
 'Z':["#####","    #","   # ","  #  "," #   ","#    ","#####"],
 '0':[" ### ","#   #","#  ##","# # #","##  #","#   #"," ### "],
 '1':["  #  "," ##  ","  #  ","  #  ","  #  ","  #  "," ### "],
 '2':[" ### ","#   #","    #","   # ","  #  "," #   ","#####"],
 '3':["#####","   # ","  #  ","   # ","    #","#   #"," ### "],
 '4':["   # ","  ## "," # # ","#  # ","#####","   # ","   # "],
 '5':["#####","#    ","#### ","    #","    #","#   #"," ### "],
 '6':["  ## "," #   ","#    ","#### ","#   #","#   #"," ### "],
 '7':["#####","    #","   # ","  #  "," #   "," #   "," #   "],
 '8':[" ### ","#   #","#   #"," ### ","#   #","#   #"," ### "],
 '9':[" ### ","#   #","#   #"," ####","    #","   # "," ##  "],
 '.':["     ","     ","     ","     ","     "," ##  "," ##  "],
 '-':["     ","     ","     ","#####","     ","     ","     "],
 '/':["    #","    #","   # ","  #  "," #   ","#    ","#    "],
 ' ':["     "]*7,
}


def tile_noise(h, w, cy, cx, seed):
    """Smooth periodic value noise in [-1,1], shape (h,w)."""
    rng = np.random.default_rng(seed)
    g = rng.uniform(-1, 1, (cy, cx))
    ys = np.arange(h) / h * cy
    xs = np.arange(w) / w * cx
    y0 = np.floor(ys).astype(int); fy = ys - y0; y1 = (y0 + 1) % cy; y0 %= cy
    x0 = np.floor(xs).astype(int); fx = xs - x0; x1 = (x0 + 1) % cx; x0 %= cx
    fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
    a = g[y0][:, x0]; b = g[y0][:, x1]; c = g[y1][:, x0]; d = g[y1][:, x1]
    top = a + (b - a) * fx[None]; bot = c + (d - c) * fx[None]
    return top + (bot - top) * fy[:, None]


# ---------------------------------------------------------------- shared colours (style.md section 4)
LIT = (138, 122, 92)       # the muted warm lit-pane tone; never bright orange/yellow
GLASS = (50, 60, 68)       # dark, slightly blue-tinted glass
SKY = (150, 164, 178)      # pale sky glint on the upper part of a pane
FRAME = (184, 180, 170)    # light painted/PVC window frame
DARK = (30, 32, 34)        # mullion line, deep shadow
SILL = (166, 162, 152)     # concrete/stone sill
MORTAR_DARK = (24, 24, 22)  # mortar is mixed toward this, not toward flat grey

# ---------------------------------------------------------------- real typefaces (style.md section 4)
# Short names for era-appropriate system faces. Any other name is treated as a file path.
FONTS = {
    'sans': ("Arial.ttf",),
    'sans_bold': ("Arial Bold.ttf",),
    'cond': ("Arial Narrow Bold.ttf", "DIN Condensed Bold.ttf"),
    'cond_light': ("Arial Narrow.ttf",),
    'black': ("Arial Black.ttf", "Impact.ttf"),
    'din': ("DIN Condensed Bold.ttf", "DIN Alternate Bold.ttf"),
    'humanist': ("GillSans.ttc", "Trebuchet MS.ttf"),
    'geometric': ("Futura.ttc",),
    'serif': ("Georgia.ttf", "Times New Roman.ttf"),
    'serif_bold': ("Georgia Bold.ttf", "Times New Roman Bold.ttf"),
    'times': ("Times New Roman.ttf",),
    'didone': ("Didot.ttc", "Baskerville.ttc"),
    'slab': ("Rockwell.ttc", "American Typewriter.ttc", "AmericanTypewriter.ttc"),
    'engraved': ("Copperplate.ttc",),
    'script': ("Brush Script.ttf", "SnellRoundhand.ttc"),
    'unicode': ("Arial Unicode.ttf",),
}
FONT_DIRS = ("/System/Library/Fonts/Supplemental", "/System/Library/Fonts", "/Library/Fonts",
             "~/Library/Fonts", "/usr/share/fonts/truetype", "/usr/share/fonts", "C:/Windows/Fonts")
_FONT_IDS = {}


def font_path(font):
    """Resolve a FONTS short name (or a path) to an existing font file, or None."""
    import os
    if os.path.isfile(os.path.expanduser(str(font))):
        return os.path.expanduser(str(font))
    for fn in FONTS.get(font, (font,)):
        for d in FONT_DIRS:
            p = os.path.join(os.path.expanduser(d), fn)
            if os.path.isfile(p):
                return p
    return None


def _font_id(font):
    """blf font id for a FONTS name or path. Falls back to Blender's bundled Inter (a real
    sans typeface), never to the bitmap FONT."""
    import blf
    if font not in _FONT_IDS:
        p = font_path(font)
        fid = blf.load(p) if p else -1
        if fid < 0:
            import bpy
            inter = bpy.utils.system_resource('DATAFILES', path="fonts/Inter.woff2")
            fid = blf.load(inter) if inter else -1
            print(f"PAINT font {font!r} not found; using Blender's bundled Inter")
        _FONT_IDS[font] = max(fid, 0)
    return _FONT_IDS[font]


_MASKS = {}


def type_mask(txt, font, cap_px, track_px=0.0):
    """Anti-aliased coverage mask (float32, rows top->bottom) of txt set in a real typeface with
    capital height cap_px (pixels of the array). Returns (mask, cap_top_row, baseline_row)."""
    key = (txt, font, round(cap_px, 3), round(track_px, 3))
    if key in _MASKS:
        return _MASKS[key]
    import blf
    import imbuf
    fid = _font_id(font)
    probe = imbuf.new((8, 8))
    with blf.bind_imbuf(fid, probe):
        blf.size(fid, 100)
        cap100 = blf.dimensions(fid, "H")[1]
        size = cap_px * 100.0 / max(cap100, 1e-3)
        blf.size(fid, size)
        full = blf.dimensions(fid, txt)[0]
        starts = [blf.dimensions(fid, txt[:i])[0] for i in range(len(txt))]
    pad = int(cap_px * 0.8) + 8
    wdt = int(full + abs(track_px) * max(len(txt) - 1, 0) + 2 * pad)
    hgt = int(cap_px * 1.7 + 2 * pad)
    ib = imbuf.new((max(wdt, 1), max(hgt, 1)))
    with blf.bind_imbuf(fid, ib):
        blf.size(fid, size)
        blf.color(fid, 1, 1, 1, 1)
        if not track_px:
            blf.position(fid, pad, pad, 0)
            blf.draw_buffer(fid, txt)
        else:
            for i, ch in enumerate(txt):
                if not ch.isspace():
                    blf.position(fid, pad + starts[i] + i * track_px, pad, 0)
                    blf.draw_buffer(fid, ch)
    with ib.with_buffer() as mv:
        a = np.array(mv, dtype=np.float32)
    m = np.ascontiguousarray(a[::-1, :, 3] / 255.0)
    base_row = hgt - 1 - pad
    _MASKS[key] = (m, base_row - cap_px, base_row)
    return _MASKS[key]


class Canvas:
    """Paint at final-pixel coordinates (x right, y DOWN, row 0 = top); stored at SS x for
    soft box-filtered edges. All shapes accept alpha; wrap=True repeats horizontally for tiles."""

    def __init__(s, w, h, color):
        s.w, s.h = w, h
        s.a = np.zeros((h * SS, w * SS, 3), np.float32)
        s.a[:] = color

    def _px(s, v, lim):
        return int(max(0, min(lim, round(v * SS))))

    # ------------------------------------------------------------ rectangles
    def rect(s, x0, y0, x1, y1, c, alpha=1.0):
        X0, X1 = s._px(x0, s.w * SS), s._px(x1, s.w * SS)
        Y0, Y1 = s._px(y0, s.h * SS), s._px(y1, s.h * SS)
        if X1 <= X0 or Y1 <= Y0:
            return
        reg = s.a[Y0:Y1, X0:X1]
        reg[:] = reg * (1 - alpha) + np.array(c, np.float32) * alpha

    def rect_wrap(s, x0, y0, x1, y1, c, alpha=1.0):
        for off in (-s.w, 0, s.w):
            s.rect(x0 + off, y0, x1 + off, y1, c, alpha)

    def mul(s, x0, y0, x1, y1, f):
        X0, X1 = s._px(x0, s.w * SS), s._px(x1, s.w * SS)
        Y0, Y1 = s._px(y0, s.h * SS), s._px(y1, s.h * SS)
        s.a[Y0:Y1, X0:X1] *= f

    def mul_wrap(s, x0, y0, x1, y1, f):
        for off in (-s.w, 0, s.w):
            s.mul(x0 + off, y0, x1 + off, y1, f)

    # ------------------------------------------------------------ mask plumbing
    def _grid(s, x0, y0, x1, y1):
        """Sample-centre coordinates (final px) of the SS grid clipped to a bbox, or None."""
        X0 = max(0, int(math.floor(x0 * SS))); X1 = min(s.w * SS, int(math.ceil(x1 * SS)))
        Y0 = max(0, int(math.floor(y0 * SS))); Y1 = min(s.h * SS, int(math.ceil(y1 * SS)))
        if X1 <= X0 or Y1 <= Y0:
            return None
        xs = ((np.arange(X0, X1) + 0.5) / SS)[None, :]
        ys = ((np.arange(Y0, Y1) + 0.5) / SS)[:, None]
        return X0, Y0, np.broadcast_to(xs, (Y1 - Y0, X1 - X0)), np.broadcast_to(ys, (Y1 - Y0, X1 - X0))

    def blend_mask(s, X0, Y0, m, c):
        """Composite colour c through a float coverage mask m placed at SS-pixel (X0, Y0)."""
        H, W = s.a.shape[:2]
        y0, x0 = max(0, Y0), max(0, X0)
        y1, x1 = min(H, Y0 + m.shape[0]), min(W, X0 + m.shape[1])
        if y1 <= y0 or x1 <= x0:
            return
        mm = m[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0][..., None]
        reg = s.a[y0:y1, x0:x1]
        reg[:] = reg * (1 - mm) + np.asarray(c, np.float32) * mm

    def _shape(s, bbox, fn, c, alpha, wrap):
        for off in ((-s.w, 0, s.w) if wrap else (0,)):
            g = s._grid(bbox[0] + off, bbox[1], bbox[2] + off, bbox[3])
            if g is None:
                continue
            X0, Y0, xs, ys = g
            m = fn(xs - off, ys).astype(np.float32) * alpha
            s.blend_mask(X0, Y0, m, c)

    # ------------------------------------------------------------ vector shapes
    def polygon(s, pts, c, alpha=1.0, wrap=False):
        """Filled polygon (even-odd rule), any winding."""
        pts = [(float(p[0]), float(p[1])) for p in pts]
        px = [p[0] for p in pts]; py = [p[1] for p in pts]

        def fn(xs, ys):
            inside = np.zeros(xs.shape, bool)
            for i in range(len(pts)):
                (xa, ya), (xb, yb) = pts[i], pts[i - 1]
                if ya == yb:
                    continue
                inside ^= ((ya > ys) != (yb > ys)) & (xs < (xb - xa) * (ys - ya) / (yb - ya) + xa)
            return inside
        s._shape((min(px), min(py), max(px), max(py)), fn, c, alpha, wrap)

    def ellipse(s, cx, cy, rx, ry=None, c=(0, 0, 0), alpha=1.0, inner=0.0, wrap=False):
        """Filled ellipse; inner in 0..1 makes a ring (inner radius = inner x outer)."""
        ry = rx if ry is None else ry

        def fn(xs, ys):
            d = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2
            return (d <= 1.0) & (d >= inner * inner)
        s._shape((cx - rx, cy - ry, cx + rx, cy + ry), fn, c, alpha, wrap)

    def disc(s, cx, cy, r, c, alpha=1.0, inner=0.0, wrap=False):
        s.ellipse(cx, cy, r, r, c, alpha, inner, wrap)

    def rrect(s, x0, y0, x1, y1, r, c, alpha=1.0, wrap=False):
        """Rounded rectangle with corner radius r."""
        r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))

        def fn(xs, ys):
            dx = np.maximum(np.maximum(x0 + r - xs, xs - (x1 - r)), 0)
            dy = np.maximum(np.maximum(y0 + r - ys, ys - (y1 - r)), 0)
            return (dx * dx + dy * dy <= r * r) & (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
        s._shape((x0, y0, x1, y1), fn, c, alpha, wrap)

    def line(s, pts, w, c, alpha=1.0, wrap=False, round_joins=True):
        """Thick polyline through pts [(x, y), ...] with width w (final px)."""
        pts = [(float(p[0]), float(p[1])) for p in pts]
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            L = math.hypot(xb - xa, yb - ya)
            if L < 1e-9:
                continue
            nx, ny = -(yb - ya) / L * w / 2, (xb - xa) / L * w / 2
            s.polygon([(xa + nx, ya + ny), (xb + nx, yb + ny), (xb - nx, yb - ny), (xa - nx, ya - ny)], c, alpha, wrap)
        if round_joins and alpha >= 1.0:
            for p in pts[1:-1]:
                s.disc(p[0], p[1], w / 2, c, alpha, wrap=wrap)

    def star(s, cx, cy, r, c, points=5, inner=0.42, rot=-90.0, alpha=1.0, wrap=False):
        pts = []
        for i in range(points * 2):
            rr = r if i % 2 == 0 else r * inner
            a = math.radians(rot + i * 180.0 / points)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        s.polygon(pts, c, alpha, wrap)

    def grad(s, x0, y0, x1, y1, c0, c1, axis='y', alpha=1.0):
        """Fill a rect with a linear ramp c0 -> c1 (top->bottom for axis 'y', left->right for 'x')."""
        g = s._grid(x0, y0, x1, y1)
        if g is None:
            return
        X0, Y0, xs, ys = g
        t = np.clip((ys - y0) / max(y1 - y0, 1e-9) if axis == 'y' else (xs - x0) / max(x1 - x0, 1e-9), 0, 1)[..., None]
        col = np.asarray(c0, np.float32) * (1 - t) + np.asarray(c1, np.float32) * t
        reg = s.a[Y0:Y0 + xs.shape[0], X0:X0 + xs.shape[1]]
        reg[:] = reg * (1 - alpha) + col * alpha

    def gmul(s, x0, y0, x1, y1, f0, f1, axis='y'):
        """Multiply a rect by a linear brightness ramp f0 -> f1 (soft shadows, grime, AO)."""
        g = s._grid(x0, y0, x1, y1)
        if g is None:
            return
        X0, Y0, xs, ys = g
        t = np.clip((ys - y0) / max(y1 - y0, 1e-9) if axis == 'y' else (xs - x0) / max(x1 - x0, 1e-9), 0, 1)
        s.a[Y0:Y0 + xs.shape[0], X0:X0 + xs.shape[1]] *= (f0 + (f1 - f0) * t)[..., None]

    # ------------------------------------------------------------ lettering
    def type(s, txt, x, y, cap, c, font='sans', align='l', valign='top', track=0.0, sx=1.0,
             max_w=None, alpha=1.0, wrap=False):
        """Set txt in a REAL typeface (style.md section 4), rasterized smoothly at SS x.
        x: left edge / centre / right edge per align ('l' 'c' 'r'); y: cap top, cap middle or
        baseline per valign ('top' 'middle' 'base'); cap: capital height in final px;
        track: extra letter spacing (final px); sx: horizontal scale (condense < 1 < extend);
        max_w: condense further if needed so the ink fits this width. Returns the ink width."""
        m, cap_top, base = type_mask(str(txt), font, cap * SS, track * SS / max(sx, 1e-3))
        cols = np.where(m.max(0) > 0.02)[0]
        if cols.size == 0:
            return 0.0
        m = m[:, cols[0]:cols[-1] + 1]
        if max_w is not None and m.shape[1] * sx > max_w * SS:
            sx = max_w * SS / m.shape[1]
        if sx != 1.0:
            nw = max(1, int(round(m.shape[1] * sx)))
            src = (np.arange(nw) + 0.5) / sx - 0.5
            i0 = np.clip(np.floor(src).astype(int), 0, m.shape[1] - 1)
            i1 = np.clip(i0 + 1, 0, m.shape[1] - 1)
            f = np.clip(src - np.floor(src), 0, 1)[None]
            m = m[:, i0] * (1 - f) + m[:, i1] * f
        wpx = m.shape[1]
        X0 = int(round(x * SS)) - {'l': 0, 'c': wpx // 2, 'r': wpx}[align]
        anchor = {'top': cap_top, 'middle': (cap_top + base) / 2, 'base': base}[valign]
        Y0 = int(round(y * SS - anchor))
        for off in ((-s.w, 0, s.w) if wrap else (0,)):
            s.blend_mask(X0 + off * SS, Y0, m * alpha, c)
        return wpx / SS

    def type_width(s, txt, cap, font='sans', track=0.0, sx=1.0):
        """Ink width (final px) that type() would produce, for layout."""
        m, _, _ = type_mask(str(txt), font, cap * SS, track * SS / max(sx, 1e-3))
        cols = np.where(m.max(0) > 0.02)[0]
        return 0.0 if cols.size == 0 else (cols[-1] - cols[0] + 1) * sx / SS

    # Legacy 5x7 bitmap font. ONLY for genuinely digital displays (dot-matrix, LED, scoreboard)
    # whose reference calls for it; style.md forbids it for any physical lettering.
    def text(s, txt, x, y, scale, c):
        cx = x
        for ch in txt.upper():
            g = FONT.get(ch, FONT[' '])
            for r, row in enumerate(g):
                for k, bit in enumerate(row):
                    if bit == '#':
                        s.rect(cx + k * scale, y + r * scale, cx + (k + 1) * scale, y + (r + 1) * scale, c)
            cx += 6 * scale

    def text_c(s, txt, cxm, y, scale, c):
        w = (6 * len(txt) - 1) * scale
        s.text(txt, cxm - w / 2, y, scale, c)

    led_text = text      # preferred names: the intent (digital displays only) is in the name
    led_text_c = text_c

    # ------------------------------------------------------------ architectural painters
    def window(s, x0, y0, x1, y1, panes=2, rows=1, lit=False, frame=FRAME, glass=GLASS, sky=SKY,
               mullion=DARK, sill=SILL, fw=None, glint=0.38, reveal=0.75, curtain=None):
        """A window painted in the style.md section 4 order: frame/sill, dark glass, pale sky glint
        on the upper part of each pane, dark mullion line. lit=True uses the muted LIT tone (light
        ~10% of panes). fw: frame width (default ~8% of the smaller side). Units: final px."""
        w, h = x1 - x0, y1 - y0
        fw = max(0.35, 0.08 * min(w, h)) if fw is None else fw
        if reveal:
            s.mul(x0 - fw * 0.6, y0 - fw * 0.6, x1 + fw * 0.6, y1, reveal)   # reveal shadow
        s.rect(x0, y0, x1, y1, frame)                                        # 1. frame
        if sill:
            s.rect(x0 - fw * 0.8, y1, x1 + fw * 0.8, y1 + fw * 1.1, sill)
            s.mul(x0 - fw * 0.8, y1 + fw * 1.1, x1 + fw * 0.8, y1 + fw * 1.6, 0.85)
        pw, ph = (w - fw) / panes, (h - fw) / rows
        for j in range(rows):
            for i in range(panes):
                gx0, gy0 = x0 + fw + i * pw, y0 + fw + j * ph
                gx1, gy1 = gx0 + pw - fw, gy0 + ph - fw
                s.rect(gx0, gy0, gx1, gy1, LIT if lit is True else (lit or glass))   # 2. glass
                if curtain and not lit:
                    cw = (gx1 - gx0) * 0.28
                    s.rect(gx0, gy0, gx0 + cw, gy1, curtain, 0.8)
                    s.rect(gx1 - cw, gy0, gx1, gy1, curtain, 0.8)
                if not lit and glint:
                    s.rect(gx0, gy0, gx1, gy0 + (gy1 - gy0) * glint, sky, 0.42)      # 3. sky glint
                s.rect(gx0, gy0, gx1, gy0 + max(0.25, fw * 0.35), mullion, 0.55)    # head shadow
        for i in range(1, panes):                                            # 4. mullion line
            mx = x0 + fw / 2 + i * pw
            s.rect(mx + fw * 0.5, y0 + fw, mx + fw * 0.5 + max(0.25, fw * 0.3), y1 - fw, mullion, 0.8)

    def masonry(s, x0, y0, x1, y1, color, course=(0.9, 1.4), length=(2.2, 3.6), joint=0.35,
                mortar=None, var=0.07, seed=1, edge=0.08, bond=0.5):
        """Coursed masonry/brick (style.md section 4): real block structure with varied course
        heights, lighter top/left and darker bottom/right edges, mortar mixed toward near-black.
        course/length: (min, max) course height and block length in final px; joint: mortar width;
        bond: course-to-course offset as a fraction of a block (0.5 = running bond). Courses fill
        the rect exactly and blocks wrap horizontally, so a full-canvas call tiles seamlessly."""
        rng = np.random.default_rng(seed)
        color = np.asarray(color, np.float32)
        mortar = mix(tuple(color * 0.82), MORTAR_DARK, 0.55) if mortar is None else mortar
        H, W = y1 - y0, x1 - x0
        s.rect(x0, y0, x1, y1, mortar)
        n = max(1, int(round(H / ((course[0] + course[1]) / 2))))
        hs = rng.uniform(*course, n); hs *= H / hs.sum()
        y, shift = y0, rng.uniform(0, 1)
        avg = (length[0] + length[1]) / 2
        for k, ch in enumerate(hs):
            m = max(1, int(round(W / avg)))
            ls = rng.uniform(*length, m); ls *= W / ls.sum()
            x = x0 + ((shift + k * bond) % 1.0) * ls[0]
            for L in ls:
                c = color * (1 + rng.uniform(-var, var))
                c = c + np.array((1, 0, -1), np.float32) * rng.uniform(-1, 1) * var * 40
                bx0, by0, bx1, by1 = x + joint / 2, y + joint / 2, x + L - joint / 2, y + ch - joint / 2
                full = (x0, x1) == (0, s.w)
                if not full:
                    bx0, bx1 = max(bx0, x0), min(bx1, x1)
                    if bx1 <= bx0:
                        x += L
                        continue
                for off in ((0, -W, W) if full else (0,)):
                    s.rect(bx0 + off, by0, bx1 + off, by1, tuple(c))
                    e = max(0.25, min(ch, L) * edge)
                    s.rect(bx0 + off, by0, bx1 + off, by0 + e, (255, 255, 255), 0.10)   # lit top
                    s.rect(bx0 + off, by0, bx0 + off + e, by1, (255, 255, 255), 0.06)   # lit left
                    s.mul(bx0 + off, by1 - e, bx1 + off, by1, 0.82)                    # dark bottom
                    s.mul(bx1 + off - e, by0, bx1 + off, by1, 0.88)                    # dark right
                x += L
            y += ch

    # ------------------------------------------------------------ weathering / output
    def weather(s, amt, cells, seed, tint=0.012, region=None):
        H, W = s.a.shape[:2]
        cy = max(1, round(cells * s.h / max(s.w, s.h))) if isinstance(cells, int) else cells[0]
        cx = max(1, round(cells * s.w / max(s.w, s.h))) if isinstance(cells, int) else cells[1]
        n = tile_noise(H, W, cy, cx, seed)
        if region is not None:
            n = n * region
        s.a *= (1 + amt * n)[..., None]
        s.a[..., 0] += tint * n * 255
        s.a[..., 2] -= tint * n * 255

    def frame(s, x0, z0, x1, z1, px=None):
        """A metric view of this canvas: world/face coordinates (x right, z UP, in metres) of the
        rect x0..x1 by z0..z1 map onto the canvas (or onto px=(px0, py0, px1, py1) of it, for
        atlases). The view's methods take metres. See Frame."""
        return Frame(s, x0, z0, x1, z1, px)

    def finish(s, k=40):
        H, W = s.h, s.w
        a = s.a.reshape(H, SS, W, SS, 3).mean(axis=(1, 3))
        a = np.clip(a, 0, 255)
        return quantize(a, k)


class Frame:
    """Metre-space painter over a Canvas region (see Canvas.frame). z increases upward.
    Lengths (line width, radii, cap height, frame width) are in metres too."""

    def __init__(s, canvas, x0, z0, x1, z1, px=None):
        s.c = canvas
        s.x0, s.z0, s.x1, s.z1 = x0, z0, x1, z1
        s.p0, s.q0, s.p1, s.q1 = px or (0, 0, canvas.w, canvas.h)
        s.kx = (s.p1 - s.p0) / (x1 - x0)          # px per metre, horizontal
        s.kz = (s.q1 - s.q0) / (z1 - z0)          # px per metre, vertical

    def X(s, x):
        return s.p0 + (x - s.x0) * s.kx

    def Y(s, z):
        return s.q0 + (s.z1 - z) * s.kz

    def P(s, x, z):
        return (s.X(x), s.Y(z))

    def _r(s, x0, z0, x1, z1):
        return min(s.X(x0), s.X(x1)), min(s.Y(z0), s.Y(z1)), max(s.X(x0), s.X(x1)), max(s.Y(z0), s.Y(z1))

    def rect(s, x0, z0, x1, z1, c, alpha=1.0):
        s.c.rect(*s._r(x0, z0, x1, z1), c, alpha)

    def mul(s, x0, z0, x1, z1, f):
        s.c.mul(*s._r(x0, z0, x1, z1), f)

    def polygon(s, pts, c, alpha=1.0, wrap=False):
        s.c.polygon([s.P(*p) for p in pts], c, alpha, wrap)

    def line(s, pts, w, c, alpha=1.0, wrap=False):
        s.c.line([s.P(*p) for p in pts], w * (s.kx + s.kz) / 2, c, alpha, wrap)

    def ellipse(s, x, z, rx, rz=None, c=(0, 0, 0), alpha=1.0, inner=0.0, wrap=False):
        s.c.ellipse(s.X(x), s.Y(z), rx * s.kx, (rx if rz is None else rz) * s.kz, c, alpha, inner, wrap)

    def disc(s, x, z, r, c, alpha=1.0, inner=0.0):
        s.ellipse(x, z, r, r, c, alpha, inner)

    def rrect(s, x0, z0, x1, z1, r, c, alpha=1.0):
        s.c.rrect(*s._r(x0, z0, x1, z1), r * (s.kx + s.kz) / 2, c, alpha)

    def grad(s, x0, z0, x1, z1, c_bottom, c_top, alpha=1.0):
        s.c.grad(*s._r(x0, z0, x1, z1), c_top, c_bottom, 'y', alpha)

    def gmul(s, x0, z0, x1, z1, f_bottom, f_top):
        s.c.gmul(*s._r(x0, z0, x1, z1), f_top, f_bottom, 'y')

    def type(s, txt, x, z, cap, c, font='sans', align='l', valign='base', track=0.0, sx=1.0, max_w=None, alpha=1.0):
        """Real-typeface lettering; z is the baseline by default (valign 'base' 'middle' 'top')."""
        return s.c.type(txt, s.X(x), s.Y(z), cap * s.kz, c, font, align, valign, track * s.kx, sx,
                        None if max_w is None else max_w * s.kx, alpha) / s.kx

    def window(s, x0, z0, x1, z1, fw=None, **kw):
        """Canvas.window in metres (sill height z0, head z1); fw in metres (default 0.07 m)."""
        s.c.window(*s._r(x0, z0, x1, z1), fw=(0.07 if fw is None else fw) * s.kx, **kw)

    def masonry(s, x0, z0, x1, z1, color, course=(0.07, 0.09), length=(0.22, 0.30), joint=0.012, **kw):
        """Canvas.masonry in metres (defaults: brick courses 70-90 mm, 220-300 mm blocks)."""
        s.c.masonry(*s._r(x0, z0, x1, z1), color, tuple(v * s.kz for v in course),
                    tuple(v * s.kx for v in length), joint * s.kx, **kw)


def quantize(img, k):
    px = img.reshape(-1, 3).astype(np.float32)
    rpx = np.round(px)
    uniq = np.unique(rpx, axis=0)
    if len(uniq) <= k:
        return rpx.reshape(img.shape).astype(np.uint8)
    lum = px @ np.array([0.3, 0.59, 0.11], np.float32)
    order = np.argsort(lum)
    nq = k // 2
    cent = [px[order[i]] for i in np.linspace(0, len(px) - 1, nq).astype(int)]
    # farthest-point picks keep small saturated details (text, stripes)
    d = np.min(((px[:, None, :] - np.array(cent)[None]) ** 2).sum(-1), axis=1)
    while len(cent) < k:
        i = int(d.argmax())
        cent.append(px[i])
        d = np.minimum(d, ((px - px[i]) ** 2).sum(-1))
    cent = np.array(cent, np.float32)
    for _ in range(12):
        lab = ((px[:, None, :] - cent[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            m = lab == j
            if m.any():
                cent[j] = px[m].mean(0)
    lab = ((px[:, None, :] - cent[None]) ** 2).sum(-1).argmin(1)
    return np.round(cent[lab]).reshape(img.shape).astype(np.uint8)


def save_png(path, arr):
    """Write an RGB uint8 array (row 0 = top) as a PNG with no alpha."""
    h, w = arr.shape[:2]
    assert (w & (w - 1)) == 0 and (h & (h - 1)) == 0, f"not power-of-two: {path} {w}x{h}"
    assert arr.ndim == 3 and arr.shape[2] == 3, f"must be RGB: {path}"
    out = oiio.ImageOutput.create(path)
    out.open(path, oiio.ImageSpec(w, h, 3, 'uint8'))
    out.write_image(np.ascontiguousarray(arr))
    out.close()
    return path


def shade(c, f):
    return tuple(min(255, v * f) for v in c)


def mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def plain(color, size=16, amt=0.05, seed=1, cells=4):
    c = Canvas(size, size, color)
    c.weather(amt, cells, seed)
    c.weather(amt * 0.5, cells * 2, seed + 7, tint=0.006)
    return c


class TextureSet:
    """Registry of texture painters for one asset. Decorate painters named t_<name>."""

    def __init__(s, colors=40):
        s.fns, s.colors = {}, colors

    def __call__(s, fn):
        s.fns[fn.__name__[2:]] = fn
        return fn

    def build(s, out_dir):
        import os
        os.makedirs(out_dir, exist_ok=True)
        return {n: save_png(os.path.join(out_dir, n + ".png"), fn().finish(s.colors)) for n, fn in s.fns.items()}
