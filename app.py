"""
NISAR Manifest Explorer

Interactive visualization of VirtualiZarr chunk manifests.
Loads from a pre-generated Kerchunk JSON - no authentication required.
"""

import warnings
from pathlib import Path

import holoviews as hv
import panel as pn

import vzviz

# Suppress zarr numcodecs warning (expected when using V2-style codecs)
warnings.filterwarnings(
    "ignore",
    message="Numcodecs codecs are not in the Zarr version 3 specification",
    category=UserWarning,
)

# Initialize extensions at module level - MUST happen before any components are created
hv.extension("bokeh")
pn.extension("tabulator", sizing_mode="stretch_width")


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
        manifest_store = vzviz.load_manifest_from_json(manifest_file)
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
