# VRM Optimization 

> NOTE: These scrips were created with Claude, please validate the structure of the optimized VRM separately before using in production!

## Pre-requisites 

**Python3**
https://www.python.org/downloads/

**Pillow**
```bash
pip install Pillow
```

## Scripts Included

### 1. optimize_vrm.py
Resizes embedded VRM textures and encodes them as KTX2/Basis Universal while
preserving VRM-specific extensions and metadata.

**Usage:**
```bash
python3 optimize_vrm.py input.vrm output.vrm [max_size] [quality] [options]
```

**Examples:**
```bash
# Default: 1024px textures, ETC1S quality 128, with mipmaps
python3 optimize_vrm.py my_avatar.vrm my_avatar_optimized.vrm

# Smaller files: 512px textures, ETC1S quality 96
python3 optimize_vrm.py my_avatar.vrm my_avatar_tiny.vrm 512 96

# Higher-quality UASTC output
python3 optimize_vrm.py my_avatar.vrm my_avatar_hq.vrm 2048 --mode uastc

# Disable KTX2 and use the original PNG/JPEG pipeline
python3 optimize_vrm.py my_avatar.vrm my_avatar_legacy.vrm --no-texture-compression

# Legacy pipeline with JPEG quality 90
python3 optimize_vrm.py my_avatar.vrm my_avatar_legacy.vrm 1024 90 --no-texture-compression
```

**Parameters:**
- `max_size`: Maximum texture dimension in pixels (default: 1024)
- `quality`: ETC1S quality 1-255 (default: 128), or JPEG quality 1-100 when
  `--no-texture-compression` is used (default: 85)
- `--mode`: `etc1s` for smaller files or `uastc` for higher quality
- `--uastc-level`: UASTC quality level 0-4 (default: 2)
- `--zstd`: UASTC Zstandard compression level 0-22 (default: 18)
- `--no-mipmaps`: Disable mipmap generation
- `--no-texture-compression` / `--no-ktx2`: Disable KTX2 encoding; retain
  transparent textures as PNG and convert opaque textures to JPEG
- `--jpeg-quality`: Set legacy JPEG quality explicitly (default: 85)
- `--ktx PATH`: Use a specific `ktx` or legacy `toktx` executable

**Notes:**
- Supports RGB and alpha textures
- Marks colour textures as sRGB and data/normal textures as linear
- The default mode adds the standard `KHR_texture_basisu` glTF extension
- Default KTX2-only output requires client support for `KHR_texture_basisu`
- The legacy PNG/JPEG mode does not require KTX-Software or `KTX2Loader`
- Maintains VRM structure and metadata
- Safe to run multiple times

### 2. validate_vrm.py
Validates VRM file structure and three-vrm compatibility.

**Usage:**
```bash
python3 validate_vrm.py file.vrm
```

**What it checks:**
- ✓ Valid GLB/glTF 2.0 format
- ✓ VRM extension present
- ✓ Buffer sizes match
- ✓ All buffer views within bounds
- ✓ PNG, JPEG, and KTX2/Basis texture metadata
- ✓ File size warnings
- ✓ Structure integrity

**Returns:**
- Exit code 0 if valid
- Exit code 1 if validation fails

## three-vrm Compatibility Notes

**Supported texture formats:**
- ✅ image/png
- ✅ image/jpeg
- ✅ image/ktx2, when `GLTFLoader` is configured with `KTX2Loader`
- ❌ image/webp (not handled by this optimizer)

That's why this script uses PNG/JPEG only - three-vrm doesn't support newer formats like KTX2 or Basis Universal yet.

Install the official Khronos KTX-Software tools as well and ensure `ktx` (or the
legacy `toktx`) is on `PATH`. Alternatively, pass its location with
`--ktx /path/to/ktx`.

KTX-Software is optional when `--no-texture-compression` is used.

## Troubleshooting

**"Module 'PIL' not found"**
```bash
pip install Pillow --break-system-packages  # On some systems
```

**VRM won't load after optimization**
```bash
# Run the validator to check what's wrong
python3 validate_vrm.py your_file.vrm

# If it reports errors, try more conservative settings
python3 optimize_vrm.py input.vrm output.vrm 2048 192

# Or use standard PNG/JPEG textures for clients without KTX2Loader
python3 optimize_vrm.py input.vrm output.vrm --no-texture-compression
```

**Textures look too compressed**
```bash
# Increase ETC1S quality
python3 optimize_vrm.py input.vrm output.vrm 1024 192

# Or use higher-quality UASTC
python3 optimize_vrm.py input.vrm output.vrm 1024 --mode uastc
```

**File is still too large**
```bash
# Use more aggressive ETC1S compression
python3 optimize_vrm.py input.vrm output.vrm 512 64
```

## Recommended Settings by Use Case

**Web/Mobile (best performance):**
```bash
python3 optimize_vrm.py input.vrm output.vrm 512 96
# Results in ~1-2MB files
```

**Desktop/VRChat (balanced):**
```bash
python3 optimize_vrm.py input.vrm output.vrm 1024 128
```

**High quality/archival:**
```bash
python3 optimize_vrm.py input.vrm output.vrm 2048 95
# Results in ~8-12MB files
```

Most VRMs use 1024x1024 or even 512x512 textures. Large textures are overkill for real-time rendering and causes:
- Slow loading times
- High memory usage
- GPU texture upload stutters
- Poor performance in React Three Fiber
- Janky frame rates

## License

Public domain / MIT - use however you want!
