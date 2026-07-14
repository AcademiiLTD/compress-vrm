#!/usr/bin/env python3
"""Resize VRM textures and encode them as KTX2 or legacy PNG/JPEG images.

The script deliberately edits the GLB container directly. Generic glTF rewriting
tools may discard VRM extensions they do not understand.
"""

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps


GLB_MAGIC = b"glTF"
JSON_CHUNK = b"JSON"
BIN_CHUNK = b"BIN\0"
KTX2_IDENTIFIER = b"\xabKTX 20\xbb\r\n\x1a\n"
KHR_TEXTURE_BASISU = "KHR_texture_basisu"


def read_glb(filepath):
    """Read a binary glTF/VRM and return its JSON and BIN chunks."""
    with open(filepath, "rb") as file:
        header = file.read(12)
        if len(header) != 12:
            raise ValueError("File is too short to be a GLB")

        magic, version, total_length = struct.unpack("<4sII", header)
        if magic != GLB_MAGIC:
            raise ValueError("Not a valid binary glTF file")
        if version != 2:
            raise ValueError(f"Unsupported glTF version: {version}")
        if total_length != os.path.getsize(filepath):
            raise ValueError(
                f"GLB header length is {total_length}, but file size is "
                f"{os.path.getsize(filepath)}"
            )

        json_data = None
        bin_data = None
        while file.tell() < total_length:
            chunk_header = file.read(8)
            if len(chunk_header) != 8:
                raise ValueError("Truncated GLB chunk header")
            chunk_length, chunk_type = struct.unpack("<I4s", chunk_header)
            chunk_data = file.read(chunk_length)
            if len(chunk_data) != chunk_length:
                raise ValueError("Truncated GLB chunk")

            if chunk_type == JSON_CHUNK:
                json_data = json.loads(chunk_data.decode("utf-8").rstrip(" \x00"))
            elif chunk_type == BIN_CHUNK:
                bin_data = chunk_data

        if json_data is None:
            raise ValueError("GLB has no JSON chunk")
        if bin_data is None:
            raise ValueError("GLB has no BIN chunk")
        return json_data, bin_data


def write_glb(filepath, json_data, bin_data):
    """Write JSON and binary data as a glTF 2.0 binary container."""
    json_bytes = json.dumps(json_data, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)

    bin_bytes = bytes(bin_data)
    bin_bytes += b"\0" * ((-len(bin_bytes)) % 4)

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with open(filepath, "wb") as file:
        file.write(struct.pack("<4sII", GLB_MAGIC, 2, total_length))
        file.write(struct.pack("<I4s", len(json_bytes), JSON_CHUNK))
        file.write(json_bytes)
        file.write(struct.pack("<I4s", len(bin_bytes), BIN_CHUNK))
        file.write(bin_bytes)


def _append_unique(values, value):
    if value not in values:
        values.append(value)


def _texture_image_sources(json_data):
    """Return texture-index -> image-index for core and existing KTX2 textures."""
    sources = {}
    for texture_index, texture in enumerate(json_data.get("textures", [])):
        basisu = texture.get("extensions", {}).get(KHR_TEXTURE_BASISU)
        if basisu is not None:
            sources[texture_index] = basisu["source"]
        elif "source" in texture:
            sources[texture_index] = texture["source"]
    return sources


def _collect_texture_slots(json_data):
    """Classify standard and VRM texture slots as sRGB or linear data."""
    srgb = set()
    linear = set()

    def add_texture(texture_info, destination):
        if isinstance(texture_info, dict) and "index" in texture_info:
            destination.add(texture_info["index"])

    for material in json_data.get("materials", []):
        pbr = material.get("pbrMetallicRoughness", {})
        add_texture(pbr.get("baseColorTexture"), srgb)
        add_texture(pbr.get("metallicRoughnessTexture"), linear)
        add_texture(material.get("normalTexture"), linear)
        add_texture(material.get("occlusionTexture"), linear)
        add_texture(material.get("emissiveTexture"), srgb)

        mtoon = material.get("extensions", {}).get("VRMC_materials_mtoon", {})
        for key in (
            "shadeMultiplyTexture",
            "matcapTexture",
            "rimMultiplyTexture",
        ):
            add_texture(mtoon.get(key), srgb)
        for key in (
            "shadingShiftTexture",
            "outlineWidthMultiplyTexture",
            "uvAnimationMaskTexture",
        ):
            add_texture(mtoon.get(key), linear)

    # VRM 0.x duplicates material texture assignments in materialProperties.
    vrm = json_data.get("extensions", {}).get("VRM", {})
    linear_vrm0_properties = {
        "_BumpMap",
        "_MetallicGlossMap",
        "_OcclusionMap",
        "_OutlineWidthTexture",
        "_UvAnimMaskTexture",
    }
    for material_property in vrm.get("materialProperties", []):
        for name, texture_index in material_property.get("textureProperties", {}).items():
            (linear if name in linear_vrm0_properties else srgb).add(texture_index)

    return srgb, linear


def _image_transfer_functions(json_data, texture_sources):
    srgb_textures, linear_textures = _collect_texture_slots(json_data)
    srgb_images = {texture_sources[index] for index in srgb_textures if index in texture_sources}
    linear_images = {
        texture_sources[index] for index in linear_textures if index in texture_sources
    }

    shared = srgb_images & linear_images
    if shared:
        indices = ", ".join(str(index) for index in sorted(shared))
        print(
            f"WARNING: Image(s) {indices} are used by both colour and data texture "
            "slots; encoding them as sRGB"
        )

    return {
        image_index: (
            "srgb"
            if image_index in srgb_images or image_index not in linear_images
            else "linear"
        )
        for image_index in set(texture_sources.values())
    }


def _aligned_size(size, max_size):
    """Fit within max_size and make both dimensions valid Basis block sizes."""
    width, height = size
    max_size = max(4, max_size - (max_size % 4))
    scale = min(1.0, max_size / max(width, height))
    width = max(4, min(max_size, int(round(width * scale / 4.0)) * 4))
    height = max(4, min(max_size, int(round(height * scale / 4.0)) * 4))
    return width, height


def _legacy_size(size, max_size):
    """Fit within max_size while retaining the old PNG/JPEG resize behaviour."""
    width, height = size
    if max(width, height) <= max_size:
        return size
    scale = max_size / max(width, height)
    return max(1, int(width * scale)), max(1, int(height * scale))


def encode_png_jpeg(image, jpeg_quality=85):
    """Encode transparent images as PNG and opaque images as JPEG."""
    has_alpha = image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
    output = BytesIO()
    if has_alpha:
        if image.mode not in {"RGBA", "LA"}:
            image = image.convert("RGBA")
        image.save(output, format="PNG", optimize=True)
        return output.getvalue(), "image/png"

    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(output, format="JPEG", quality=jpeg_quality, optimize=True)
    return output.getvalue(), "image/jpeg"


def _find_ktx_tool(ktx_path=None):
    """Find modern `ktx` or legacy `toktx`, returning (kind, path)."""
    candidates = [ktx_path] if ktx_path else ["ktx", "toktx"]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
        if resolved and os.path.isfile(resolved) and os.access(resolved, os.X_OK):
            kind = "toktx" if os.path.basename(resolved).lower().startswith("toktx") else "ktx"
            return kind, resolved
    raise RuntimeError(
        "KTX2 encoding requires Khronos KTX-Software's 'ktx' or 'toktx' "
        "executable. Install KTX-Software and put it on PATH, or pass --ktx PATH."
    )


def encode_ktx2(
    image,
    image_index,
    transfer_function,
    ktx_tool,
    mode="etc1s",
    quality=128,
    uastc_level=2,
    zstd=18,
    mipmaps=True,
):
    """Encode a Pillow image with a Khronos KTX tool and return KTX2 bytes."""
    with tempfile.TemporaryDirectory(prefix="vrm-ktx2-") as directory:
        source_path = Path(directory) / f"image-{image_index}.png"
        output_path = Path(directory) / f"image-{image_index}.ktx2"
        image.save(source_path, format="PNG", optimize=True)

        tool_kind, tool_path = ktx_tool
        if tool_kind == "ktx":
            channels = "R8G8B8A8" if image.mode == "RGBA" else "R8G8B8"
            command = [
                tool_path,
                "create",
                "--format",
                f"{channels}_{'SRGB' if transfer_function == 'srgb' else 'UNORM'}",
                "--encode",
                "basis-lz" if mode == "etc1s" else "uastc-ldr-4x4",
                "--assign-tf",
                transfer_function,
                "--assign-primaries",
                "bt709" if transfer_function == "srgb" else "none",
                "--assign-texcoord-origin",
                "top-left",
            ]
            if mipmaps:
                command.append("--generate-mipmap")
            if mode == "etc1s":
                command.extend(("--qlevel", str(quality)))
            else:
                command.extend(("--uastc-quality", str(uastc_level)))
                if zstd:
                    command.extend(("--zstd", str(zstd)))
            command.extend((str(source_path), str(output_path)))
        else:
            command = [
                tool_path,
                "--t2",
                "--encode",
                "basis-lz" if mode == "etc1s" else "uastc",
                "--assign_oetf",
                transfer_function,
                "--assign_primaries",
                "bt709" if transfer_function == "srgb" else "none",
            ]
            if mipmaps:
                command.append("--genmipmap")
            if mode == "etc1s":
                command.extend(("--qlevel", str(quality)))
            else:
                command.extend(("--uastc_quality", str(uastc_level)))
                if zstd:
                    command.extend(("--zcmp", str(zstd)))
            command.extend((str(output_path), str(source_path)))

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"{tool_kind} failed for image {image_index}: {detail}")

        ktx2_data = output_path.read_bytes()
        if not ktx2_data.startswith(KTX2_IDENTIFIER):
            raise RuntimeError(
                f"{tool_kind} produced an invalid KTX2 file for image {image_index}"
            )
        return ktx2_data


def _buffer_view_payloads(json_data, bin_data):
    payloads = []
    for index, buffer_view in enumerate(json_data.get("bufferViews", [])):
        if buffer_view.get("buffer", 0) != 0:
            raise ValueError(f"BufferView {index} does not reference the GLB buffer")
        offset = buffer_view.get("byteOffset", 0)
        length = buffer_view["byteLength"]
        if offset + length > len(bin_data):
            raise ValueError(f"BufferView {index} exceeds the BIN chunk")
        payloads.append(bin_data[offset : offset + length])
    return payloads


def _rebuild_buffer(json_data, payloads):
    """Repack buffer views with conservative four-byte alignment."""
    new_bin_data = bytearray()
    for buffer_view, payload in zip(json_data.get("bufferViews", []), payloads):
        new_bin_data.extend(b"\0" * ((-len(new_bin_data)) % 4))
        buffer_view["byteOffset"] = len(new_bin_data)
        buffer_view["byteLength"] = len(payload)
        new_bin_data.extend(payload)

    json_data["buffers"][0]["byteLength"] = len(new_bin_data)
    return bytes(new_bin_data)


def optimize_vrm(
    input_path,
    output_path,
    max_size=1024,
    quality=128,
    mode="etc1s",
    uastc_level=2,
    zstd=18,
    mipmaps=True,
    ktx_path=None,
    texture_compression=True,
    jpeg_quality=85,
):
    """Resize embedded textures, encode them, and preserve VRM data."""
    minimum_size = 4 if texture_compression else 1
    if max_size < minimum_size:
        raise ValueError(f"max_size must be at least {minimum_size}")
    if texture_compression and not 1 <= quality <= 255:
        raise ValueError("ETC1S quality must be between 1 and 255")
    if not texture_compression and not 1 <= jpeg_quality <= 100:
        raise ValueError("JPEG quality must be between 1 and 100")
    if mode not in {"etc1s", "uastc"}:
        raise ValueError("mode must be 'etc1s' or 'uastc'")

    print(f"Reading VRM from: {input_path}")
    json_data, bin_data = read_glb(input_path)
    if len(json_data.get("buffers", [])) != 1:
        raise ValueError("A binary VRM must contain exactly one buffer")

    images = json_data.get("images", [])
    textures = json_data.get("textures", [])
    if not images or not textures:
        print("No texture images found; writing an unchanged copy")
        write_glb(output_path, json_data, bin_data)
        return

    texture_sources = _texture_image_sources(json_data)
    if not texture_sources:
        print("No referenced texture images found; writing an unchanged copy")
        write_glb(output_path, json_data, bin_data)
        return

    transfer_functions = (
        _image_transfer_functions(json_data, texture_sources)
        if texture_compression
        else {}
    )
    texture_image_indices = sorted(set(texture_sources.values()))
    needs_encoder = texture_compression and any(
        image_index >= len(images) or images[image_index].get("mimeType") != "image/ktx2"
        for image_index in texture_image_indices
    )
    ktx_tool = _find_ktx_tool(ktx_path) if needs_encoder else None
    payloads = _buffer_view_payloads(json_data, bin_data)
    encoded_images = set()

    print(f"Found {len(texture_image_indices)} texture image(s)")
    for image_index in texture_image_indices:
        if image_index >= len(images):
            raise ValueError(f"Texture references missing image {image_index}")
        image_definition = images[image_index]
        mime_type = image_definition.get("mimeType")

        if mime_type == "image/ktx2":
            print(f"Texture image {image_index}: already KTX2, keeping it")
            if texture_compression:
                encoded_images.add(image_index)
            continue
        if "bufferView" not in image_definition:
            raise ValueError(
                f"Image {image_index} is external; VRM texture images must be embedded"
            )
        if mime_type not in {"image/png", "image/jpeg", "image/jpg"}:
            raise ValueError(f"Image {image_index} has unsupported MIME type {mime_type!r}")

        buffer_view_index = image_definition["bufferView"]
        if buffer_view_index >= len(payloads):
            raise ValueError(f"Image {image_index} references missing BufferView")
        original_data = payloads[buffer_view_index]

        with Image.open(BytesIO(original_data)) as source_image:
            image = ImageOps.exif_transpose(source_image)
            image.load()
            original_dimensions = image.size
            dimensions = (
                _aligned_size(image.size, max_size)
                if texture_compression
                else _legacy_size(image.size, max_size)
            )
            if dimensions != image.size:
                image = image.resize(dimensions, Image.Resampling.LANCZOS)

            if texture_compression:
                if image.mode not in {"RGB", "RGBA"}:
                    has_alpha = image.mode in {"LA", "PA"} or "transparency" in image.info
                    image = image.convert("RGBA" if has_alpha else "RGB")

                transfer_function = transfer_functions.get(image_index, "srgb")
                print(
                    f"Texture image {image_index}: {original_dimensions[0]}x"
                    f"{original_dimensions[1]} {mime_type} -> {dimensions[0]}x"
                    f"{dimensions[1]} KTX2/{mode.upper()} ({transfer_function})"
                )
                encoded_data = encode_ktx2(
                    image,
                    image_index,
                    transfer_function,
                    ktx_tool,
                    mode=mode,
                    quality=quality,
                    uastc_level=uastc_level,
                    zstd=zstd,
                    mipmaps=mipmaps,
                )
                new_mime_type = "image/ktx2"
            else:
                encoded_data, new_mime_type = encode_png_jpeg(
                    image, jpeg_quality=jpeg_quality
                )
                format_name = "PNG" if new_mime_type == "image/png" else "JPEG"
                detail = "alpha preserved" if format_name == "PNG" else f"quality {jpeg_quality}"
                print(
                    f"Texture image {image_index}: {original_dimensions[0]}x"
                    f"{original_dimensions[1]} {mime_type} -> {dimensions[0]}x"
                    f"{dimensions[1]} {format_name} ({detail})"
                )

        payloads[buffer_view_index] = encoded_data
        image_definition["mimeType"] = new_mime_type
        if texture_compression:
            encoded_images.add(image_index)
        print(
            f"  {len(original_data):,} -> {len(encoded_data):,} bytes "
            f"({(1 - len(encoded_data) / len(original_data)) * 100:.1f}% reduction)"
        )

    for texture_index, image_index in texture_sources.items():
        if image_index not in encoded_images:
            continue
        texture = textures[texture_index]
        if KHR_TEXTURE_BASISU in texture.get("extensions", {}):
            continue
        texture.setdefault("extensions", {})[KHR_TEXTURE_BASISU] = {"source": image_index}
        texture.pop("source", None)

    basisu_textures = [
        texture
        for texture in textures
        if KHR_TEXTURE_BASISU in texture.get("extensions", {})
    ]
    if basisu_textures:
        _append_unique(json_data.setdefault("extensionsUsed", []), KHR_TEXTURE_BASISU)
    if any("source" not in texture for texture in basisu_textures):
        _append_unique(json_data.setdefault("extensionsRequired", []), KHR_TEXTURE_BASISU)

    new_bin_data = _rebuild_buffer(json_data, payloads)
    print(
        f"Binary data: {len(bin_data):,} -> {len(new_bin_data):,} bytes "
        f"({(1 - len(new_bin_data) / len(bin_data)) * 100:.1f}% reduction)"
    )
    print(f"Writing optimized VRM to: {output_path}")
    write_glb(output_path, json_data, new_bin_data)
    output_size = os.path.getsize(output_path)
    print(f"Output file size: {output_size:,} bytes ({output_size / 1024 / 1024:.2f} MB)")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Resize embedded VRM textures and encode them as KTX2 or PNG/JPEG"
    )
    parser.add_argument("input", help="Input .vrm file")
    parser.add_argument("output", help="Output .vrm file")
    parser.add_argument(
        "max_size",
        nargs="?",
        type=int,
        default=1024,
        help="maximum texture dimension (default: 1024)",
    )
    parser.add_argument(
        "quality",
        nargs="?",
        type=int,
        default=None,
        help=(
            "ETC1S quality from 1-255 (default: 128), or JPEG quality from "
            "1-100 with --no-texture-compression (default: 85)"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("etc1s", "uastc"),
        default="etc1s",
        help="Basis compression mode (default: etc1s)",
    )
    parser.add_argument(
        "--uastc-level",
        type=int,
        choices=range(0, 5),
        default=2,
        metavar="0-4",
        help="UASTC quality level (default: 2)",
    )
    parser.add_argument(
        "--zstd",
        type=int,
        choices=range(0, 23),
        default=18,
        metavar="0-22",
        help="UASTC Zstandard level (default: 18)",
    )
    parser.add_argument("--no-mipmaps", action="store_true", help="do not generate mipmaps")
    parser.add_argument(
        "--no-texture-compression",
        "--no-ktx2",
        action="store_true",
        help="disable KTX2 encoding and use the legacy PNG/JPEG pipeline",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        choices=range(1, 101),
        default=None,
        metavar="1-100",
        help="JPEG quality for --no-texture-compression (default: 85)",
    )
    parser.add_argument(
        "--ktx",
        "--toktx",
        dest="ktx_path",
        help="path to ktx or legacy toktx (default: find either on PATH)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    texture_compression = not args.no_texture_compression
    quality = args.quality if args.quality is not None else 128
    jpeg_quality = (
        args.jpeg_quality
        if args.jpeg_quality is not None
        else (args.quality if not texture_compression and args.quality is not None else 85)
    )
    try:
        optimize_vrm(
            args.input,
            args.output,
            max_size=args.max_size,
            quality=quality,
            mode=args.mode,
            uastc_level=args.uastc_level,
            zstd=args.zstd,
            mipmaps=not args.no_mipmaps,
            ktx_path=args.ktx_path,
            texture_compression=texture_compression,
            jpeg_quality=jpeg_quality,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
