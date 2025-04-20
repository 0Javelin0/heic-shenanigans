#!/bin/bash

if [ $# -lt 2 ]; then
    echo "Usage: ./merge_to_exr.sh <input_folder> <original.HEIC> [output.exr]"
    exit 1
fi

input_folder="$1"
original_heic="$2"
output_path="${3:-output_acesCG.exr}"

# Create a temporary directory for intermediate files
temp_dir=$(mktemp -d)
echo "Using temporary directory: $temp_dir"

# Get dimensions from base image
base_info=$(oiiotool --info "$input_folder/input_base.tiff" | head -n1)
width=$(echo "$base_info" | cut -d' ' -f3)
height=$(echo "$base_info" | cut -d' ' -f5 | tr -d ',')

if [ -z "$width" ] || [ -z "$height" ]; then
    echo "Error: Could not determine image dimensions"
    echo "Debug info: $base_info"
    exit 1
fi
echo "Image dimensions: ${width}x${height}"

# Extract headroom from original HEIC
headroom=$(exiftool -HDRGainMapHeadroom -b "$original_heic")
if [ -z "$headroom" ]; then
    echo "Error: Could not extract HDR headroom"
    exit 1
fi
echo "Extracted HDR headroom: $headroom"

# List all input files
echo "Input files found:"
ls -1 "$input_folder"/*.tiff

# Process base image (RGB) - Convert from sRGB curve through Linear P3 to ACEScg
echo "Processing base image..."
oiiotool "$input_folder/input_base.tiff" \
    --ch R,G,B \
    --chnames sdr.R,sdr.G,sdr.B \
    --colorconfig studio-config-v1.0.0_aces-v1.3_ocio-v2.1.ocio \
    --colorconvert "sRGB - Texture" "Linear Rec.709 (sRGB)" \
    --colorconvert "Linear P3-D65" "ACES - ACEScg" \
    -o "$temp_dir/base.exr" || exit 1

# Process gain map (Y) - Convert from Rec709 curve to Linear
echo "Processing gain map..."
oiiotool "$input_folder/input_hdrgainmap_50.tiff" \
    --ch Y \
    --chnames gainmap.Y \
    --resize "${width}x${height}" \
    --colorconfig studio-config-v1.0.0_aces-v1.3_ocio-v2.1.ocio \
    --ocionamedtransform "Rec.709 - Curve" \
    -o "$temp_dir/gainmap.exr" || exit 1

# Process depth (Y)
echo "Processing depth map..."
oiiotool "$input_folder/input_depth_0.tiff" \
    --ch Y \
    --chnames depth.Y \
    --resize "${width}x${height}" \
    -o "$temp_dir/depth.exr" || exit 1

# Process all mattes (Y)
echo "Processing mattes..."
for matte in "$input_folder"/input_*matte_*.tiff; do
    if [ -f "$matte" ]; then
        name=$(basename "$matte" .tiff)
        # Clean up the matte name to be more Nuke-friendly
        clean_name=$(echo "$name" | sed 's/input_//' | sed 's/matte_//')
        echo "Processing matte: $clean_name"
        oiiotool "$matte" \
            --ch Y \
            --chnames "mattes.$clean_name.Y" \
            --resize "${width}x${height}" \
            -o "$temp_dir/$clean_name.exr" || exit 1
    else
        echo "Warning: No matte files found matching pattern: $matte"
    fi
done

# Apply HDR formula: hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)
echo "Applying HDR formula..."
# Create 3-channel gainmap by duplicating Y to RGB
oiiotool "$temp_dir/gainmap.exr" \
    --ch gainmap.Y,gainmap.Y,gainmap.Y \
    --chnames R,G,B \
    -o "$temp_dir/gainmap_rgb.exr" || exit 1

# Calculate HDR: first multiply gainmap by (headroom - 1.0)
oiiotool "$temp_dir/gainmap_rgb.exr" \
    --mulc "$(echo "$headroom - 1.0" | bc -l)" \
    --addc 1.0 \
    -o "$temp_dir/gainmap_scaled.exr" || exit 1

# Then multiply base image by scaled gainmap
oiiotool "$temp_dir/base.exr" \
    "$temp_dir/gainmap_scaled.exr" \
    --mul \
    --chnames R,G,B \
    -o "$temp_dir/hdr_base.exr" || exit 1

# Create final EXR
echo "Creating final multilayer EXR..."

# First, create with HDR as main RGB
oiiotool "$temp_dir/hdr_base.exr" \
    --ch R,G,B \
    -o "$temp_dir/final.exr" || exit 1

# Add SDR layer
oiiotool "$temp_dir/final.exr" "$temp_dir/base.exr" \
    --ch sdr.R,sdr.G,sdr.B \
    --siappend \
    -o "$temp_dir/final.exr" || exit 1

# Add gainmap layer (using the RGB version we created earlier)
oiiotool "$temp_dir/final.exr" "$temp_dir/gainmap_rgb.exr" \
    --ch R,G,B \
    --chnames gainmap.R,gainmap.G,gainmap.B \
    --siappend \
    -o "$temp_dir/final.exr" || exit 1

# Add depth layer
oiiotool "$temp_dir/final.exr" "$temp_dir/depth.exr" \
    --ch depth.Y \
    --siappend \
    -o "$temp_dir/final.exr" || exit 1

# Add matte layers
for m in "$temp_dir"/semantic*.exr; do
    if [ -f "$m" ]; then
        clean_name=$(basename "$m" .exr)
        oiiotool "$temp_dir/final.exr" "$m" \
            --ch "mattes.$clean_name.Y" \
            --siappend \
            -o "$temp_dir/final.exr" || exit 1
    fi
done

# Move to final destination
mv "$temp_dir/final.exr" "$output_path"

# Clean up temporary files
rm -rf "$temp_dir"

echo "Successfully merged TIFFs into: $output_path" 