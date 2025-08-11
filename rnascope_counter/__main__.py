import argparse
from .app import run_app


def main():
    parser = argparse.ArgumentParser(description="RNAScope counter application")
    parser.add_argument("--hippocampus", required=True, help="Path to hippocampus montage TIFF")
    parser.add_argument("--thalamus", required=True, help="Path to thalamus montage TIFF")
    parser.add_argument("--output", default="rnascope_results.csv", help="Path to output CSV file")
    args = parser.parse_args()
    run_app(args.hippocampus, args.thalamus, args.output)


if __name__ == "__main__":
    main()
