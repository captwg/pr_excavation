import sys
from math import log
from Bio import AlignIO
import yaml

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

def split_domains(config_path):
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    alignment_file = config['paths']['alignment2']
    min_len = config['split']['min_domain_len']
    window = config['split']['window_size']
    out_prefix = "RuvC"

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

    best_i, best_j, best_val = None, None, None
    for i in range(min_len, ncol - 2 * min_len):
        for j in range(i + min_len, ncol - min_len):
            val = sm[i] + sm[j]
            if best_val is None or val < best_val:
                best_val, best_i, best_j = val, i, j

    if best_i is None:
        best_i, best_j = ncol // 3, 2 * ncol // 3

    domains = [(0, best_i), (best_i, best_j), (best_j, ncol)]
    names = ["I", "II", "III"]

    for name, (s, e) in zip(names, domains):
        sub = aln[:, s:e]
        out_path = f"{out_prefix}-{name}.aln"
        AlignIO.write(sub, out_path, "fasta")
        print(f"RuvC-{name}\t{s}\t{e}\t{e - s}")

if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    split_domains(config_file)
