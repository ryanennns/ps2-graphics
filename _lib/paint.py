"""Texture painting: 4x supersampled canvas, bitmap font, correlated weathering,
box-filter downsample and no-dither palette quantization (style.md section 4)."""
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


class Canvas:
    def __init__(s, w, h, color):
        s.w, s.h = w, h
        s.a = np.zeros((h * SS, w * SS, 3), np.float32)
        s.a[:] = color

    def _px(s, v, lim):
        return int(max(0, min(lim, round(v * SS))))

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

    def finish(s, k=40):
        H, W = s.h, s.w
        a = s.a.reshape(H, SS, W, SS, 3).mean(axis=(1, 3))
        a = np.clip(a, 0, 255)
        return quantize(a, k)


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
