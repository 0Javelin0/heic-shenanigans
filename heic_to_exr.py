#!/usr/bin/env python3

import os
import sys
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import pillow_heif
import numpy as np
import subprocess
import json

def extract_heic(input_path, output_dir):
    """Extract all images from HEIC file to TIFFs."""
    print(f"\nExtracting images from {input_path}...")
    
    heif_file = pillow_heif.read_heif(str(input_path))
    print(f"HEIC info: {heif_file.info}")
    
    # Initialize paths
    base_path = None
    gain_map_path = None
    depth_path = None
    matte_paths = []
    headroom = None
    
    # Extract base image
    print("\nExtracting base image...")
    base_image = Image.frombytes(
        heif_file.mode,
        heif_file.size,
        heif_file.data,
        "raw",
        heif_file.mode,
        heif_file.stride,
    )
    base_path = output_dir / "input_base.tiff"
    base_image.save(base_path, format='TIFF')
    print(f"Saved base image to {base_path}")
    
    # Extract gain map
    print("\nLooking for gain map...")
    if 'aux' in heif_file.info:
        print(f"Found aux data: {heif_file.info['aux']}")
        if 'urn:com:apple:photo:2020:aux:hdrgainmap' in heif_file.info['aux']:
            try:
                aux_id = heif_file.info['aux']['urn:com:apple:photo:2020:aux:hdrgainmap'][0]
                print(f"Found gain map aux ID: {aux_id}")
                aux_image = heif_file.get_aux_image(aux_id)
                gain_map = Image.frombytes(
                    aux_image.mode,
                    aux_image.size,
                    aux_image.data,
                    "raw",
                    aux_image.mode,
                    aux_image.stride,
                )
                gain_map_path = output_dir / "input_hdrgainmap_50.tiff"
                gain_map.save(gain_map_path, format='TIFF')
                print(f"Saved gain map to {gain_map_path}")
            except Exception as e:
                print(f"Warning: Could not extract gain map: {str(e)}")
        else:
            print("No gain map found in aux data")
    else:
        print("No aux data found in HEIC")
    
    # Extract depth map
    print("\nLooking for depth map...")
    if 'depth_images' in heif_file.info and heif_file.info['depth_images']:
        try:
            depth_image = heif_file.info['depth_images'][0]
            depth_map = Image.frombytes(
                depth_image.mode,
                depth_image.size,
                depth_image.data,
                "raw",
                depth_image.mode,
                depth_image.stride,
            )
            depth_path = output_dir / "input_depth_0.tiff"
            depth_map.save(depth_path, format='TIFF')
            print(f"Saved depth map to {depth_path}")
        except Exception as e:
            print(f"Warning: Could not extract depth map: {str(e)}")
    else:
        print("No depth map found")
    
    # Extract mattes
    print("\nLooking for mattes...")
    if 'aux' in heif_file.info:
        for aux_type, aux_ids in heif_file.info['aux'].items():
            if 'matte' in aux_type.lower():
                print(f"Found matte type: {aux_type}")
                for aux_id in aux_ids:
                    try:
                        aux_image = heif_file.get_aux_image(aux_id)
                        aux_pil = Image.frombytes(
                            aux_image.mode,
                            aux_image.size,
                            aux_image.data,
                            "raw",
                            aux_image.mode,
                            aux_image.stride,
                        )
                        aux_type_name = aux_type.split(':')[-1]
                        aux_path = output_dir / f"input_{aux_type_name}_{aux_id}.tiff"
                        aux_pil.save(aux_path, format='TIFF')
                        matte_paths.append(aux_path)
                        print(f"Saved matte {aux_id} to {aux_path}")
                    except Exception as e:
                        print(f"Warning: Could not extract matte {aux_id}: {str(e)}")
    else:
        print("No mattes found")
    
    # Get HDR headroom
    if 'HDRGainMapHeadroom' in heif_file.info:
        headroom = heif_file.info['HDRGainMapHeadroom']
        print(f"\nFound HDR headroom: {headroom}")
    else:
        print("\nNo HDR headroom found in HEIC info")
    
    return base_path, gain_map_path, depth_path, matte_paths, headroom

def merge_to_exr(input_dir, original_heic, output_path):
    """Merge extracted TIFFs into a multilayer EXR."""
    print("\nMerging to EXR...")
    
    # Get dimensions from base image
    print("Getting image dimensions...")
    base_info = subprocess.check_output(['oiiotool', '--info', str(input_dir / "input_base.tiff")]).decode()
    print(f"Base image info: {base_info}")
    width = int(base_info.split()[2])
    height = int(base_info.split()[4].rstrip(','))
    print(f"Image dimensions: {width}x{height}")

    # Process base image (RGB) - Convert from sRGB curve through Linear P3 to ACEScg
    print("\nProcessing base image...")
    subprocess.run([
        'oiiotool', str(input_dir / "input_base.tiff"),
        '--ch', 'R,G,B',
        '--chnames', 'sdr.R,sdr.G,sdr.B',
        '--colorconfig', 'studio-config-v1.0.0_aces-v1.3_ocio-v2.1.ocio',
        '--colorconvert', 'sRGB - Texture', 'Linear Rec.709 (sRGB)',
        '--colorconvert', 'Linear P3-D65', 'ACES - ACEScg',
        '-o', str(input_dir / "base.exr")
    ], check=True)
    print("Base image processed")

    # Process gain map if it exists
    gain_map_path = input_dir / "input_hdrgainmap_50.tiff"
    if gain_map_path.exists():
        print("\nProcessing gain map...")
        # Process gain map (Y) - Convert from Rec709 curve to Linear
        subprocess.run([
            'oiiotool', str(gain_map_path),
            '--ch', 'Y',
            '--chnames', 'gainmap.Y',
            '--resize', f"{width}x{height}",
            '--colorconfig', 'studio-config-v1.0.0_aces-v1.3_ocio-v2.1.ocio',
            '--ocionamedtransform', 'Rec.709 - Curve',
            '-o', str(input_dir / "gainmap.exr")
        ], check=True)
        print("Gain map processed")

        # Create 3-channel gainmap by duplicating Y to RGB
        subprocess.run([
            'oiiotool', str(input_dir / "gainmap.exr"),
            '--ch', 'gainmap.Y,gainmap.Y,gainmap.Y',
            '--chnames', 'gainmap.R,gainmap.G,gainmap.B',
            '-o', str(input_dir / "gainmap_rgb.exr")
        ], check=True)
        print("Gain map converted to RGB")

        # Calculate HDR: first multiply gainmap by (headroom - 1.0)
        headroom = float(subprocess.check_output(['exiftool', '-HDRGainMapHeadroom', '-b', str(original_heic)]).decode())
        print(f"Using HDR headroom: {headroom}")
        subprocess.run([
            'oiiotool', str(input_dir / "gainmap_rgb.exr"),
            '--mulc', str(headroom - 1.0),
            '--addc', '1.0',
            '-o', str(input_dir / "gainmap_scaled.exr")
        ], check=True)
        print("Gain map scaled")

        # Then multiply base image by scaled gainmap
        subprocess.run([
            'oiiotool', str(input_dir / "base.exr"),
            str(input_dir / "gainmap_scaled.exr"),
            '--mul',
            '--chnames', 'R,G,B',
            '-o', str(input_dir / "hdr_base.exr")
        ], check=True)
        print("HDR base created")
    else:
        print("\nNo gain map found, using base image as HDR base")
        shutil.copy(str(input_dir / "base.exr"), str(input_dir / "hdr_base.exr"))

    # Process depth if it exists
    depth_path = input_dir / "input_depth_0.tiff"
    if depth_path.exists():
        print("\nProcessing depth map...")
        subprocess.run([
            'oiiotool', str(depth_path),
            '--ch', 'Y',
            '--chnames', 'depth.Y',
            '--resize', f"{width}x{height}",
            '-o', str(input_dir / "depth.exr")
        ], check=True)
        print("Depth map processed")
    else:
        print("\nNo depth map found")

    # Process mattes
    print("\nProcessing mattes...")
    for matte in input_dir.glob("input_*matte_*.tiff"):
        if matte.exists():
            clean_name = matte.stem.replace("input_", "").replace("matte_", "")
            print(f"Processing matte: {clean_name}")
            subprocess.run([
                'oiiotool', str(matte),
                '--ch', 'Y',
                '--chnames', f"mattes.{clean_name}.Y",
                '--resize', f"{width}x{height}",
                '-o', str(input_dir / f"{clean_name}.exr")
            ], check=True)
            print(f"Matte {clean_name} processed")
    else:
        print("No mattes found")

    # Create final EXR with HDR as main RGB
    print("\nCreating final EXR...")
    subprocess.run([
        'oiiotool', str(input_dir / "hdr_base.exr"),
        '--ch', 'R,G,B',
        '-o', str(input_dir / "final.exr")
    ], check=True)
    print("Base layer created")

    # Add SDR layer
    print("Adding SDR layer...")
    subprocess.run([
        'oiiotool', str(input_dir / "final.exr"),
        str(input_dir / "base.exr"),
        '--ch', 'sdr.R,sdr.G,sdr.B',
        '--siappend',
        '-o', str(input_dir / "final.exr")
    ], check=True)
    print("SDR layer added")

    # Add gainmap layer if it exists
    if gain_map_path.exists():
        print("Adding gainmap layer...")
        subprocess.run([
            'oiiotool', str(input_dir / "final.exr"),
            str(input_dir / "gainmap_rgb.exr"),
            '--ch', 'gainmap.R,gainmap.G,gainmap.B',
            '--siappend',
            '-o', str(input_dir / "final.exr")
        ], check=True)
        print("Gainmap layer added")

    # Add depth layer if it exists
    if depth_path.exists():
        print("Adding depth layer...")
        subprocess.run([
            'oiiotool', str(input_dir / "final.exr"),
            str(input_dir / "depth.exr"),
            '--ch', 'depth.Y',
            '--siappend',
            '-o', str(input_dir / "final.exr")
        ], check=True)
        print("Depth layer added")

    # Add matte layers
    print("Adding matte layers...")
    for matte in input_dir.glob("*.exr"):
        if matte.stem.startswith("semantic"):
            clean_name = matte.stem
            print(f"Adding matte layer: {clean_name}")
            subprocess.run([
                'oiiotool', str(input_dir / "final.exr"),
                str(matte),
                '--ch', f"mattes.{clean_name}.Y",
                '--siappend',
                '-o', str(input_dir / "final.exr")
            ], check=True)
            print(f"Matte layer {clean_name} added")

    # Move to final destination
    print(f"\nMoving final EXR to {output_path}")
    shutil.move(str(input_dir / "final.exr"), str(output_path))
    print("Done!")

def main():
    if len(sys.argv) != 2:
        print("Usage: python heic_to_exr.py <input.heic>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist")
        sys.exit(1)

    # Create output path next to input file
    output_path = input_path.parent / f"{input_path.stem}_acesCG.exr"

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        print(f"Using temporary directory: {temp_dir}")
        
        # Extract images from HEIC
        base_path, gain_map_path, depth_path, matte_paths, headroom = extract_heic(input_path, temp_dir)
        
        # Merge to EXR
        merge_to_exr(temp_dir, input_path, output_path)

    print(f"\nSuccessfully created: {output_path}")

if __name__ == "__main__":
    main() 