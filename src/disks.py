"""Pre-trace: snap large near-disk blobs to perfect circles."""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage


def snap_disks_in_label_image(
    img: Image.Image,
    *,
    min_area_frac: float = 0.06,
    min_disk_fill: float = 0.80,
    max_radius_cv: float = 0.09,
    max_aspect: float = 1.22,
) -> Image.Image:
    """
    Open thin bridges (circle↔shards), then replace badge disks with true circles.
    """
    if img.mode == "RGBA":
        rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
        alpha = np.asarray(img.getchannel("A"), dtype=np.uint8)
        has_a = True
    else:
        rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
        alpha = None
        has_a = False

    h, w, _ = rgb.shape
    canvas = float(h * w)
    out = rgb.copy()
    white = (rgb[:, :, 0] >= 250) & (rgb[:, :, 1] >= 250) & (rgb[:, :, 2] >= 250)

    flat = rgb.reshape(-1, 3)
    uniq = np.unique(flat, axis=0)
    colors = [
        tuple(int(x) for x in c)
        for c in uniq
        if not (int(c[0]) >= 250 and int(c[1]) >= 250 and int(c[2]) >= 250)
    ]

    # structure ~3px to cut thin AA bridges
    struct = ndimage.generate_binary_structure(2, 1)
    struct = ndimage.iterate_structure(struct, 2)

    for col in colors:
        mask = (
            (rgb[:, :, 0] == col[0])
            & (rgb[:, :, 1] == col[1])
            & (rgb[:, :, 2] == col[2])
        )
        if not mask.any():
            continue
        # disconnect shards lightly attached to badge
        opened = ndimage.binary_opening(mask, structure=struct)
        labeled, nlab = ndimage.label(opened)
        for lab in range(1, nlab + 1):
            comp = labeled == lab
            area = int(comp.sum())
            if area < canvas * min_area_frac:
                continue

            ys, xs = np.where(comp)
            y0, y1 = int(ys.min()), int(ys.max())
            x0, x1 = int(xs.min()), int(xs.max())
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            aspect = max(bw, bh) / max(1.0, min(bw, bh))
            if aspect > max_aspect:
                continue

            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            # radius from bbox (more stable than mass centroid with holes)
            r = min(bw, bh) / 2.0 * 0.99
            if r < 16:
                continue

            dists = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
            ring = dists[dists >= r * 0.88]
            if len(ring) < 40:
                continue
            cv = float(ring.std() / (ring.mean() + 1e-6))
            if cv > max_radius_cv:
                continue

            yy, xx = np.ogrid[:h, :w]
            disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= r**2
            disk_area = float(disk.sum())
            fill = area / disk_area
            if fill < min_disk_fill:
                continue

            # Clear original disk-ish pixels of this color near the disk region
            # (use original mask∩expanded disk so text holes stay white)
            clear = mask & (
                (xx - cx) ** 2 + (yy - cy) ** 2 <= (r * 1.05) ** 2
            )
            out[clear] = 255
            out[disk] = np.array(col, dtype=np.uint8)
            # restore holes that were white in source labels
            out[disk & white] = 255

    result = Image.fromarray(out, mode="RGB")
    if has_a and alpha is not None:
        result = result.convert("RGBA")
        result.putalpha(Image.fromarray(alpha, mode="L"))
    return result
