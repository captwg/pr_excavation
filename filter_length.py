import sys

def filter_fasta(input_fasta, output_fasta, min_len):
    count_before = 0
    count_after = 0
    with open(input_fasta, "r") as in_f, open(output_fasta, "w") as out_f:
        header = None
        sequence = []
        for line in in_f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header:
                    count_before += 1
                    seq_str = "".join(sequence)
                    if len(seq_str) >= min_len:
                        out_f.write(f"{header}\n{seq_str}\n")
                        count_after += 1
                header = line
                sequence = []
            else:
                sequence.append(line)
        # Handle the last record
        if header:
            count_before += 1
            seq_str = "".join(sequence)
            if len(seq_str) >= min_len:
                out_f.write(f"{header}\n{seq_str}\n")
                count_after += 1
    
    print(f"Total sequences before filtering: {count_before}")
    print(f"Total sequences after filtering (length >= {min_len}): {count_after}")
    print(f"Removed sequences: {count_before - count_after}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python filter_length.py <input.fasta> <output.fasta> <min_len>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    min_length = int(sys.argv[3])
    filter_fasta(input_file, output_file, min_length)
