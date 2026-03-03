import sys
from math import log
from Bio import AlignIO


def entropy(column):
    counts = {}
    total = 0
    for c in column:
        if c == '-' or c == '.':
            continue
        counts[c] = counts.get(c, 0) + 1
        total += 1
    if total == 0:
        return 0.0
    ent = 0.0
    for v in counts.values():
        p = v / total
        ent -= p * log(p + 1e-12)
    return ent


def smooth(values, window):
    n = len(values)
    half = window // 2
    out = [0.0] * n
    for i in range(n):
        s = 0.0
        c = 0
        start = max(0, i - half)
        end = min(n, i + half + 1)
        for j in range(start, end):
            s += values[j]
            c += 1
        out[i] = s / c
    return out


def split_domains(alignment_file, out_prefix, min_len=60, window=15):
    aln = AlignIO.read(alignment_file, "fasta")
    nseq = len(aln)
    ncol = aln.get_alignment_length()

    gap_frac = []
    ent = []
    for i in range(ncol):
        col = aln[:, i]
        gaps = col.count('-') + col.count('.')
        gap_frac.append(gaps / nseq)
        ent.append(entropy(col))

    max_ent = max(ent) if max(ent) > 0 else 1.0
    score = []
    for i in range(ncol):
        cons = 1.0 - (ent[i] / max_ent)
        score.append((1.0 - gap_frac[i]) * cons)

    sm = smooth(score, window)

    best_i = None
    best_j = None
    best_val = None
    for i in range(min_len, ncol - 2 * min_len):
        for j in range(i + min_len, ncol - min_len):
            val = sm[i] + sm[j]
            if best_val is None or val < best_val:
                best_val = val
                best_i = i
                best_j = j

    if best_i is None or best_j is None:
        best_i = ncol // 3
        best_j = 2 * ncol // 3

    domains = [(0, best_i), (best_i, best_j), (best_j, ncol)]
    names = ["RuvC-I", "RuvC-II", "RuvC-III"]

    for name, (s, e) in zip(names, domains):
        sub = aln[:, s:e]
        out_path = f"{out_prefix}_{name}.aln"
        AlignIO.write(sub, out_path, "fasta")
        print(f"{name}\t{s}\t{e}\t{e - s}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python split_domains.py <alignment2.aln> <output_prefix>")
        sys.exit(1)
    split_domains(sys.argv[1], sys.argv[2])
