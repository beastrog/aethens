import sys


def main() -> None:
    for line in sys.stdin:
        print(sum(int(tok) for tok in line.split()))


if __name__ == "__main__":
    main()
    sys.exit(0)
