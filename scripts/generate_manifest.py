#!/usr/bin/env python3
"""
Generate a Kerchunk JSON manifest from a NISAR HDF5 file.

Requires NASA Earthdata authentication (will prompt for login).

Usage:
    uv run --group dev scripts/generate_manifest.py
"""

import json
from pathlib import Path
from urllib.parse import urlparse

import earthaccess
import ujson
import virtualizarr as vz

from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.stores import AiohttpStore
from virtualizarr.manifests import ManifestStore
from virtualizarr.utils import convert_v3_to_v2_metadata
from virtualizarr.writers.kerchunk import to_kerchunk_json


def manifeststore_to_kerchunk_refs(store: ManifestStore) -> dict:
    """
    Convert a ManifestStore directly to Kerchunk refs format.

    This bypasses xarray entirely, avoiding dimension conflict errors
    that can occur with complex HDF5 files like NISAR.

    The hierarchy is flattened so all arrays appear at the root level
    with their full paths as names (e.g., "science/LSAR/data").
    This is compatible with manifestgroup_from_kerchunk_refs.
    """
    refs = {}

    # Root group metadata
    refs[".zgroup"] = '{"zarr_format":2}'
    root_attrs = store._group.metadata.attributes or {}
    refs[".zattrs"] = ujson.dumps(root_attrs)

    def collect_arrays(group, path_prefix=""):
        """Recursively collect all arrays with their full paths."""
        arrays = []

        for array_name, array in group.arrays.items():
            full_path = f"{path_prefix}/{array_name}" if path_prefix else array_name
            arrays.append((full_path, array))

        for group_name, subgroup in group.groups.items():
            sub_path = f"{path_prefix}/{group_name}" if path_prefix else group_name
            arrays.extend(collect_arrays(subgroup, sub_path))

        return arrays

    all_arrays = collect_arrays(store._group)

    for array_path, array in all_arrays:
        # Convert V3 metadata to V2 for Kerchunk compatibility
        v2_metadata = convert_v3_to_v2_metadata(array.metadata)
        refs[f"{array_path}/.zarray"] = to_kerchunk_json(v2_metadata)

        # Array attributes (including dimension names if available)
        array_attrs = {}
        if array.metadata.dimension_names:
            array_attrs["_ARRAY_DIMENSIONS"] = list(array.metadata.dimension_names)
        refs[f"{array_path}/.zattrs"] = ujson.dumps(array_attrs)

        # Chunk references
        for chunk_key, entry in array.manifest.dict().items():
            path = entry["path"]
            # Remove file:// prefix if present
            if path.startswith("file://"):
                path = path[7:]
            # Handle scalar arrays (empty chunk key) - use "c" for Kerchunk compatibility
            if chunk_key == "":
                chunk_key = "c"
            refs[f"{array_path}/{chunk_key}"] = [
                path,
                entry["offset"],
                entry["length"],
            ]

    return {"version": 1, "refs": refs}


def main():
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "nisar_manifest.json"

    print("Authenticating with NASA Earthdata...")
    earthaccess.login()

    print("Searching for NISAR data...")
    query = earthaccess.DataGranules()
    query.short_name("NISAR_L2_GCOV_BETA_V1")
    query.params["attribute[]"] = "int,FRAME_NUMBER,77"
    query.params["attribute[]"] = "int,TRACK_NUMBER,5"
    results = query.get_all()
    print(f"Found {len(results)} granules")

    if not results:
        print("No granules found. Check query parameters.")
        return

    # Get the HTTPS URL
    https_links = earthaccess.results.DataGranule.data_links(
        results[0], access="external"
    )
    https_url = https_links[0]
    print(f"URL: {https_url}")

    # Parse URL and get auth token
    parsed = urlparse(https_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    token = earthaccess.get_edl_token()["access_token"]

    # Create store with authentication
    store = AiohttpStore(
        base_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    registry = ObjectStoreRegistry({base_url: store})

    print("Parsing HDF5 file...")
    parser = vz.parsers.HDFParser()
    manifest_store = parser(https_url, registry=registry)
    print("ManifestStore created!")

    # Convert directly to Kerchunk JSON (bypasses xarray to avoid dimension conflicts)
    print("Converting to Kerchunk format...")
    kerchunk_refs = manifeststore_to_kerchunk_refs(manifest_store)

    print(f"Saving manifest to {output_file}...")
    with open(output_file, "w") as f:
        ujson.dump(kerchunk_refs, f)

    # Save metadata about the source
    metadata_file = output_dir / "manifest_metadata.json"
    metadata = {
        "source_url": https_url,
        "short_name": "NISAR_L2_GCOV_BETA_V1",
        "frame_number": 77,
        "track_number": 5,
    }
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Done! Manifest saved to {output_file}")


if __name__ == "__main__":
    main()
