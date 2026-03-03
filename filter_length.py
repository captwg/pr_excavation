import sys
from Bio import SeqIO
import yaml

def filter_fasta(config_path):
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    min_len = config['filter']['min_length']
    input_file = config['paths']['input_fasta']
    output_file = config['paths']['filtered_fasta']
    
    count_before = 0
    count_after = 0
    
    with open(output_file, "w") as out_handle:
        for record in SeqIO.parse(input_file, "fasta"):
            count_before += 1
            if len(record.seq) >= min_len:
                SeqIO.write(record, out_handle, "fasta")
                count_after += 1
                
    print(f"Total: {count_before}")
    print(f"Kept (>= {min_len}aa): {count_after}")
    print(f"Removed: {count_before - count_after}")

if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    filter_fasta(config_file)
