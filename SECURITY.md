# Security Policy

## Supported versions

Only the latest release on [PyPI](https://pypi.org/project/silica-eda/) receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/simaanc/silica-eda/security/advisories/new),
not in a public issue.

Include the silica-eda version, your OS, the MCP tool involved, and the
smallest input that reproduces the problem. You should get a reply within a
week. Once a fix is released, the advisory is published with credit to you,
unless you'd rather stay anonymous.

## Scope

silica is an MCP server that an AI agent drives: it runs EDA tools and reads
and writes files on the machine it runs on. Treat these as vulnerabilities:

- A file tool that reads, lists or writes outside the project root
  (`read_rtl`, `write_rtl`, `format_rtl`, `get_constraints`, `search_rtl` and
  `get_project_structure` are confined to it).
- Command or script injection through a tool argument, such as a file path or
  top-module name that ends up executed in a generated Yosys, sby or eqy
  script, or on a command line.
- A tool enabled or invoked despite being disabled in `~/.silica/config.toml`.

Out of scope: bugs in the EDA tools themselves (report those upstream), and
anything that requires the agent to already have arbitrary shell access.
