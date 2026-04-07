import argparse

from .crew import run_crew


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stockify multi-agent analysis")
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Ticker symbols to analyze, for example AAPL MSFT NVDA",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_crew(args.symbols)
    print(report)


if __name__ == "__main__":
    main()
