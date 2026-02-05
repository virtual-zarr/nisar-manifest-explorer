"""
NISAR Manifest Explorer

Interactive visualization of VirtualiZarr chunk manifests.
Loads from a pre-generated Kerchunk JSON - no authentication required.
"""

from pathlib import Path

import holoviews as hv
import panel as pn
import ujson

from obspec_utils.registry import ObjectStoreRegistry
from virtualizarr.manifests import (
    ChunkManifest,
    ManifestArray,
    ManifestGroup,
    ManifestStore,
)
from virtualizarr.manifests.manifest import ChunkEntry
from virtualizarr.manifests.utils import create_v3_array_metadata
from virtualizarr.codecs import zarr_codec_config_to_v3
from zarr.core.metadata.v3 import ArrayV3Metadata

import numpy as np

import vzviz

# Initialize extensions at module level - MUST happen before any components are created
hv.extension("bokeh")
pn.extension("tabulator", sizing_mode="stretch_width")


def find_var_names_nested(refs: dict) -> list[str]:
    """Find variable names in refs, handling nested paths like 'science/LSAR/data'."""
    var_names = []
    for key in refs.keys():
        if key.endswith("/.zarray"):
            # Remove the /.zarray suffix to get the variable path
            var_name = key[:-8]  # len("/.zarray") == 8
            var_names.append(var_name)
    return var_names


def parse_zarray(zarray_str: str, zattrs: dict) -> "ArrayV3Metadata":
    """Parse a .zarray JSON string into ArrayV3Metadata."""
    zarray = ujson.loads(zarray_str) if isinstance(zarray_str, str) else zarray_str

    dtype = np.dtype(zarray["dtype"])
    fill_value = zarray.get("fill_value")

    # Handle fill_value conversion
    if np.issubdtype(dtype, np.floating) and (
        fill_value is None or fill_value == "NaN" or fill_value == "nan"
    ):
        fill_value = np.nan
    elif np.issubdtype(dtype, np.complexfloating):
        # Complex fill values come as [real, imag] lists
        if isinstance(fill_value, list) and len(fill_value) == 2:
            fill_value = complex(fill_value[0], fill_value[1])
        elif fill_value is None or fill_value == "NaN" or fill_value == "nan":
            fill_value = complex(np.nan, np.nan)

    filters = zarray.get("filters", []) or []
    compressor = zarray.get("compressor")

    codec_configs = [*filters, *(compressor if compressor is not None else [])]
    numcodec_configs = [
        zarr_codec_config_to_v3(config) for config in codec_configs if config
    ]

    dimension_names = zattrs.get("_ARRAY_DIMENSIONS")

    return create_v3_array_metadata(
        chunk_shape=tuple(zarray["chunks"]),
        data_type=dtype,
        codecs=numcodec_configs,
        fill_value=fill_value,
        shape=tuple(zarray["shape"]),
        dimension_names=dimension_names,
        attributes={k: v for k, v in zattrs.items() if k != "_ARRAY_DIMENSIONS"},
    )


def build_nested_group(arrays_dict: dict, root_attrs: dict) -> ManifestGroup:
    """
    Build a nested ManifestGroup hierarchy from a flat dict of arrays.

    Takes a dict like {"science/LSAR/data": ManifestArray, ...} and builds
    nested ManifestGroups.
    """
    # Organize arrays by their group paths
    # Structure: {group_path: {array_name: ManifestArray}}
    groups_tree = {}

    for full_path, array in arrays_dict.items():
        parts = full_path.split("/")
        if len(parts) == 1:
            # Array at root level
            group_path = ""
            array_name = parts[0]
        else:
            # Array in a subgroup
            group_path = "/".join(parts[:-1])
            array_name = parts[-1]

        if group_path not in groups_tree:
            groups_tree[group_path] = {}
        groups_tree[group_path][array_name] = array

    def build_group(path: str) -> ManifestGroup:
        """Recursively build a ManifestGroup for the given path."""
        # Get arrays at this level
        arrays_at_level = groups_tree.get(path, {})

        # Find immediate child groups
        child_groups = {}
        prefix = f"{path}/" if path else ""
        for group_path in groups_tree.keys():
            if group_path == path:
                continue
            # Check if this is an immediate child
            if path == "":
                # Root level - find top-level groups
                if "/" not in group_path:
                    child_name = group_path
                else:
                    child_name = group_path.split("/")[0]
            else:
                if not group_path.startswith(prefix):
                    continue
                remainder = group_path[len(prefix) :]
                if "/" not in remainder:
                    child_name = remainder
                else:
                    child_name = remainder.split("/")[0]

            if child_name and child_name not in child_groups:
                child_path = f"{prefix}{child_name}" if prefix else child_name
                child_groups[child_name] = build_group(child_path)

        attrs = root_attrs if path == "" else {}
        return ManifestGroup(
            arrays=arrays_at_level, groups=child_groups, attributes=attrs
        )

    return build_group("")


def load_manifest_from_json(json_path: str | Path) -> ManifestStore:
    """
    Load a ManifestStore from a Kerchunk JSON file.

    Handles flattened hierarchies where variable names contain slashes
    (e.g., 'science/LSAR/data') and rebuilds the nested group structure.
    """
    with open(json_path) as f:
        kerchunk = ujson.load(f)

    refs = kerchunk["refs"]

    # Find all variable names (paths ending in /.zarray)
    var_names = find_var_names_nested(refs)

    # Build ManifestArrays for each variable
    arrays = {}
    for var_name in var_names:
        # Get .zarray and .zattrs
        zarray_key = f"{var_name}/.zarray"
        zattrs_key = f"{var_name}/.zattrs"

        zarray_str = refs.get(zarray_key)
        zattrs_str = refs.get(zattrs_key, "{}")

        if not zarray_str:
            continue

        zattrs = ujson.loads(zattrs_str) if isinstance(zattrs_str, str) else zattrs_str

        # Parse metadata
        metadata = parse_zarray(zarray_str, zattrs)

        # Collect chunk entries
        chunk_entries = {}
        prefix = f"{var_name}/"
        for key, value in refs.items():
            if key.startswith(prefix) and not key.endswith(
                (".zarray", ".zattrs", ".zgroup")
            ):
                chunk_key = key[len(prefix) :]
                # Skip empty chunk keys or invalid entries
                if not chunk_key or chunk_key.startswith("."):
                    continue
                if isinstance(value, list) and len(value) == 3:
                    path, offset, length = value
                    chunk_entries[chunk_key] = ChunkEntry.with_validation(
                        path=path, offset=offset, length=length
                    )

        if chunk_entries:
            manifest = ChunkManifest(entries=chunk_entries)
            arrays[var_name] = ManifestArray(metadata=metadata, chunkmanifest=manifest)

    # Get root attributes
    root_attrs_str = refs.get(".zattrs", "{}")
    root_attrs = (
        ujson.loads(root_attrs_str)
        if isinstance(root_attrs_str, str)
        else root_attrs_str
    )

    # Build nested group hierarchy
    group = build_nested_group(arrays, root_attrs)

    return ManifestStore(group=group, registry=ObjectStoreRegistry())


def create_app():
    """Create the Panel application."""
    manifest_file = Path(__file__).parent / "data" / "nisar_manifest.json"

    if not manifest_file.exists():
        return pn.Column(
            pn.pane.Markdown("# Manifest Not Found"),
            pn.pane.Markdown(
                f"Expected manifest at: `{manifest_file}`\n\n"
                "Run `uv run --group dev scripts/generate_manifest.py` to create it."
            ),
        )

    try:
        manifest_store = load_manifest_from_json(manifest_file)
        return vzviz.manifest_dashboard(manifest_store)
    except Exception:
        import traceback

        return pn.Column(
            pn.pane.Markdown("# Error Loading Manifest"),
            pn.pane.Markdown(f"```\n{traceback.format_exc()}\n```"),
        )


# Create the app - this is what panel serve looks for
app = create_app()

# Make it servable for panel serve
app.servable(title="NISAR Manifest Explorer")

if __name__ == "__main__":
    app.show(title="NISAR Manifest Explorer")
