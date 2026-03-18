#!/usr/bin/env python3
"""
VRM Validator - Updated to understand GLB padding correctly
"""
import json
import struct
import sys

def validate_vrm(filepath):
    """Validate a VRM file"""
    print(f"Validating: {filepath}")
    print("=" * 60)
    
    try:
        with open(filepath, 'rb') as f:
            # Check GLB header
            magic = f.read(4)
            if magic != b'glTF':
                print("❌ FAIL: Invalid magic bytes (not a GLB file)")
                return False
            print("✓ Valid GLB magic bytes")
            
            version = struct.unpack('<I', f.read(4))[0]
            if version != 2:
                print(f"❌ FAIL: Unsupported glTF version: {version}")
                return False
            print(f"✓ glTF version 2")
            
            total_length = struct.unpack('<I', f.read(4))[0]
            
            # Read JSON chunk
            json_length = struct.unpack('<I', f.read(4))[0]
            json_type = f.read(4)
            if json_type != b'JSON':
                print(f"❌ FAIL: Invalid JSON chunk type")
                return False
            
            if json_length % 4 != 0:
                print(f"⚠️  WARNING: JSON chunk length not 4-byte aligned")
            print("✓ Valid JSON chunk")
            
            json_data = json.loads(f.read(json_length).decode('utf-8').rstrip(' \x00'))
            
            # Read binary chunk
            bin_length = struct.unpack('<I', f.read(4))[0]
            bin_type = f.read(4)
            if bin_type != b'BIN\0':
                print(f"❌ FAIL: Invalid binary chunk type: {bin_type}")
                return False
            
            if bin_length % 4 != 0:
                print(f"❌ FAIL: Binary chunk length must be 4-byte aligned")
                print(f"  Got: {bin_length} (remainder {bin_length % 4})")
                return False
            print("✓ Valid binary chunk (4-byte aligned)")
            
            bin_data = f.read(bin_length)
            
            # Validate VRM extension
            if 'extensions' not in json_data:
                print("⚠️  WARNING: No extensions found")
            elif 'VRM' not in json_data['extensions']:
                print("⚠️  WARNING: VRM extension not found")
            else:
                print("✓ VRM extension present")
                vrm_version = json_data['extensions']['VRM'].get('specVersion', 'unknown')
                print(f"  VRM spec version: {vrm_version}")
            
            # Validate required glTF fields
            required_fields = ['asset', 'scenes', 'nodes']
            for field in required_fields:
                if field not in json_data:
                    print(f"❌ FAIL: Missing required field: {field}")
                    return False
            print(f"✓ All required glTF fields present")
            
            # Check asset version
            if 'version' in json_data['asset']:
                print(f"  glTF asset version: {json_data['asset']['version']}")
            
            # Validate buffer - the JSON declares unpadded size
            if 'buffers' in json_data:
                declared_buffer_size = json_data['buffers'][0]['byteLength']
                actual_data_size = len(bin_data.rstrip(b'\x00'))  # Strip padding
                
                # The binary chunk may have padding, so we check if declared size fits
                if declared_buffer_size > bin_length:
                    print(f"❌ FAIL: Buffer size exceeds chunk size")
                    print(f"  Declared: {declared_buffer_size}, Chunk: {bin_length}")
                    return False
                    
                print(f"✓ Buffer declaration valid")
                print(f"  Declared in JSON: {declared_buffer_size:,} bytes")
                print(f"  Binary chunk size: {bin_length:,} bytes")
                if bin_length > declared_buffer_size:
                    print(f"  Padding: {bin_length - declared_buffer_size} bytes")
            
            # Validate buffer views
            if 'bufferViews' in json_data:
                print(f"✓ {len(json_data['bufferViews'])} buffer views")
                for idx, bv in enumerate(json_data['bufferViews']):
                    offset = bv['byteOffset']
                    length = bv['byteLength']
                    # Check against declared buffer size, not chunk size
                    if offset + length > json_data['buffers'][0]['byteLength']:
                        print(f"❌ FAIL: BufferView {idx} exceeds buffer bounds")
                        return False
                print("✓ All buffer views within bounds")
            
            # Validate images/textures
            if 'images' in json_data:
                print(f"✓ {len(json_data['images'])} images/textures")
                for idx, img in enumerate(json_data['images']):
                    mime = img.get('mimeType', 'unknown')
                    if mime not in ['image/png', 'image/jpeg', 'image/jpg']:
                        print(f"⚠️  WARNING: Texture {idx} has unusual MIME type: {mime}")
                    if 'bufferView' in img:
                        bv_idx = img['bufferView']
                        if bv_idx >= len(json_data['bufferViews']):
                            print(f"❌ FAIL: Image {idx} references invalid bufferView {bv_idx}")
                            return False
                print("✓ All textures reference valid buffer views")
            
            # Validate materials
            if 'materials' in json_data:
                print(f"✓ {len(json_data['materials'])} materials")
            
            # Validate meshes
            if 'meshes' in json_data:
                total_prims = sum(len(m.get('primitives', [])) for m in json_data['meshes'])
                print(f"✓ {len(json_data['meshes'])} meshes, {total_prims} primitives")
            
            # Check for three-vrm compatibility
            print("\nthree-vrm compatibility checks:")
            
            if 'images' in json_data:
                unsupported = []
                for idx, img in enumerate(json_data['images']):
                    mime = img.get('mimeType', '')
                    if mime not in ['image/png', 'image/jpeg', 'image/jpg']:
                        unsupported.append((idx, mime))
                
                if unsupported:
                    print(f"⚠️  Unsupported texture formats found:")
                    for idx, mime in unsupported:
                        print(f"   Texture {idx}: {mime}")
                    print("   three-vrm supports: image/png, image/jpeg")
                else:
                    print("✓ All textures use supported formats (PNG/JPEG)")
            
            # File size check
            import os
            file_size = os.path.getsize(filepath)
            print(f"\nFile size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
            if file_size > 10 * 1024 * 1024:
                print("⚠️  File is quite large (>10MB) - may cause performance issues")
            elif file_size > 5 * 1024 * 1024:
                print("⚠️  File is moderately large (>5MB) - consider optimization")
            else:
                print("✓ File size is reasonable for web use")
            
            print("\n" + "=" * 60)
            print("✅ VALIDATION PASSED - VRM should load in three-vrm")
            return True
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python validate_vrm.py <file.vrm>")
        sys.exit(1)
    
    success = validate_vrm(sys.argv[1])
    sys.exit(0 if success else 1)
