"""Bounded in-silico PCR and local BLAST+ screening of primer pairs.

Results describe the supplied sequence/database and search parameters, not
experimental specificity or a guarantee that every genomic site was found.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path
import re
import subprocess
import tempfile


def _primer(value):
    value = value.upper().strip()
    if not re.fullmatch(r'[ACGT]{4,100}', value):
        raise ValueError('Provide an unambiguous A/C/G/T primer of 4–100 bases')
    return value


def _reverse_complement(sequence):
    return sequence.translate(str.maketrans('ACGT', 'TGCA'))[::-1]


def _sites(primer, sequence, max_mismatches):
    for start in range(len(sequence) - len(primer) + 1):
        mismatches = sum(a != b for a, b in zip(primer, sequence[start:start + len(primer)]))
        if mismatches <= max_mismatches:
            yield start, start + len(primer), mismatches


def in_silico_pcr(forward_primer, reverse_primer, sequence,
                  max_product_size=5000, max_mismatches=2):
    """Return inward-facing, ungapped products on both reference strands.

    Coordinates are zero-based, half-open in the supplied forward reference.
    Ambiguous reference bases count as mismatches. No external data is fetched.
    """
    forward, reverse = _primer(forward_primer), _primer(reverse_primer)
    sequence = sequence.upper().strip()
    if not sequence or len(sequence) > 1_000_000 or not re.fullmatch(r'[ACGTN]+', sequence):
        raise ValueError('Provide 1–1,000,000 A/C/G/T/N reference bases')
    if max_product_size < max(len(forward), len(reverse)) or not 0 <= max_mismatches < min(len(forward), len(reverse)):
        raise ValueError('Invalid product-size or mismatch bound')
    products = []
    for strand, left, right in [('+', forward, _reverse_complement(reverse)),
                                ('-', reverse, _reverse_complement(forward))]:
        right_sites = list(_sites(right, sequence, max_mismatches))
        right_starts = [site[0] for site in right_sites]
        for left_start, left_end, left_mismatches in _sites(left, sequence, max_mismatches):
            lo = bisect_left(right_starts, left_end)
            hi = bisect_right(right_starts, left_start + max_product_size - len(right))
            for right_start, right_end, right_mismatches in right_sites[lo:hi]:
                if left_end <= right_start and right_end - left_start <= max_product_size:
                    products.append({'forward_start': left_start if strand == '+' else right_start,
                                     'reverse_start': right_end if strand == '+' else left_end,
                                     'start': left_start, 'end': right_end, 'strand': strand,
                                     'product_size': right_end - left_start,
                                     'mismatches': left_mismatches + right_mismatches,
                                     'sequence': sequence[left_start:right_end] if strand == '+'
                                     else _reverse_complement(sequence[left_start:right_end])})
                    if len(products) > 10_000:
                        raise ValueError('Too many candidate products; narrow the reference or mismatch bound')
    return products


def check_specificity_local_blast(forward_primer, reverse_primer, blast_db_path,
                                  max_mismatches=3, max_product_size=5000,
                                  max_targets=100, expected_subject=None):
    """Screen full-length, ungapped BLAST+ hits and pair inward-facing sites.

    BLAST is a heuristic search capped by max_targets. is_specific remains
    unknown without an explicit expected subject; it is never an assay claim.
    Requires a user-selected BLAST database on the engine host.
    """
    forward, reverse = _primer(forward_primer), _primer(reverse_primer)
    if not blast_db_path or not 0 <= max_mismatches < min(len(forward), len(reverse)):
        raise ValueError('Provide a database path and valid mismatch bound')
    if not 1 <= max_targets <= 10_000 or max_product_size < max(len(forward), len(reverse)):
        raise ValueError('Invalid search bounds')
    with tempfile.TemporaryDirectory(prefix='primer-screen-') as temporary:
        query = Path(temporary) / 'primers.fasta'
        query.write_text(f'>forward\n{forward}\n>reverse\n{reverse}\n')
        result = subprocess.run([
            'blastn', '-query', str(query), '-db', str(blast_db_path),
            '-task', 'blastn-short', '-dust', 'no', '-max_target_seqs', str(max_targets),
            '-outfmt', '6 qseqid sseqid qstart qend sstart send length mismatch gaps qlen',
        ], check=True, capture_output=True, text=True, timeout=300)
    hits = defaultdict(lambda: defaultdict(list))
    for line in result.stdout.splitlines():
        fields = line.split('\t')
        if len(fields) != 10:
            raise ValueError('Unexpected BLAST tabular output')
        primer, subject = fields[:2]
        qs, qe, ss, se, length, mismatches, gaps, qlen = map(int, fields[2:])
        if primer not in ['forward', 'reverse'] or qs != 1 or qe != qlen or length != qlen or gaps or mismatches > max_mismatches:
            continue
        hits[subject][primer].append((ss, se, mismatches))
    products = []
    for subject, primers in hits.items():
        for fs, fe, fm in primers['forward']:
            for rs, re_, rm in primers['reverse']:
                inward = (fs < fe < re_ < rs) or (rs < re_ < fe < fs)
                start, end = min(fs, fe, rs, re_), max(fs, fe, rs, re_)
                if inward and end - start + 1 <= max_product_size:
                    product = {'template': subject, 'start': start - 1, 'end': end,
                               'strand': '+' if fs < fe else '-', 'product_length': end - start + 1,
                               'mismatches': fm + rm}
                    if product not in products:
                        products.append(product)
    return {'validation_method': 'local_blast', 'is_specific': None if expected_subject is None else
            len(products) == 1 and products[0]['template'] == expected_subject,
            'num_products': len(products), 'products': products,
            'database': str(blast_db_path), 'max_targets': max_targets,
            'max_mismatches': max_mismatches, 'max_product_size': max_product_size,
            'scope': 'Full-length ungapped hits returned by this bounded heuristic search; not experimental validation'}


def check_primer_specificity(forward_primer, reverse_primer, organism,
                             database='refseq_representative_genomes', max_targets=10,
                             primer_specificity_database=None):
    """Screen the explicitly provided local database; never manufacture web results."""
    if not primer_specificity_database:
        raise ValueError('Provide primer_specificity_database as a local BLAST+ database path. '
                         'For NCBI Primer-BLAST, submit the pair through its official web interface and retain the returned results.')
    return check_specificity_local_blast(forward_primer, reverse_primer,
                                         primer_specificity_database, max_targets=max_targets)
