"""
NISAR Byte Range Interleaving Analysis

Creates a static visualization showing how chunks from different variables
are interleaved in an HDF5 file, and why selecting a spatial region results
in scattered I/O operations.

Usage:
    uv run python scripts/interleaving_analysis.py
"""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def load_chunks(json_path: str | Path) -> list[dict]:
    """Load chunk data from the NISAR manifest."""
    with open(json_path) as f:
        data = json.load(f)

    refs = data.get("refs", data)

    chunks = []
    for key, value in refs.items():
        if isinstance(value, list) and len(value) == 3:
            path, offset, length = value
            parts = key.rsplit("/", 1)
            variable = parts[0] if len(parts) == 2 else key
            chunk_key = parts[1] if len(parts) == 2 else ""
            chunks.append(
                {
                    "variable": variable,
                    "chunk_key": chunk_key,
                    "offset": offset,
                    "length": length,
                    "end": offset + length,
                }
            )

    return sorted(chunks, key=lambda x: x["offset"])


def get_variable_short_name(var: str) -> str:
    """Shorten variable names for display."""
    return var.split("/")[-1]


def create_interleaving_figure(chunks: list[dict], output_path: str | Path):
    """Create a figure showing byte range interleaving."""

    # Get HHHH chunks for column dim_1=10
    hhhh_chunks = [c for c in chunks if "HHHH" in c["variable"]]
    col_10 = [c for c in hhhh_chunks if c["chunk_key"].split(".")[1] == "10"]
    col_10_sorted = sorted(col_10, key=lambda x: x["offset"])

    # Calculate metrics
    total_data = sum(c["length"] for c in col_10_sorted)
    min_offset = col_10_sorted[0]["offset"]
    max_offset = col_10_sorted[-1]["end"]
    byte_span = max_offset - min_offset
    read_amp = byte_span / total_data

    # Find other chunks within this byte range
    other_chunks = [
        c
        for c in chunks
        if min_offset <= c["offset"] <= max_offset and "HHHH" not in c["variable"]
    ]

    # Count by variable
    var_counts = defaultdict(lambda: {"count": 0, "bytes": 0})
    for c in other_chunks:
        name = get_variable_short_name(c["variable"])
        var_counts[name]["count"] += 1
        var_counts[name]["bytes"] += c["length"]

    # Create figure with 3 subplots
    fig = plt.figure(figsize=(16, 14))

    # Define grid: top row spans full width, bottom row has 2 plots, summary at bottom
    gs = fig.add_gridspec(3, 2, height_ratios=[1.2, 1, 1], hspace=0.4, wspace=0.3)

    # =========================================================================
    # Plot 1: Byte range overview (top, full width)
    # =========================================================================
    ax1 = fig.add_subplot(gs[0, :])

    # Color palette
    colors = {
        "HHHH": "#e41a1c",  # Red - our selection
        "HVHV": "#377eb8",  # Blue
        "mask": "#4daf4a",  # Green
        "numberOfLooks": "#984ea3",  # Purple
        "elevationAngle": "#ff7f00",  # Orange
        "other": "#999999",  # Gray
    }

    # Plot all chunks in the byte range as thin bars
    y_positions = {"HHHH": 0, "HVHV": 1, "mask": 2, "numberOfLooks": 3, "other": 4}

    # Normalize to MB for display
    norm = 1e6

    for c in chunks:
        if c["offset"] < min_offset or c["offset"] > max_offset:
            continue

        short_name = get_variable_short_name(c["variable"])
        if short_name not in y_positions:
            short_name = "other"

        y = y_positions[short_name]
        color = colors.get(short_name, colors["other"])
        alpha = 1.0 if short_name == "HHHH" else 0.6

        ax1.barh(
            y,
            c["length"] / norm,
            left=c["offset"] / norm,
            height=0.7,
            color=color,
            alpha=alpha,
            edgecolor="none",
        )

    # Highlight selected HHHH chunks in solid black
    for i, c in enumerate(col_10_sorted):
        ax1.barh(
            0,
            c["length"] / norm,
            left=c["offset"] / norm,
            height=0.7,
            color="black",
            edgecolor="black",
            linewidth=0.5,
            label="Selected chunks (col 10)" if i == 0 else None,
        )

    # Add legend for the top plot
    # Create custom legend handles
    from matplotlib.patches import Patch

    legend_handles = [
        Patch(facecolor="black", edgecolor="black", label="Selected (column 10)"),
        Patch(facecolor=colors["HHHH"], edgecolor="none", label="HHHH (other)"),
        Patch(facecolor=colors["HVHV"], edgecolor="none", label="HVHV"),
        Patch(facecolor=colors["mask"], edgecolor="none", label="mask"),
        Patch(
            facecolor=colors["numberOfLooks"], edgecolor="none", label="numberOfLooks"
        ),
        Patch(facecolor=colors["other"], edgecolor="none", label="other"),
    ]
    ax1.legend(handles=legend_handles, loc="upper right", fontsize=9, ncol=2)

    ax1.set_yticks(list(y_positions.values()))
    ax1.set_yticklabels(list(y_positions.keys()))
    ax1.set_xlabel("Byte Offset (MB)", fontsize=12)
    ax1.set_xlim(min_offset / norm - 10, max_offset / norm + 10)
    ax1.set_title(
        f"Byte Layout: Selecting HHHH column 10 spans {byte_span/1e6:.0f} MB "
        f"(data: {total_data/1e6:.1f} MB, {read_amp:.0f}× read amplification)",
        fontsize=14,
        fontweight="bold",
    )

    # Add span indicator
    ax1.axvline(min_offset / norm, color="red", linestyle="--", alpha=0.7, linewidth=2)
    ax1.axvline(max_offset / norm, color="red", linestyle="--", alpha=0.7, linewidth=2)

    # =========================================================================
    # Plot 2: Zoomed view showing interleaving detail
    # =========================================================================
    ax2 = fig.add_subplot(gs[1, 0])

    # Zoom into 80-95 MB region where we saw clear interleaving
    zoom_min, zoom_max = 80e6, 95e6
    zoom_chunks = [c for c in chunks if zoom_min <= c["offset"] <= zoom_max]

    y_pos = 0
    bar_height = 0.8
    labels_added = set()

    for c in zoom_chunks:
        short_name = get_variable_short_name(c["variable"])
        color = colors.get(short_name, colors["other"])

        label = short_name if short_name not in labels_added else None
        labels_added.add(short_name)

        ax2.barh(
            y_pos,
            c["length"] / norm,
            left=c["offset"] / norm,
            height=bar_height,
            color=color,
            edgecolor="white",
            linewidth=0.5,
            label=label,
        )
        y_pos += 1

    ax2.set_xlabel("Byte Offset (MB)", fontsize=11)
    ax2.set_ylabel("Chunk Index (sorted by offset)", fontsize=11)
    ax2.set_title("Zoomed: 80-95 MB (showing interleaved chunks)", fontsize=12)
    ax2.legend(loc="upper right", fontsize=9)

    # =========================================================================
    # Plot 3: Bar chart of intervening chunks by variable
    # =========================================================================
    ax3 = fig.add_subplot(gs[1, 1])

    # Sort by count
    sorted_vars = sorted(var_counts.items(), key=lambda x: -x[1]["count"])[:8]
    var_names = [v[0] for v in sorted_vars]
    counts = [v[1]["count"] for v in sorted_vars]
    bar_colors = [colors.get(v, colors["other"]) for v in var_names]

    bars = ax3.barh(range(len(var_names)), counts, color=bar_colors, edgecolor="white")
    ax3.set_yticks(range(len(var_names)))
    ax3.set_yticklabels(var_names)
    ax3.set_xlabel("Number of Chunks", fontsize=11)
    ax3.set_title(
        f"Other variables' chunks within HHHH selection's byte range\n"
        f"(Total: {len(other_chunks):,} chunks from {len(var_counts)} variables)",
        fontsize=12,
    )
    ax3.invert_yaxis()

    # Add count labels
    for bar, count in zip(bars, counts):
        ax3.text(
            bar.get_width() + 20,
            bar.get_y() + bar.get_height() / 2,
            f"{count:,}",
            va="center",
            fontsize=10,
        )

    # =========================================================================
    # Plot 4: Summary statistics box
    # =========================================================================
    ax4 = fig.add_subplot(gs[2, :])
    ax4.axis("off")

    # Build summary text with proper alignment
    summary_lines = [
        "INTERLEAVING ANALYSIS: Why selecting a spatial region highlights chunks from multiple variables",
        "",
        "Selection: HHHH variable, column 10 (dim_1=10, all rows)",
        "",
        f"  • Selected chunks:      {len(col_10_sorted):,}  (one per row in the array)",
        f"  • Actual data size:     {total_data/1e6:.1f} MB",
        f"  • Byte range span:      {byte_span/1e6:.0f} MB  (from {min_offset/1e6:.1f} MB to {max_offset/1e6:.1f} MB)",
        f"  • Read amplification:   {read_amp:.0f}×  (would read {read_amp:.0f}× more bytes than needed)",
        "",
        f"Within this {byte_span/1e6:.0f} MB span, there are {len(other_chunks):,} chunks from other variables interleaved.",
        "",
        "ROOT CAUSE: HDF5 writes chunks sequentially as data is generated, not grouped by variable.",
        "This is why cloud-native formats like Zarr (one chunk = one file) provide better random access.",
    ]
    summary_text = "\n".join(summary_lines)

    ax4.text(
        0.5,
        0.5,
        summary_text,
        transform=ax4.transAxes,
        fontsize=12,
        fontfamily="monospace",
        verticalalignment="center",
        horizontalalignment="center",
        bbox=dict(
            boxstyle="round,pad=0.8", facecolor="wheat", alpha=0.8, edgecolor="gray"
        ),
    )

    # =========================================================================
    # Final adjustments and save
    # =========================================================================
    fig.suptitle(
        "NISAR HDF5 Byte Range Interleaving Analysis",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_path}")
    plt.close()


def main():
    # Project root is parent of scripts/
    project_root = Path(__file__).parent.parent
    manifest_file = project_root / "data" / "nisar_manifest.json"

    if not manifest_file.exists():
        print(f"Manifest not found: {manifest_file}")
        return

    print("Loading manifest...")
    chunks = load_chunks(manifest_file)
    print(f"Loaded {len(chunks):,} chunks")

    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "interleaving_analysis.png"
    print("Creating visualization...")
    create_interleaving_figure(chunks, output_path)

    print(f"\nOutput saved to: {output_path}")


if __name__ == "__main__":
    main()
