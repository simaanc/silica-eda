import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="silica",
        description="Silica — AI-native EDA environment",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="Start the MCP server (stdio transport)")

    args = parser.parse_args()

    if args.command == "serve":
        from silica.server import mcp
        mcp.run()
    else:
        parser.print_help()
        sys.exit(1)
