import yaml
import subprocess
import os

def run_command(cmd):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    p = config['paths']
    c = config['cluster']
    m = config['mafft']
    
    # 1. Filter Length
    run_command("python filter_length.py config.yaml")
    
    # 2. Initial Alignment
    run_command(f"mafft --retree 1 --maxiterate 0 --thread {m['threads']} {p['filtered_fasta']} > {p['alignment1']}")
    
    # 3. Clustering
    if not os.path.exists("tmp"): os.makedirs("tmp")
    run_command(f"mmseqs easy-cluster {p['filtered_fasta']} {p['cluster_out']} tmp "
                f"--min-seq-id {c['min_seq_id']} -c {c['coverage']} --cov-mode {c['cov_mode']}")
    
    # Sync MMSeqs2 output names to match config
    if os.path.exists(f"{p['cluster_out']}_cluster.tsv"):
        os.rename(f"{p['cluster_out']}_cluster.tsv", "cluster.tsv")
    if os.path.exists(f"{p['cluster_out']}_rep_seq.fasta"):
        os.rename(f"{p['cluster_out']}_rep_seq.fasta", p['representative_fasta'])
        
    # 4. High-precision Alignment
    run_command(f"mafft --genafpair --maxiterate {m['max_iterate']} --ep {m['ep']} --thread {m['threads']} "
                f"{p['representative_fasta']} > {p['alignment2']}")
    
    # 5. Split Domains
    run_command("python split_domains.py config.yaml")
    
    # 6. HHM Profile
    for domain in ["I", "II", "III"]:
        run_command(f"hhmake -i RuvC-{domain}.aln -o RuvC-{domain}.hhm")

if __name__ == "__main__":
    main()
