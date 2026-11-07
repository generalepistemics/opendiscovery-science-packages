#!/usr/bin/env python3
"""
Pocket druggability assessment.

Scores detected pockets for drug-likeness using a 6-axis weighted model:
volume, hydrophobicity, enclosure, depth, H-bond capacity, aromaticity.

Usage:
    python druggability.py --input protein.pdb --pockets pockets.json --output druggability.json
"""

import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

try:
    from Bio.PDB import PDBParser, NeighborSearch
except ImportError:
    sys.exit("ERROR: BioPython is required. Install with: pip install biopython")

try:
    import numpy as np
except ImportError:
    sys.exit("ERROR: NumPy is required. Install with: pip install numpy")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STANDARD_RESIDUES = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HID", "HIE", "HIP", "CYX", "ASH", "GLH",
}

WATER_RESIDUES = {"HOH", "WAT", "TIP", "TIP3", "SOL", "H2O"}

# Amino acid property categories
HYDROPHOBIC_RESIDUES = {"ALA", "VAL", "ILE", "LEU", "MET", "PHE", "TRP", "PRO"}
POLAR_RESIDUES = {"SER", "THR", "ASN", "GLN", "CYS", "TYR", "HIS"}
CHARGED_RESIDUES = {"ASP", "GLU", "LYS", "ARG"}
AROMATIC_RESIDUES = {"PHE", "TYR", "TRP", "HIS"}
HBOND_RESIDUES = {"SER", "THR", "ASN", "GLN", "ASP", "GLU", "LYS", "ARG",
                  "HIS", "TYR", "CYS", "TRP"}

# Scoring weights (from chem_agent.md design spec)
WEIGHTS = {
    "volume": 0.25,
    "hydrophobicity": 0.20,
    "enclosure": 0.25,
    "depth": 0.15,
    "hb_capacity": 0.10,
    "aromaticity": 0.05,
}

# 26 unit direction vectors (cube faces + edges + corners)
DIRECTION_VECTORS = []
for dx in (-1, 0, 1):
    for dy in (-1, 0, 1):
        for dz in (-1, 0, 1):
            if dx == 0 and dy == 0 and dz == 0:
                continue
            v = np.array([dx, dy, dz], dtype=float)
            DIRECTION_VECTORS.append(v / np.linalg.norm(v))


# ---------------------------------------------------------------------------
# Pocket property computation
# ---------------------------------------------------------------------------


def _get_pocket_residues(structure, center, radius=8.0, chain_id=None):
    """Get actual residue objects near a pocket center."""
    atoms = []
    for model in structure:
        for chain in model:
            if chain_id and chain.get_id() != chain_id:
                continue
            for residue in chain:
                resname = residue.get_resname().strip()
                if resname in WATER_RESIDUES:
                    continue
                if resname not in STANDARD_RESIDUES:
                    continue
                for atom in residue:
                    atoms.append(atom)
        break

    if not atoms:
        return []

    ns = NeighborSearch(atoms)
    center_arr = np.array(center, dtype=float)
    nearby = ns.search(center_arr, radius, level="R")
    return [r for r in nearby if r.get_resname().strip() in STANDARD_RESIDUES]


def compute_hydrophobicity(residues):
    """Fraction of pocket residues that are hydrophobic (0.0 - 1.0)."""
    if not residues:
        return 0.0
    n_hydrophobic = sum(
        1 for r in residues
        if r.get_resname().strip() in HYDROPHOBIC_RESIDUES
    )
    return n_hydrophobic / len(residues)


def compute_enclosure(structure, center, probe_distance=10.0, chain_id=None):
    """
    Measure pocket enclosure by casting 26 directional rays from the center
    and checking what fraction hit protein atoms within probe_distance.

    Returns fraction (0.0 - 1.0). Higher = more enclosed.
    """
    atoms = []
    for model in structure:
        for chain in model:
            if chain_id and chain.get_id() != chain_id:
                continue
            for residue in chain:
                resname = residue.get_resname().strip()
                if resname in WATER_RESIDUES:
                    continue
                for atom in residue:
                    atoms.append(atom)
        break

    if not atoms:
        return 0.0

    ns = NeighborSearch(atoms)
    center_arr = np.array(center, dtype=float)

    hits = 0
    for direction in DIRECTION_VECTORS:
        # Sample along the ray at intervals
        for dist in np.arange(2.0, probe_distance, 1.0):
            probe_point = center_arr + direction * dist
            nearby = ns.search(probe_point, 2.5, level="A")
            if nearby:
                hits += 1
                break

    return hits / len(DIRECTION_VECTORS)


def compute_hb_capacity(residues):
    """Count residues capable of hydrogen bonding."""
    return sum(
        1 for r in residues
        if r.get_resname().strip() in HBOND_RESIDUES
    )


def compute_aromaticity(residues):
    """Count aromatic residues in the pocket."""
    return sum(
        1 for r in residues
        if r.get_resname().strip() in AROMATIC_RESIDUES
    )


# ---------------------------------------------------------------------------
# Scoring functions (piecewise linear from design spec)
# ---------------------------------------------------------------------------


def score_volume(volume):
    """Score pocket volume. Optimal: 300-800 A^3."""
    if 300 <= volume <= 800:
        return 1.0
    if 150 <= volume < 300:
        return 0.5 + 0.5 * (volume - 150) / 150
    if 800 < volume <= 1500:
        return 0.5 + 0.5 * (1500 - volume) / 700
    if volume < 150:
        return 0.2 * (volume / 150)
    # > 1500
    return max(0.1, 0.2 * (2000 - volume) / 500) if volume < 2000 else 0.1


def score_hydrophobicity(hydro):
    """Score hydrophobicity fraction. Optimal: 0.3-0.7."""
    if 0.3 <= hydro <= 0.7:
        return 1.0
    if 0.2 <= hydro < 0.3:
        return 0.5 + 0.5 * (hydro - 0.2) / 0.1
    if 0.7 < hydro <= 0.8:
        return 0.5 + 0.5 * (0.8 - hydro) / 0.1
    return 0.2


def score_enclosure(enclosure):
    """Score pocket enclosure. Optimal: >0.5."""
    if enclosure > 0.5:
        return 1.0
    if 0.3 <= enclosure <= 0.5:
        return 0.5 + 0.5 * (enclosure - 0.3) / 0.2
    return 0.2 * (enclosure / 0.3) if enclosure > 0 else 0.0


def score_depth(depth):
    """Score pocket depth. Optimal: >5 A."""
    if depth > 5.0:
        return 1.0
    if 3.0 <= depth <= 5.0:
        return 0.5 + 0.5 * (depth - 3.0) / 2.0
    return 0.2 * (depth / 3.0) if depth > 0 else 0.0


def score_hb_capacity(n_hb):
    """Score H-bond capacity. Optimal: 2-8."""
    if 2 <= n_hb <= 8:
        return 1.0
    if n_hb == 1:
        return 0.5
    if 9 <= n_hb <= 12:
        return 0.5
    if n_hb == 0 or n_hb > 12:
        return 0.2


def score_aromaticity(n_aromatic):
    """Score aromatic residue count. Optimal: >=2."""
    if n_aromatic >= 2:
        return 1.0
    if n_aromatic == 1:
        return 0.5
    return 0.2


def classify_druggability(score):
    """Classify pocket druggability from composite score."""
    if score > 0.7:
        return "druggable"
    if score >= 0.4:
        return "difficult"
    return "undruggable"


# ---------------------------------------------------------------------------
# Main assessment pipeline
# ---------------------------------------------------------------------------


def assess_druggability(input_pdb, pockets_json, output_path, chain_id=None):
    """
    Score all pockets in the input JSON for druggability.

    Augments each pocket with druggability_score, druggability_class,
    and a properties dict.
    """
    print("=" * 60)
    print("DRUGGABILITY ASSESSMENT")
    print("=" * 60)
    print(f"Protein: {input_pdb}")
    print(f"Pockets: {pockets_json}")
    print()

    # Load pocket data
    with open(pockets_json) as f:
        data = json.load(f)

    pockets = data.get("pockets", [])
    if not pockets:
        print("No pockets to assess.")
        data["pockets"] = []
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        return

    # Parse protein structure
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("protein", input_pdb)

    for pocket in pockets:
        center = pocket["center"]
        volume = pocket.get("volume_A3", 0)
        depth = pocket.get("depth_A", 0)

        # Get residues near pocket center
        residues = _get_pocket_residues(
            structure, center, radius=8.0, chain_id=chain_id
        )

        # Compute properties
        hydrophobicity = compute_hydrophobicity(residues)
        enclosure = compute_enclosure(structure, center, chain_id=chain_id)
        hb_capacity = compute_hb_capacity(residues)
        aromaticity = compute_aromaticity(residues)

        # If volume/depth not from detection, estimate from residues
        if volume == 0 and residues:
            res_coords = []
            for r in residues:
                for a in r:
                    res_coords.append(a.get_vector().get_array())
            if len(res_coords) >= 4:
                try:
                    from scipy.spatial import ConvexHull
                    hull = ConvexHull(np.array(res_coords))
                    volume = hull.volume * 0.3  # rough pocket fraction
                except Exception:
                    volume = len(residues) * 30  # rough estimate

        if depth == 0 and residues:
            center_arr = np.array(center)
            dists = [
                np.linalg.norm(
                    np.array(a.get_vector().get_array()) - center_arr
                )
                for r in residues for a in r
            ]
            depth = max(dists) if dists else 0

        # Score each axis
        scores = {
            "volume": score_volume(volume),
            "hydrophobicity": score_hydrophobicity(hydrophobicity),
            "enclosure": score_enclosure(enclosure),
            "depth": score_depth(depth),
            "hb_capacity": score_hb_capacity(hb_capacity),
            "aromaticity": score_aromaticity(aromaticity),
        }

        # Weighted composite
        composite = sum(
            WEIGHTS[k] * scores[k] for k in WEIGHTS
        )

        # Augment pocket data
        pocket["druggability_score"] = round(composite, 2)
        pocket["druggability_class"] = classify_druggability(composite)
        pocket["properties"] = {
            "volume_A3": round(volume, 1),
            "hydrophobicity": round(hydrophobicity, 2),
            "enclosure": round(enclosure, 2),
            "depth_A": round(depth, 1),
            "hb_capacity": hb_capacity,
            "aromaticity": aromaticity,
        }
        pocket["property_scores"] = {k: round(v, 2) for k, v in scores.items()}

        # Print summary
        cls = pocket["druggability_class"]
        print(f"  Pocket {pocket['rank']} — {cls} (score: {composite:.2f})")
        print(f"    Volume: {volume:.0f} A^3 (score: {scores['volume']:.2f})")
        print(f"    Hydrophobicity: {hydrophobicity:.2f} (score: {scores['hydrophobicity']:.2f})")
        print(f"    Enclosure: {enclosure:.2f} (score: {scores['enclosure']:.2f})")
        print(f"    Depth: {depth:.1f} A (score: {scores['depth']:.2f})")
        print(f"    H-bond capacity: {hb_capacity} (score: {scores['hb_capacity']:.2f})")
        print(f"    Aromaticity: {aromaticity} (score: {scores['aromaticity']:.2f})")
        print()

    # Write output
    print("NOTE: Druggability classification is heuristic (literature thresholds),")
    print("not a validated predictor. Use for prioritization guidance only.")
    print()

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Druggability data saved to: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Assess pocket druggability using a 6-axis weighted model. "
                    "Scores volume, hydrophobicity, enclosure, depth, "
                    "H-bond capacity, and aromaticity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python druggability.py --input protein.pdb --pockets pockets.json --output druggability.json
  python druggability.py --input protein.pdb --pockets pockets.json --output druggability.json --chain A
        """,
    )
    parser.add_argument("--input", required=True, help="Input PDB file")
    parser.add_argument("--pockets", required=True, help="Pockets JSON from detect.py")
    parser.add_argument("--output", required=True, help="Output druggability JSON")
    parser.add_argument("--chain", default=None, help="Chain ID (optional)")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"ERROR: PDB file not found: {args.input}")
    if not os.path.exists(args.pockets):
        sys.exit(f"ERROR: Pockets file not found: {args.pockets}")

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    assess_druggability(args.input, args.pockets, args.output, args.chain)


if __name__ == "__main__":
    main()
