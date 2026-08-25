"""Local JLCPCB-oriented DFM preflight for KiCadRoutingTools."""

from .checker import check_bom_cpl, check_pcb
from .model import DfmReport, Finding
from .standards import JlcFr4Profile, make_jlc_fr4_profile

__all__ = [
    "DfmReport", "Finding", "JlcFr4Profile", "check_bom_cpl", "check_pcb",
    "make_jlc_fr4_profile",
]
