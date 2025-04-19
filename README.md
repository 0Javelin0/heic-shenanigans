# 🖼️ HEIC Image Extractor

A Python tool for extracting all components from HEIC (High Efficiency Image Container) files, including HDR gain maps, depth maps, and metadata.

## ✨ Features

- 📸 Extracts the base image from HEIC files
- 🎨 Extracts auxiliary images including gain maps (for HDR)
- 📊 Extracts depth maps when available
- 📝 Preserves all metadata including:
  - 🎨 ICC color profiles
  - 📸 EXIF data
  - 📄 XMP metadata
  - 🔄 Other auxiliary image data

## 📋 Requirements

- 🐍 Python 3.x
- 📦 Required Python packages:
  - Pillow
  - pillow-heif
  - numpy

## 💻 Usage

```bash
python gain_map_extract.py input.heic [--output-dir OUTPUT_DIR]
```

### ⚙️ Arguments

- `input`: Path to the input HEIC image
- `--output-dir`: (Optional) Directory where extracted files will be saved. If not specified, files will be saved in the same directory as the input file.

### 📁 Output Files

For each input HEIC file, the tool generates:

1. 📸 Base image: `{filename}_base.tiff`
2. 🎨 Auxiliary images (if present): `{filename}_{aux_type}_{id}.tiff`
3. 📊 Depth maps (if present): `{filename}_depth_{index}.tiff`
4. 📄 Metadata: `{filename}_metadata.json`

The metadata JSON file contains:
- 📐 Image information (mode, size, stride)
- 🎨 ICC profile data
- 📸 EXIF data
- 📄 XMP metadata
- 🔄 All auxiliary image information

## 🚀 Example

```bash
python gain_map_extract.py photo.heic --output-dir extracted_images
```

This will create:
- 📸 `extracted_images/photo_base.tiff`
- 🎨 `extracted_images/photo_gain_map_1.tiff` (if HDR gain map exists)
- 📊 `extracted_images/photo_depth_0.tiff` (if depth map exists)
- 📄 `extracted_images/photo_metadata.json`

## 📝 Notes

- 🎯 All images are saved in TIFF format to preserve maximum quality
- 🔄 The tool handles both standard HEIC files and HDR HEIC files
- 🔐 Metadata is base64 encoded in the JSON file to handle binary data
