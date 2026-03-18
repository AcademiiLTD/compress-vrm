#!/usr/bin/env python3
"""
VRM Texture Optimizer - FINAL CORRECT VERSION
According to GLB spec, both JSON and BIN chunk lengths MUST be padded to 4-byte alignment.
"""
import json
import struct
import sys
import os
from PIL import Image
from io import BytesIO

def read_glb(filepath):
    """Read a GLB/VRM file and return its components"""
    with open(filepath, 'rb') as f:
        # Read header
        magic = f.read(4)
        if magic != b'glTF':
            raise ValueError("Not a valid glTF binary file")
        
        version = struct.unpack('<I', f.read(4))[0]
        total_length = struct.unpack('<I', f.read(4))[0]
        
        # Read JSON chunk
        json_length = struct.unpack('<I', f.read(4))[0]
        json_type = f.read(4)
        json_data = json.loads(f.read(json_length).decode('utf-8').rstrip(' \x00'))
        
        # Read binary chunk
        bin_length = struct.unpack('<I', f.read(4))[0]
        bin_type = f.read(4)
        bin_data = f.read(bin_length)
        
        return json_data, bin_data

def write_glb(filepath, json_data, bin_data):
    """Write a GLB/VRM file according to spec"""
    json_str = json.dumps(json_data, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')
    
    # Pad JSON to 4-byte alignment with spaces
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes_padded = json_bytes + b' ' * json_padding
    
    # Pad binary to 4-byte alignment with null bytes
    bin_padding = (4 - (len(bin_data) % 4)) % 4
    bin_bytes_padded = bin_data + b'\0' * bin_padding
    
    # Total file length
    total_length = 12 + 8 + len(json_bytes_padded) + 8 + len(bin_bytes_padded)
    
    with open(filepath, 'wb') as f:
        # GLB Header (12 bytes)
        f.write(b'glTF')
        f.write(struct.pack('<I', 2))
        f.write(struct.pack('<I', total_length))
        
        # JSON chunk (8 bytes header + padded data)
        f.write(struct.pack('<I', len(json_bytes_padded)))
        f.write(b'JSON')
        f.write(json_bytes_padded)
        
        # Binary chunk (8 bytes header + padded data)
        # CRITICAL: chunk length MUST include the padding!
        f.write(struct.pack('<I', len(bin_bytes_padded)))
        f.write(b'BIN\0')
        f.write(bin_bytes_padded)

def optimize_vrm(input_path, output_path, max_size=1024, jpeg_quality=85):
    """Optimize VRM file by compressing textures"""
    print(f"Reading VRM from: {input_path}")
    json_data, bin_data = read_glb(input_path)
    
    original_size = len(bin_data)
    print(f"Original binary data size: {original_size:,} bytes ({original_size/1024/1024:.2f} MB)")
    
    if 'images' not in json_data:
        print("No images found in VRM")
        return
    
    print(f"\nFound {len(json_data['images'])} textures")
    
    new_bin_data = bytearray()
    
    # Process each buffer view
    for bv_idx, buffer_view in enumerate(json_data['bufferViews']):
        old_offset = buffer_view['byteOffset']
        old_length = buffer_view['byteLength']
        
        # Check if this buffer view is used by an image
        is_image = False
        image_idx = None
        for idx, img in enumerate(json_data['images']):
            if img.get('bufferView') == bv_idx:
                is_image = True
                image_idx = idx
                break
        
        if is_image:
            # Extract and compress the image
            image_data = bin_data[old_offset:old_offset + old_length]
            mime_type = json_data['images'][image_idx].get('mimeType', 'image/png')
            
            print(f"\nTexture {image_idx} (BufferView {bv_idx}):")
            print(f"  Original: {old_length:,} bytes ({old_length/1024:.2f} KB, {mime_type})")
            
            try:
                img = Image.open(BytesIO(image_data))
                print(f"  Resolution: {img.size[0]}x{img.size[1]}")
                
                # Resize if needed
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    print(f"  Resized to: {img.size[0]}x{img.size[1]}")
                
                mode = img.mode
                
                # Compress
                output = BytesIO()
                if mode == 'RGBA' or mode == 'LA' or 'transparency' in img.info:
                    img.save(output, format='PNG', optimize=True)
                    new_mime = 'image/png'
                    print(f"  Saved as PNG (has alpha channel)")
                else:
                    if mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(output, format='JPEG', quality=jpeg_quality, optimize=True)
                    new_mime = 'image/jpeg'
                    print(f"  Converted to JPEG (quality {jpeg_quality})")
                
                compressed_data = output.getvalue()
                print(f"  Compressed: {len(compressed_data):,} bytes ({len(compressed_data)/1024:.2f} KB)")
                print(f"  Reduction: {(1 - len(compressed_data)/old_length)*100:.1f}%")
                
                # Update buffer view
                buffer_view['byteOffset'] = len(new_bin_data)
                buffer_view['byteLength'] = len(compressed_data)
                
                # Add to new buffer
                new_bin_data.extend(compressed_data)
                
                # Update mime type
                json_data['images'][image_idx]['mimeType'] = new_mime
                
            except Exception as e:
                print(f"  Error: {e}, keeping original")
                buffer_view['byteOffset'] = len(new_bin_data)
                new_bin_data.extend(image_data)
        else:
            # Not an image, keep as-is
            buffer_view['byteOffset'] = len(new_bin_data)
            new_bin_data.extend(bin_data[old_offset:old_offset + old_length])
    
    # Update buffer size - this should be the unpadded size
    json_data['buffers'][0]['byteLength'] = len(new_bin_data)
    
    new_size = len(new_bin_data)
    print(f"\nNew binary data size: {new_size:,} bytes ({new_size/1024/1024:.2f} MB)")
    print(f"Total reduction: {(1 - new_size/original_size)*100:.1f}%")
    
    print(f"\nWriting optimized VRM to: {output_path}")
    write_glb(output_path, json_data, bytes(new_bin_data))
    
    output_file_size = os.path.getsize(output_path)
    print(f"Output file size: {output_file_size:,} bytes ({output_file_size/1024/1024:.2f} MB)")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python optimize_vrm.py <input.vrm> <output.vrm> [max_size] [jpeg_quality]")
        print("  max_size: Maximum texture dimension (default: 1024)")
        print("  jpeg_quality: JPEG quality 1-100 (default: 85)")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    max_size = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
    jpeg_quality = int(sys.argv[4]) if len(sys.argv) > 4 else 85
    
    optimize_vrm(input_file, output_file, max_size, jpeg_quality)
