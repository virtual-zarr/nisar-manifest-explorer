#!/usr/bin/env python3
"""
Generate a Kerchunk JSON manifest from a NISAR HDF5 file.

Requires NASA Earthdata authentication (will prompt for login).

Usage:
    uv run --group dev scripts/generate_manifest.py
"""

from pathlib import Path
from urllib.parse import urlparse

import earthaccess
import virtualizarr as vz
import vzviz

from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.stores import AiohttpStore


def main():
    output_dir = Path(__file__).parent.parent / "data"
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

    # Save manifest and metadata
    print(f"Saving manifest to {output_file}...")
    vzviz.save_manifest_to_json(
        manifest_store,
        output_file,
        metadata={
            "source_url": https_url,
            "short_name": "NISAR_L2_GCOV_BETA_V1",
            "frame_number": 77,
            "track_number": 5,
        },
    )

    print(f"Done! Manifest saved to {output_file}")


if __name__ == "__main__":
    main()
