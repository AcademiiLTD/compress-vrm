# VRM Optimization Tools

## Your VRM was 60% too large!

**Original file:** 14.17 MB  
**Optimized file:** 5.62 MB  
**Reduction:** 60.7% smaller

The problem was **massive 4096x4096 PNG textures** eating up ~9MB. This causes stuttering in React Three Fiber and three-vrm because the browser has to decode huge PNGs before uploading to the GPU.

**NOTE:** The included optimized.vrm file has been fixed to work with the pixiv three-vrm viewer. The issue was that the GLB binary chunk length MUST be 4-byte aligned (divisible by 4). The chunk length now includes padding bytes to ensure proper alignment, which is required by the glTF 2.0 specification.

## What was done:
- ✅ Resized textures from 4096x4096 → 1024x1024
- ✅ Converted PNGs to JPEG (85% quality) where no alpha channel needed
- ✅ Kept PNG for textures with transparency
- ✅ Validated VRM structure stays intact
- ✅ Confirmed three-vrm compatibility

## Scripts Included

### 1. optimize_vrm.py
Compresses VRM textures while maintaining compatibility with pixiv/three-vrm.

**Usage:**
```bash
python3 optimize_vrm.py input.vrm output.vrm [max_size] [jpeg_quality]
```

**Examples:**
```bash
# Default: 1024px textures, 85% JPEG quality
python3 optimize_vrm.py my_avatar.vrm my_avatar_optimized.vrm

# Smaller files: 512px textures, 80% quality
python3 optimize_vrm.py my_avatar.vrm my_avatar_tiny.vrm 512 80

# Higher quality: 2048px textures, 90% quality
python3 optimize_vrm.py my_avatar.vrm my_avatar_hq.vrm 2048 90
```

**Parameters:**
- `max_size`: Maximum texture dimension in pixels (default: 1024)
- `jpeg_quality`: JPEG compression quality 1-100 (default: 85)

**Notes:**
- Automatically keeps PNG for textures with alpha channels
- Converts RGB textures to JPEG for better compression
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
- ✓ Texture formats (PNG/JPEG only for three-vrm)
- ✓ File size warnings
- ✓ Structure integrity

**Returns:**
- Exit code 0 if valid
- Exit code 1 if validation fails

## three-vrm Compatibility Notes

**Supported texture formats:**
- ✅ image/png
- ✅ image/jpeg
- ❌ image/webp (not supported)
- ❌ image/ktx2 (not supported)

That's why this script uses PNG/JPEG only - three-vrm doesn't support newer formats like KTX2 or Basis Universal yet.

## Requirements

```bash
pip install Pillow
```

That's it! Only needs PIL/Pillow for image processing. Uses Python's built-in libraries for everything else.

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
python3 optimize_vrm.py input.vrm output.vrm 2048 95
```

**Textures look too compressed**
```bash
# Use higher quality settings
python3 optimize_vrm.py input.vrm output.vrm 1024 95

# Or keep higher resolution
python3 optimize_vrm.py input.vrm output.vrm 2048 90
```

**File is still too large**
```bash
# Use more aggressive compression
python3 optimize_vrm.py input.vrm output.vrm 512 75
```

## Recommended Settings by Use Case

**Web/Mobile (best performance):**
```bash
python3 optimize_vrm.py input.vrm output.vrm 512 80
# Results in ~1-2MB files
```

**Desktop/VRChat (balanced):**
```bash
python3 optimize_vrm.py input.vrm output.vrm 1024 85
# Results in ~3-6MB files (your optimized.vrm is this)
```

**High quality/archival:**
```bash
python3 optimize_vrm.py input.vrm output.vrm 2048 95
# Results in ~8-12MB files
```

## Why Your Original VRM Was So Big

Your VRM had:
- Texture 0: 4096x4096 PNG → 1.1 MB
- Texture 1: 4096x4096 PNG → 3.8 MB (main body)
- Texture 2: 4096x4096 PNG → 3.2 MB (clothing)
- Texture 3: 1024x1024 PNG → 0.9 MB
- Texture 4: 300x54 PNG → 0.005 MB

**Total texture size: 9.1 MB out of 14.2 MB**

Most VRMs use 1024x1024 or even 512x512 textures. 4096x4096 is overkill for real-time rendering and causes:
- Slow loading times
- High memory usage
- GPU texture upload stutters
- Poor performance in React Three Fiber
- Janky frame rates

## License

Public domain / MIT - use however you want!
