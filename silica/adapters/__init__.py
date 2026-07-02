"""Tool adapters — one module per EDA tool.

Adapter conventions:

- Detection goes through ``silica.detect.resolve`` (registry name → binary),
  or ``oss_cad_suite.which`` for suite-internal helper binaries (vvp, solvers,
  verilator_bin) that have no registry entry.
- ``subprocess.run`` env handling: adapters for tools bundled in the OSS CAD
  Suite must pass ``env=oss_cad_suite.env_with_suite()`` so the suite's PATH
  and support files are visible. Commercial-tool adapters (vcs, questa,
  xcelium, vivado, quartus, dc_shell, jaspergold, vc_formal, spyglass, verdi)
  and standalone linters (verible, svlint) deliberately pass no ``env`` —
  those tools are never shipped in the suite and inherit the caller's
  environment unchanged.
- Values interpolated into generated scripts must be vetted with
  ``_script_paths.unsafe_script_value`` first.
"""
