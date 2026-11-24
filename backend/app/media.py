"""Image, audio and video conversion."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

from . import formats as F
from .util import ToolError, ext_of, human_size, run

try:  # HEIC / HEIF (iPhone photos) and AVIF support
    import pillow_heif

    pillow_heif.register_heif_opener()
    if hasattr(pillow_heif, "register_avif_opener"):
        try:
            pillow_heif.register_avif_opener()
        except Exception:
            pass
except Exception:  # pragma: no cover
    pass

Image.MAX_IMAGE_PIXELS = 120_000_000  # big scans are fine; decompression bombs (>240 MP) are refused

PIL_FORMAT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "avif": "AVIF", "gif": "GIF", "bmp": "BMP",
              "tiff": "TIFF", "tif": "TIFF", "ico": "ICO"}
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


# --------------------------------------------------------------------------- images

def svg_to_png(data: bytes, width: int | None = None) -> bytes:
    import cairosvg

    try:
        return cairosvg.svg2png(bytestring=data, output_width=width, unsafe=False)
    except Exception as exc:
        raise ToolError("This SVG could not be rendered.") from exc


def open_image(path: Path, all_frames: bool = False) -> list[Image.Image]:
    """Open any supported image (incl. SVG, HEIC, AVIF, PSD); returns frames with EXIF rotation applied."""
    e = ext_of(path.name)
    try:
        if e == "svg":
            im = Image.open(io.BytesIO(svg_to_png(path.read_bytes(), 2048)))
            im.load()
            return [im]
        im = Image.open(path)
        frames = []
        n = getattr(im, "n_frames", 1) if all_frames else 1
        for i in range(n):
            if n > 1:
                im.seek(i)
            fr = ImageOps.exif_transpose(im.copy()) if i == 0 else im.copy()
            frames.append(fr)
        return frames
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"'{path.name}' could not be read as an image.") from exc


def _flatten(im: Image.Image, background: str = "#ffffff") -> Image.Image:
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, background)
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB") if im.mode not in ("RGB", "L") else im


def _resize(im: Image.Image, width: int | None, height: int | None, fit: str = "contain") -> Image.Image:
    if not width and not height:
        return im
    w0, h0 = im.size
    if width and not height:
        height = max(1, round(h0 * width / w0))
    elif height and not width:
        width = max(1, round(w0 * height / h0))
    assert width and height
    if fit == "stretch":
        return im.resize((width, height), Image.LANCZOS)
    if fit == "cover":
        return ImageOps.fit(im, (width, height), Image.LANCZOS)
    s = min(width / w0, height / h0)  # fit inside the box, keeping the aspect ratio
    return im.resize((max(1, round(w0 * s)), max(1, round(h0 * s))), Image.LANCZOS)


def save_image(im: Image.Image | list[Image.Image], dst: Path, fmt: str, quality: int = 88, lossless: bool = False,
               background: str = "#ffffff", ico_sizes: list[int] | None = None) -> Path:
    frames = im if isinstance(im, list) else [im]
    first = frames[0]
    fmt = fmt.lower()
    if fmt in ("jpg", "jpeg"):
        _flatten(first, background).save(dst, format="JPEG", quality=quality, optimize=True, progressive=True)
    elif fmt == "png":
        out = first if first.mode in ("RGBA", "RGB", "L", "LA", "P") else first.convert("RGBA")
        out.save(dst, format="PNG", optimize=True)
    elif fmt in ("webp", "avif"):
        if len(frames) > 1 and fmt == "webp":
            frames[0].save(dst, format="WEBP", save_all=True, append_images=frames[1:], quality=quality,
                           lossless=lossless, duration=first.info.get("duration", 100), loop=0)
        else:
            try:
                first.save(dst, format=PIL_FORMAT[fmt], quality=quality, lossless=lossless)
            except (KeyError, OSError) as exc:
                raise ToolError(f"{fmt.upper()} output isn't supported on this server.") from exc
    elif fmt == "gif":
        if len(frames) > 1:
            frames[0].save(dst, format="GIF", save_all=True, append_images=frames[1:], loop=0,
                           duration=first.info.get("duration", 100), disposal=2, optimize=True)
        else:
            first.convert("RGBA").save(dst, format="GIF", optimize=True)
    elif fmt == "bmp":
        _flatten(first, background).save(dst, format="BMP")
    elif fmt in ("tiff", "tif"):
        frames[0].save(dst, format="TIFF", compression="tiff_deflate", save_all=len(frames) > 1, append_images=frames[1:])
    elif fmt == "ico":
        sq = _square(first.convert("RGBA"))
        sizes = [s for s in (ico_sizes or ICO_SIZES) if s <= max(sq.size)] or [min(sq.size)]
        sq.save(dst, format="ICO", sizes=[(s, s) for s in sizes])
    else:
        raise ToolError(f"Unsupported image format: {fmt.upper()}")
    return dst


def _square(im: Image.Image) -> Image.Image:
    w, h = im.size
    if w == h:
        return im
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas


def image_to_svg(src: Path, dst: Path, mode: str = "trace", colors: str = "color", detail: str = "medium") -> Path:
    """Vectorise a raster image (true paths) or wrap it losslessly inside an SVG."""
    if mode == "embed":
        im = open_image(src)[0]
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        w, h = im.size
        dst.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                       f'width="{w}" height="{h}" viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" '
                       f'href="data:image/png;base64,{b64}"/></svg>', encoding="utf-8")
        return dst
    import re

    import vtracer

    im = open_image(src)[0].convert("RGBA")
    if max(im.size) > 2000:
        im.thumbnail((2000, 2000), Image.LANCZOS)
    alpha = im.getchannel("A")
    transparent = alpha.getextrema()[0] < 128
    key = (255, 0, 254)
    if transparent:
        # Paint transparent areas with a unique key colour, trace, then drop the key-coloured paths.
        flat = Image.new("RGB", im.size, key)
        flat.paste(im.convert("RGB"), mask=alpha.point(lambda a: 255 if a >= 128 else 0))
        im = flat
    tmp = dst.with_suffix(".trace.png")
    im.save(tmp, format="PNG")
    presets = {"low": (8, 5, 24, 6.0), "medium": (4, 6, 16, 4.0), "high": (2, 8, 8, 3.5)}
    speckle, precision, layer_diff, length = presets.get(detail, presets["medium"])
    vtracer.convert_image_to_svg_py(
        str(tmp), str(dst), colormode="binary" if colors == "bw" else "color", hierarchical="stacked", mode="spline",
        filter_speckle=speckle, color_precision=precision, layer_difference=layer_diff, corner_threshold=60,
        length_threshold=length, max_iterations=10, splice_threshold=45, path_precision=3,
    )
    tmp.unlink(missing_ok=True)
    svg = re.sub(r"<!--.*?-->\s*", "", dst.read_text(encoding="utf-8"), flags=re.S)
    dst.write_text(svg, encoding="utf-8")
    if transparent and colors != "bw":

        def is_key(m: re.Match) -> bool:
            h = m.group(1)
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return abs(r - key[0]) + abs(g - key[1]) + abs(b - key[2]) < 60

        svg = re.sub(r'<path[^>]*fill="#([0-9A-Fa-f]{6})"[^>]*/>\s*', lambda m: "" if is_key(m) else m.group(0), svg)
        dst.write_text(svg, encoding="utf-8")
    return dst


def convert_image(src: Path, dst_dir: Path, base: str, fmt: str, opts: dict) -> list[Path]:
    fmt = {"jpeg": "jpg", "tif": "tiff"}.get(fmt, fmt)
    dst = dst_dir / f"{base}.{fmt}"
    if fmt == "svg":
        if ext_of(src.name) == "svg":
            dst.write_bytes(src.read_bytes())
            return [dst]
        return [image_to_svg(src, dst, opts.get("svg_mode", "trace"), opts.get("svg_colors", "color"), opts.get("svg_detail", "medium"))]
    if fmt == "pdf":
        from .convert import images_to_pdf, to_pdf

        return [to_pdf(src, dst_dir, src.name) if ext_of(src.name) == "svg" else images_to_pdf([src], dst)]
    animated = fmt in ("gif", "webp") and ext_of(src.name) in ("gif", "webp")
    frames = open_image(src, all_frames=animated)
    w, h = int(opts.get("width") or 0) or None, int(opts.get("height") or 0) or None
    frames = [_resize(f, w, h, opts.get("fit", "contain")) for f in frames]
    if fmt == "ico":
        sizes = [int(s) for s in (opts.get("ico_sizes") or [16, 32, 48, 64, 128, 256])]
        return [save_image(frames, dst, "ico", ico_sizes=sizes)]
    return [save_image(frames, dst, fmt, int(opts.get("quality", 88) or 88), bool(opts.get("lossless")),
                       opts.get("background", "#ffffff"))]


def compress_image(src: Path, dst_dir: Path, base: str, quality: int = 75, target_kb: float = 0, max_side: int = 0,
                   out_fmt: str = "same") -> tuple[Path, str]:
    e = ext_of(src.name)
    fmt = e if out_fmt == "same" else out_fmt
    fmt = {"jpeg": "jpg", "jfif": "jpg", "heic": "jpg", "heif": "jpg", "tif": "jpg", "tiff": "jpg", "bmp": "jpg", "svg": "png"}.get(fmt, fmt)
    if fmt not in ("jpg", "png", "webp", "avif", "gif"):
        fmt = "jpg"
    im = open_image(src)[0]
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    dst = dst_dir / f"{base}_compressed.{fmt}"
    original = src.stat().st_size

    def encode(q: int, img: Image.Image) -> bytes:
        buf = io.BytesIO()
        if fmt == "png":
            # palette quantisation keeps PNGs small while staying lossless-looking
            pal = img.convert("RGBA").quantize(colors=max(16, min(256, q * 3)), method=Image.Quantize.FASTOCTREE)
            pal.save(buf, format="PNG", optimize=True)
        elif fmt == "gif":
            img.convert("RGBA").save(buf, format="GIF", optimize=True)
        elif fmt == "jpg":
            _flatten(img).save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        else:
            img.save(buf, format=PIL_FORMAT[fmt], quality=q)
        return buf.getvalue()

    data = encode(quality, im)
    if target_kb and target_kb > 0:
        target = target_kb * 1024
        lo, hi, best = 5, 95, None
        img = im
        for _ in range(3):  # shrink dimensions if quality alone can't reach the target
            lo, hi = 5, 95
            while lo <= hi:
                mid = (lo + hi) // 2
                d = encode(mid, img)
                if len(d) <= target:
                    best, lo = d, mid + 1
                else:
                    hi = mid - 1
            if best is not None:
                break
            img = img.resize((max(1, int(img.width * 0.75)), max(1, int(img.height * 0.75))), Image.LANCZOS)
        data = best if best is not None else encode(5, img)
    dst.write_bytes(data)
    new = dst.stat().st_size
    if new >= original and not target_kb and fmt == e:
        dst.write_bytes(src.read_bytes())
        return dst, "This image is already well optimised — we kept the original."
    note = f"{human_size(original)} → {human_size(new)} ({100 - new * 100 / max(original, 1):.0f}% smaller)."
    if target_kb and new > target_kb * 1024:
        note += f" Smallest possible; above your {target_kb:g} KB target."
    return dst, note


def edit_image(src: Path, dst_dir: Path, base: str, rotate: int = 0, flip: str = "none", width: int = 0,
               height: int = 0, percent: float = 0, fit: str = "contain", grayscale: bool = False,
               strip_metadata: bool = True) -> Path:
    e = ext_of(src.name)
    out_fmt = e if e in ("jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif", "avif") else "png"
    frames = open_image(src, all_frames=e in ("gif", "webp"))
    result = []
    for im in frames:
        if percent and percent > 0:
            im = im.resize((max(1, round(im.width * percent / 100)), max(1, round(im.height * percent / 100))), Image.LANCZOS)
        elif width or height:
            im = _resize(im, width or None, height or None, fit)
        if rotate % 360:
            im = im.rotate(-rotate, expand=True, fillcolor=(255, 255, 255, 0) if im.mode == "RGBA" else None)
        if flip in ("horizontal", "both"):
            im = ImageOps.mirror(im)
        if flip in ("vertical", "both"):
            im = ImageOps.flip(im)
        if grayscale:
            im = ImageOps.grayscale(im) if im.mode != "RGBA" else im.convert("LA")
        result.append(im)
    dst = dst_dir / f"{base}_edited.{'jpg' if out_fmt == 'jpeg' else out_fmt}"
    save_image(result, dst, out_fmt if out_fmt != "jpeg" else "jpg", quality=92)
    _ = strip_metadata  # Pillow writes no EXIF unless explicitly passed, so metadata is always removed
    return dst


def favicon_pack(src: Path, dst_dir: Path, name: str = "My Site", color: str = "#0f766e") -> list[Path]:
    """favicon.ico + PNG icons + web manifest + HTML snippet."""
    im = _square(open_image(src)[0].convert("RGBA"))
    out_dir = dst_dir / "favicon"
    out_dir.mkdir(exist_ok=True)
    files = []
    ico = out_dir / "favicon.ico"
    im.save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    files.append(ico)
    for fname, size in (("favicon-16x16.png", 16), ("favicon-32x32.png", 32), ("apple-touch-icon.png", 180),
                        ("android-chrome-192x192.png", 192), ("android-chrome-512x512.png", 512)):
        p = out_dir / fname
        icon = im.resize((size, size), Image.LANCZOS)
        if fname == "apple-touch-icon.png":  # iOS shows transparency as black
            bg = Image.new("RGBA", icon.size, "white")
            bg.alpha_composite(icon)
            icon = bg
        icon.save(p, format="PNG", optimize=True)
        files.append(p)
    if ext_of(src.name) == "svg":
        (out_dir / "favicon.svg").write_bytes(src.read_bytes())
        files.append(out_dir / "favicon.svg")
    manifest = {"name": name, "short_name": name[:12], "icons": [
        {"src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"}],
        "theme_color": color, "background_color": "#ffffff", "display": "standalone"}
    (out_dir / "site.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    files.append(out_dir / "site.webmanifest")
    snippet = (
        '<link rel="icon" href="/favicon.ico" sizes="any">\n'
        + ('<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n' if ext_of(src.name) == "svg" else "")
        + '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">\n'
        '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">\n'
        '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">\n'
        f'<link rel="manifest" href="/site.webmanifest">\n<meta name="theme-color" content="{color}">\n'
    )
    (out_dir / "install.html").write_text(snippet, encoding="utf-8")
    files.append(out_dir / "install.html")
    return files


# --------------------------------------------------------------------------- audio & video

QUALITY_CRF = {"high": 20, "medium": 26, "low": 32}
AUDIO_BITRATE = {"high": "256k", "medium": "160k", "low": "96k"}
RESOLUTIONS = {"2160": 2160, "1440": 1440, "1080": 1080, "720": 720, "480": 480, "360": 360}


# Real media containers only. Playlists (HLS/DASH), concat lists, image sequences, device and network
# demuxers are refused: a ".mp4" that is really a playlist could otherwise make ffmpeg read server files
# or internal URLs.
SAFE_DEMUXERS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi", "flv", "mpeg", "mpegts",
                 "mpegvideo", "ogg", "wav", "w64", "mp3", "flac", "aac", "asf", "aiff", "amr", "gif", "ac3", "eac3",
                 "dts", "wv", "ape", "caf", "mxf", "dv", "m4v", "h264", "hevc", "nut", "opus", "mpc"}
FF_INPUT = ["-protocol_whitelist", "file"]


def probe(src: Path) -> dict:
    from .config import MAX_MEDIA_MINUTES

    try:
        out = run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-print_format", "json",
                   "-show_format", "-show_streams", str(src)], timeout=60).stdout
        info = json.loads(out or "{}")
    except Exception as exc:
        raise ToolError(f"'{src.name}' is not a readable audio or video file.") from exc
    demuxers = set((info.get("format", {}).get("format_name") or "").split(","))
    if not demuxers & SAFE_DEMUXERS:
        raise ToolError(f"'{src.name}' is not a supported audio or video file.")
    try:
        duration = float(info.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0
    if duration > MAX_MEDIA_MINUTES * 60:
        raise ToolError(f"'{src.name}' is longer than {MAX_MEDIA_MINUTES} minutes, the maximum per file.")
    return info


def _trim_args(opts: dict) -> list[str]:
    from .security import media_time

    args = []
    start, end = media_time(opts.get("start")), media_time(opts.get("end"))
    if start:
        args += ["-ss", start]
    if end:
        args += ["-to", end]
    return args


def convert_media(src: Path, dst_dir: Path, base: str, fmt: str, opts: dict) -> Path:
    info = probe(src)
    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 0 for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    cat = F.FORMATS.get(fmt, ("", ""))[1]
    if cat == "video" and not has_video and fmt != "gif":
        raise ToolError("This file has no video track. Choose an audio format instead.")
    if fmt == "gif" and not has_video:
        raise ToolError("This file has no video track to turn into a GIF.")
    if cat == "audio" and not has_audio:
        raise ToolError("This file has no audio track.")
    dst = dst_dir / f"{base}.{fmt}"
    q = opts.get("quality", "medium")
    trim = _trim_args(opts)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin"] + FF_INPUT + trim + ["-i", str(src)]
    if fmt == "gif":
        fps = max(1, min(int(opts.get("fps") or 12), 30))
        width = max(80, min(int(opts.get("gif_width") or 480), 1280))
        vf = f"fps={fps},scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
        cmd += ["-t", "60", "-filter_complex", vf, "-loop", "0", str(dst)]  # GIFs are capped at one minute
    elif cat == "audio":
        cmd += ["-vn"]
        codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE.get(q, "160k")],
                 "wav": ["-c:a", "pcm_s16le"],
                 "flac": ["-c:a", "flac"],
                 "ogg": ["-c:a", "libvorbis", "-q:a", {"high": "7", "medium": "5", "low": "3"}.get(q, "5")],
                 "opus": ["-c:a", "libopus", "-b:a", {"high": "160k", "medium": "96k", "low": "64k"}.get(q, "96k")],
                 "m4a": ["-c:a", "aac", "-b:a", AUDIO_BITRATE.get(q, "160k")]}[fmt]
        cmd += codec + [str(dst)]
    else:
        res = RESOLUTIONS.get(str(opts.get("resolution", "")))
        # H.264/VP9 need even dimensions; this also handles odd-sized GIFs and phone videos
        vf = [f"scale=-2:'trunc(min({res},ih)/2)*2'" if res else "scale='trunc(iw/2)*2':'trunc(ih/2)*2'"]
        crf = QUALITY_CRF.get(q, 26)
        if fmt == "webm":
            v = ["-c:v", "libvpx-vp9", "-crf", str(crf + 6), "-b:v", "0", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1"]
            a = ["-c:a", "libopus", "-b:a", "128k"]
        elif fmt == "avi":
            v = ["-c:v", "mpeg4", "-q:v", {"high": "3", "medium": "5", "low": "8"}.get(q, "5")]
            a = ["-c:a", "libmp3lame", "-b:a", "192k"]
        else:  # mp4, mov, mkv
            v = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p"]
            a = ["-c:a", "aac", "-b:a", "160k"]
        if vf:
            v = ["-vf", ",".join(vf)] + v
        if opts.get("mute") or not has_audio:
            a = ["-an"]
        extra = ["-movflags", "+faststart"] if fmt in ("mp4", "mov") else []
        cmd += v + a + extra + [str(dst)]
    try:
        run(cmd)
    except RuntimeError as exc:
        raise ToolError("This media file could not be converted. It may be damaged or use an unusual codec.") from exc
    if not dst.exists() or dst.stat().st_size == 0:
        raise ToolError("Conversion produced an empty file. Check the start/end times.")
    return dst


def compress_video(src: Path, dst_dir: Path, base: str, level: str = "medium", resolution: str = "") -> tuple[Path, str]:
    crf = {"light": 23, "medium": 28, "strong": 33}.get(level, 28)
    dst = dst_dir / f"{base}_compressed.mp4"
    res = RESOLUTIONS.get(str(resolution))
    vf = ["-vf", f"scale=-2:'trunc(min({res},ih)/2)*2'" if res else "scale='trunc(iw/2)*2':'trunc(ih/2)*2'"]
    has_audio = any(s.get("codec_type") == "audio" for s in probe(src).get("streams", []))
    cmd = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin"] + FF_INPUT + ["-i", str(src)] + vf +
           ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p"] +
           (["-c:a", "aac", "-b:a", "128k"] if has_audio else ["-an"]) + ["-movflags", "+faststart", str(dst)])
    try:
        run(cmd)
    except RuntimeError as exc:
        raise ToolError("This video could not be compressed. It may be damaged or use an unusual codec.") from exc
    original, new = src.stat().st_size, dst.stat().st_size
    if new >= original:
        return dst, f"{human_size(original)} → {human_size(new)}. This video was already efficiently encoded."
    return dst, f"{human_size(original)} → {human_size(new)} ({100 - new * 100 / original:.0f}% smaller)."
