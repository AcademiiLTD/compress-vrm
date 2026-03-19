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

Most VRMs use 1024x1024 or even 512x512 textures. Large textures are overkill for real-time rendering and causes:
- Slow loading times
- High memory usage
- GPU texture upload stutters
- Poor performance in React Three Fiber
- Janky frame rates

## License

Public domain / MIT - use however you want!
