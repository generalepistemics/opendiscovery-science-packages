"""
Ambient RNA Correction for Single-Cell RNA-seq Data

This module provides functions for removing ambient RNA contamination using
CellBender or SoupX-based approaches.

For detailed guidance, see references/ambient_rna_correction.md
"""

import scanpy as sc
import numpy as np
import pandas as pd
import subprocess
import os
from pathlib import Path
from typing import Union, Optional, Tuple
import warnings


def run_cellbender(
    raw_h5: Union[str, Path],
    expected_cells: int,
    total_droplets: Optional[int] = None,
    output_dir: Union[str, Path] = "results/cellbender",
    epochs: int = 200,
    fpr: float = 0.01,
    use_cuda: bool = True,
    **kwargs
) -> sc.AnnData:
    """
    Run CellBender remove-background to correct ambient RNA.

    CellBender uses a deep generative model to estimate and remove ambient RNA
    contamination from droplet-based scRNA-seq data.

    Parameters
    ----------
    raw_h5 : str or Path
        Path to raw_feature_bc_matrix.h5 file from CellRanger
    expected_cells : int
        Expected number of real cells in the dataset
    total_droplets : int, optional
        Total droplets to include (should be 2-3x expected_cells)
        If None, automatically set to 3x expected_cells
    output_dir : str or Path
        Directory to save CellBender outputs
    epochs : int
        Number of training epochs (default: 200)
    fpr : float
        False positive rate for cell calling (default: 0.01)
    use_cuda : bool
        Use GPU acceleration if available (default: True)
    **kwargs
        Additional arguments passed to cellbender remove-background

    Returns
    -------
    adata : AnnData
        Corrected count matrix as AnnData object

    Notes
    -----
    - Requires CellBender installation: pip install cellbender
    - GPU recommended for speed (10-20x faster than CPU)
    - For high-soup tissues (brain, lung, tumor), set total_droplets = 3x expected_cells
    """
    # Set up paths
    raw_h5 = Path(raw_h5)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if total_droplets is None:
        total_droplets = expected_cells * 3

    output_h5 = output_dir / "cellbender_output.h5"

    # Build command
    cmd = [
        "cellbender", "remove-background",
        "--input", str(raw_h5),
        "--output", str(output_h5),
        "--expected-cells", str(expected_cells),
        "--total-droplets-included", str(total_droplets),
        "--epochs", str(epochs),
        "--fpr", str(fpr)
    ]

    if use_cuda:
        cmd.append("--cuda")

    # Add any additional arguments
    for key, value in kwargs.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])

    print(f"Running CellBender with command:")
    print(" ".join(cmd))

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("CellBender completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"CellBender failed with error:\n{e.stderr}")
        raise

    # Load corrected counts
    adata = sc.read_10x_h5(str(output_h5).replace(".h5", "_filtered.h5"))
    adata.var_names_make_unique()

    # Store metadata
    adata.uns["cellbender"] = {
        "raw_h5": str(raw_h5),
        "expected_cells": expected_cells,
        "total_droplets": total_droplets,
        "epochs": epochs,
        "fpr": fpr
    }

    return adata


def run_soupx_python(
    raw_matrix_dir: Union[str, Path],
    filtered_matrix_dir: Union[str, Path],
    clusters: Optional[np.ndarray] = None,
    output_dir: Union[str, Path] = "results/soupx"
) -> sc.AnnData:
    """Run the official R SoupX implementation from a Python workflow.

    Requires Rscript, SoupX and Matrix on the selected engine host. Counts
    remain raw during estimation. No correlation heuristic substitutes for SoupX.
    """
    import tempfile
    from scipy.io import mmread

    raw_matrix_dir = Path(raw_matrix_dir).resolve(strict=True)
    filtered_matrix_dir = Path(filtered_matrix_dir).resolve(strict=True)
    adata = sc.read_10x_mtx(filtered_matrix_dir, var_names="gene_ids", make_unique=False)
    if clusters is None:
        clustered = adata.copy()
        sc.pp.normalize_total(clustered, target_sum=1e4)
        sc.pp.log1p(clustered)
        sc.pp.pca(clustered)
        sc.pp.neighbors(clustered)
        sc.tl.leiden(clustered)
        clusters = clustered.obs["leiden"].to_numpy()
    if len(clusters) != adata.n_obs or pd.isna(clusters).any():
        raise ValueError("Provide one nonmissing cluster per filtered cell")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="soupx-") as temporary:
        temporary = Path(temporary)
        pd.DataFrame({"barcode": adata.obs_names, "cluster": clusters}).to_csv(
            temporary / "clusters.csv", index=False)
        subprocess.run([
            "Rscript", str(Path(__file__).with_name("run_soupx.R")),
            str(raw_matrix_dir), str(filtered_matrix_dir), str(temporary),
        ], check=True)
        corrected = mmread(temporary / "corrected.mtx").tocsr().T.tocsr()
        genes = (temporary / "genes.txt").read_text().splitlines()
        cells = (temporary / "barcodes.txt").read_text().splitlines()
        if genes != list(adata.var_names) or cells != list(adata.obs_names) or corrected.shape != adata.shape:
            raise ValueError("SoupX output identities differ from the filtered matrix")
        contamination = pd.read_csv(temporary / "contamination.csv")["rho"].to_numpy()
    adata.X = corrected
    adata.uns["soupx"] = {"contamination_fraction": float(np.mean(contamination)),
                          "implementation": "R SoupX autoEstCont/adjustCounts"}
    adata.obs["soupx_contamination"] = contamination
    adata.write_h5ad(output_dir / "soupx_corrected.h5ad")
    return adata


def estimate_contamination(adata: sc.AnnData) -> float:
    """
    Estimate ambient RNA contamination fraction from corrected AnnData.

    Parameters
    ----------
    adata : AnnData
        AnnData object with ambient correction metadata

    Returns
    -------
    contamination : float
        Estimated contamination fraction
    """
    if "soupx" in adata.uns:
        return float(adata.uns["soupx"]["contamination_fraction"])
    raise ValueError("No measured contamination fraction is available. CellBender metadata alone does not establish a contamination percentage.")


def compare_before_after(
    adata_before: sc.AnnData,
    adata_after: sc.AnnData,
    marker_genes: list,
    output_dir: Union[str, Path] = "results/ambient"
):
    """
    Compare expression before and after ambient RNA correction.

    Parameters
    ----------
    adata_before : AnnData
        Data before correction
    adata_after : AnnData
        Data after correction
    marker_genes : list
        List of marker genes to compare
    output_dir : str or Path
        Directory to save comparison plots
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compare total counts
    before_counts = adata_before.X.sum(axis=1).A1
    after_counts = adata_after.X.sum(axis=1).A1

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(before_counts, after_counts, alpha=0.3, s=0.5, edgecolors='none')
    ax.set_xlabel("Before Correction")
    ax.set_ylabel("After Correction")
    ax.set_title("Total Counts Before vs After Correction", fontweight='bold')
    sns.despine(ax=ax)

    fig.tight_layout()
    fig.savefig(output_dir / "counts_comparison.png", dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / "counts_comparison.svg", dpi=300, bbox_inches='tight')
    plt.close(fig)

    print(f"Mean counts before: {before_counts.mean():.1f}")
    print(f"Mean counts after: {after_counts.mean():.1f}")
    print(f"Reduction: {(1 - after_counts.mean()/before_counts.mean()) * 100:.1f}%")


# Example usage
if __name__ == "__main__":
    # Example: Run CellBender
    adata = run_cellbender(
        raw_h5="raw_feature_bc_matrix.h5",
        expected_cells=10000,
        output_dir="results/cellbender"
    )

    print(f"Loaded corrected data: {adata.shape[0]} cells, {adata.shape[1]} genes")
