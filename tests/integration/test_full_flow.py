"""Tool-to-tool integration test: synthesize -> run_place_route.

Drives the flagship flow entirely through the MCP tools — no side-channel
netlist building. This is the loop the README advertises.
"""

import os
from unittest.mock import patch

import pytest

from silica import oss_cad_suite
from silica.tools import place_route, synthesis

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("yosys") is None
        or oss_cad_suite.which("nextpnr-ice40") is None,
        reason="yosys or nextpnr-ice40 not installed",
    ),
]


class _Registry:
    """Minimal MCPServer stand-in that captures registered tool functions."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


@pytest.fixture
def tools():
    reg = _Registry()
    synthesis.register(reg)
    place_route.register(reg)
    return reg.tools


def test_synthesize_to_bitstream(tools, counter_v):
    # Empty config: no enabled-list restrictions from this machine's ~/.silica
    with patch("silica.config.load", return_value={}):
        synth = tools["synthesize"](
            top_module="counter", files=[counter_v], target="ice40", tool="yosys",
        )
        assert synth["exit_code"] == 0, synth["errors"]
        assert synth["netlist"] is not None
        assert os.path.exists(synth["netlist"])

        pnr = tools["run_place_route"](
            netlist=synth["netlist"], arch="ice40", device="hx8k", tool="nextpnr",
        )
        assert pnr["exit_code"] == 0, pnr["errors"]
        assert pnr["output"] is not None
        assert os.path.exists(pnr["output"])
        # icepack ships with OSS CAD Suite; without it the .asc is the output.
        packed = oss_cad_suite.which("icepack") is not None
        assert pnr["output"].endswith(".bin" if packed else ".asc")
