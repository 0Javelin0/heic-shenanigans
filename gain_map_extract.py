#!/usr/bin/env python3

import os
from PIL import Image
import pillow_heif
import numpy as np
from pathlib import Path
import json
import base64

def extract_all_images(input_path, output_dir=None):
    """
    Extract all images from a HEIC file including base image, gain map, depth map, and all auxiliary images.
    Also dumps all metadata into a JSON file.
    
    Args:
        input_path (str): Path to input HDR image (HEIC or JPEG)
        output_dir (str, optional): Directory for output files. If None, will use input file's directory.
    """
    input_path = Path(input_path)
    
    # Create output directory if not provided
    if output_dir is None:
        output_dir = input_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Read HEIC file
    heif_file = pillow_heif.read_heif(str(input_path))
    
    # Dictionary to store all extracted images and their paths
    extracted_images = {}
    
    # Get primary image
    base_image = Image.frombytes(
        heif_file.mode,
        heif_file.size,
        heif_file.data,
        "raw",
        heif_file.mode,
        heif_file.stride,
    )
    base_path = output_dir / f"{input_path.stem}_base.tiff"
    base_image.save(base_path, format='TIFF')
    extracted_images['base'] = str(base_path)
    
    # Extract all auxiliary images
    if 'aux' in heif_file.info:
        for aux_type, aux_ids in heif_file.info['aux'].items():
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
                    
                    # Create a sanitized filename from the aux type
                    aux_type_name = aux_type.split(':')[-1]
                    aux_path = output_dir / f"{input_path.stem}_{aux_type_name}_{aux_id}.tiff"
                    aux_pil.save(aux_path, format='TIFF')
                    extracted_images[f"{aux_type_name}_{aux_id}"] = str(aux_path)
                except Exception as e:
                    print(f"Warning: Could not extract auxiliary image {aux_id} of type {aux_type}: {str(e)}")
    
    # Extract depth images if available
    if 'depth_images' in heif_file.info and heif_file.info['depth_images']:
        for i, depth_image in enumerate(heif_file.info['depth_images']):
            depth_pil = Image.frombytes(
                depth_image.mode,
                depth_image.size,
                depth_image.data,
                "raw",
                depth_image.mode,
                depth_image.stride,
            )
            depth_path = output_dir / f"{input_path.stem}_depth_{i}.tiff"
            depth_pil.save(depth_path, format='TIFF')
            extracted_images[f"depth_{i}"] = str(depth_path)
    
    # Prepare metadata
    metadata = {
        'info': {},
        'aux_images': {},
        'depth_images': [],
        'icc_profile': None,
        'exif': None,
        'xmp': None,
        'primary': {
            'mode': heif_file.mode,
            'size': heif_file.size,
            'stride': heif_file.stride
        }
    }
    
    # Copy all info
    for key, value in heif_file.info.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            metadata['info'][key] = value
        elif isinstance(value, bytes):
            # Convert bytes to base64 for JSON serialization
            metadata['info'][key] = base64.b64encode(value).decode('utf-8')
        elif isinstance(value, dict):
            metadata['info'][key] = {
                k: base64.b64encode(v).decode('utf-8') if isinstance(v, bytes) else v
                for k, v in value.items()
            }
    
    # Handle ICC profile
    if 'icc_profile' in heif_file.info:
        metadata['icc_profile'] = base64.b64encode(heif_file.info['icc_profile']).decode('utf-8')
    
    # Handle EXIF
    if 'exif' in heif_file.info:
        metadata['exif'] = base64.b64encode(heif_file.info['exif']).decode('utf-8')
    
    # Handle XMP
    if 'xmp' in heif_file.info:
        metadata['xmp'] = base64.b64encode(heif_file.info['xmp']).decode('utf-8')
    
    # Save metadata to file
    metadata_path = output_dir / f"{input_path.stem}_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Return paths and metadata
    result = {
        'extracted_images': extracted_images,
        'metadata_path': str(metadata_path)
    }
    
    return result

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract all images and metadata from HEIC files')
    parser.add_argument('input', help='Input HEIC image path')
    parser.add_argument('--output-dir', help='Output directory for extracted images')
    
    args = parser.parse_args()
    
    try:
        result = extract_all_images(args.input, args.output_dir)
        print("\nExtracted images:")
        for name, path in result['extracted_images'].items():
            print(f"{name}: {path}")
        print(f"\nMetadata saved to: {result['metadata_path']}")
    except Exception as e:
        print(f"Error: {str(e)}")
