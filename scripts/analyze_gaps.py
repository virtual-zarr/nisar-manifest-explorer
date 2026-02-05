#!/usr/bin/env python3
"""
Analyze gaps in the NISAR manifest to understand HDF5 file structure.

Usage:
    uv run scripts/analyze_gaps.py
"""

import ujson
from pathlib import Path
from collections import Counter

# HDF5 page size from h5stat
PAGE_SIZE = 4_194_304  # 4 MB


def main():
    manifest_file = Path(__file__).parent.parent / "data" / "nisar_manifest.json"

    with open(manifest_file) as f:
        kerchunk = ujson.load(f)

    refs = kerchunk["refs"]

    # Extract all chunk references (path, offset, length)
    chunks = []
    for key, value in refs.items():
        if isinstance(value, list) and len(value) == 3:
            path, offset, length = value
            chunks.append(
                {
                    "key": key,
                    "offset": offset,
                    "length": length,
                    "end": offset + length,
                }
            )

    if not chunks:
        print("No chunks found!")
        return

    # Sort by offset
    chunks.sort(key=lambda x: x["offset"])

    print(f"Total chunks: {len(chunks)}")
    print(f"First chunk offset: {chunks[0]['offset']:,}")
    print(f"Last chunk end: {chunks[-1]['end']:,}")
    print()

    # Analyze gaps
    gaps = []
    for i in range(1, len(chunks)):
        prev_end = chunks[i - 1]["end"]
        curr_start = chunks[i]["offset"]
        gap = curr_start - prev_end
        if gap > 0:
            gaps.append(
                {
                    "start": prev_end,
                    "end": curr_start,
                    "size": gap,
                    "after": chunks[i - 1]["key"],
                    "before": chunks[i]["key"],
                }
            )

    print(f"Total gaps: {len(gaps)}")
    total_gap_bytes = sum(g["size"] for g in gaps)
    print(f"Total gap bytes: {total_gap_bytes:,} ({total_gap_bytes / 1e6:.1f} MB)")
    print()

    # Gap size distribution
    print("Gap size distribution:")
    size_buckets = Counter()
    for g in gaps:
        if g["size"] < 1024:
            size_buckets["< 1 KB"] += 1
        elif g["size"] < 4096:
            size_buckets["1-4 KB"] += 1
        elif g["size"] < 65536:
            size_buckets["4-64 KB"] += 1
        elif g["size"] < 1_048_576:
            size_buckets["64 KB - 1 MB"] += 1
        elif g["size"] < PAGE_SIZE:
            size_buckets["1-4 MB"] += 1
        elif g["size"] < PAGE_SIZE * 2:
            size_buckets["4-8 MB (1-2 pages)"] += 1
        else:
            size_buckets[f"> 8 MB ({g['size'] // PAGE_SIZE} pages)"] += 1

    for bucket, count in sorted(size_buckets.items()):
        print(f"  {bucket}: {count}")
    print()

    # Check for page-aligned gaps
    print("Page alignment analysis (4 MB pages):")
    page_aligned_starts = sum(1 for g in gaps if g["start"] % PAGE_SIZE == 0)
    page_aligned_ends = sum(1 for g in gaps if g["end"] % PAGE_SIZE == 0)
    page_aligned_sizes = sum(1 for g in gaps if g["size"] % PAGE_SIZE == 0)

    print(f"  Gaps starting at page boundary: {page_aligned_starts}")
    print(f"  Gaps ending at page boundary: {page_aligned_ends}")
    print(f"  Gaps with page-multiple size: {page_aligned_sizes}")
    print()

    # Check chunk alignment
    print("Chunk alignment analysis:")
    chunk_page_aligned = sum(1 for c in chunks if c["offset"] % PAGE_SIZE == 0)
    chunk_4k_aligned = sum(1 for c in chunks if c["offset"] % 4096 == 0)
    chunk_512_aligned = sum(1 for c in chunks if c["offset"] % 512 == 0)

    print(f"  Chunks at 4 MB page boundary: {chunk_page_aligned} / {len(chunks)}")
    print(f"  Chunks at 4 KB boundary: {chunk_4k_aligned} / {len(chunks)}")
    print(f"  Chunks at 512 byte boundary: {chunk_512_aligned} / {len(chunks)}")
    print()

    # Largest gaps
    print("Top 10 largest gaps:")
    largest = sorted(gaps, key=lambda x: x["size"], reverse=True)[:10]
    for g in largest:
        pages = g["size"] / PAGE_SIZE
        print(f"  {g['size']:,} bytes ({pages:.2f} pages) at offset {g['start']:,}")
        print(f"    After: {g['after'][:60]}...")
        print(f"    Before: {g['before'][:60]}...")
    print()

    # Check if gaps correlate with metadata regions
    # The first ~5 MB typically contains file metadata
    metadata_region_end = 5_000_000
    gaps_in_metadata = [g for g in gaps if g["start"] < metadata_region_end]
    print(f"Gaps in first 5 MB (metadata region): {len(gaps_in_metadata)}")
    for g in gaps_in_metadata[:5]:
        print(f"  {g['start']:,} - {g['end']:,} ({g['size']:,} bytes)")


if __name__ == "__main__":
    main()
