import sys

def main():
    print("FATAL ERROR: 'python run.py' wrapper is DEPRECATED and has been removed.", file=sys.stderr)
    print("Please use the canonical CLI entrypoint:", file=sys.stderr)
    print("  python -m app.cli.quarantine_cli", file=sys.stderr)
    print("Example:", file=sys.stderr)
    print("  python -m app.cli.quarantine_cli backfill <tenant_id>", file=sys.stderr)
    sys.exit(1)

if __name__ == '__main__':
    main()
