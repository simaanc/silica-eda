import sys


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if cmd == "serve":
        from silica.server import mcp
        mcp.run()
    elif cmd == "setup":
        from silica.setup import main as setup_main
        setup_main()
    elif cmd == "config":
        from silica.setup import print_config
        print_config()
    else:
        print(f"silica: unknown command '{cmd}'")
        print("Usage: silica [serve|setup|config]")
        sys.exit(1)
