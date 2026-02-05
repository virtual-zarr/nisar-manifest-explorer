---
title: NISAR Manifest Explorer
emoji: 🛰️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# NISAR Manifest Explorer

Interactive visualization of VirtualiZarr chunk manifests for NASA NISAR satellite data.

This dashboard displays the structure of a NISAR HDF5 file without requiring NASA Earthdata authentication - the manifest metadata was pre-generated and bundled with this Space.

## Features

- **Variables Overview**: Browse all variables with their shapes, chunk sizes, and storage info
- **ByteMap**: Visualize how chunks are laid out in the source file(s)
- **ChunkMap**: See the chunk grid structure for selected variables
- **Summary Statistics**: File-level and manifest-level metrics

## Local Development

```bash
# Install dependencies
uv sync

# Run the app
uv run panel serve app.py --show
```

## Regenerating the Manifest

To update the manifest with different NISAR data (requires NASA Earthdata login):

```bash
uv run scripts/generate_manifest.py
```

## About

Built with [vzviz](https://github.com/virtual-zarr/vzviz) and [VirtualiZarr](https://github.com/zarr-developers/VirtualiZarr).
