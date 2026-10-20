import sys

_USAGE = """\
Usage: silica [serve|setup|config]

  serve     Start the MCP server on stdio (the default). MCP clients run this;
            it waits for MCP messages on stdin.
  setup     Interactive wizard that adds silica to your MCP clients.
  config    Show the configuration and which EDA tools are detected.

Options:
  -h, --help     Show this help and exit.
  -V, --version  Show silica's version and exit.

`silica-eda` is the same command, so `uvx silica-eda@latest setup` works too.
Docs: https://github.com/simaanc/silica-eda"""


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
    elif cmd in ("-h", "--help", "help"):
        print(_USAGE)
    elif cmd in ("-V", "--version", "version"):
        from silica import __version__
        print(f"silica-eda {__version__}")
    else:
        # stderr: a client that passes a wrong argument reads stdout as MCP.
        print(f"silica: unknown command '{cmd}'", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        sys.exit(1)
