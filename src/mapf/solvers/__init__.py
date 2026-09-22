"""Unified MAPF Solvers package: Centralized (CBS, Prioritized), Decentralized Negotiation, and Registry."""

from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.binary_runner import BaseBinarySolver, ExternalBinarySolver
from mapf.solvers.cbs import CentralizedCBSSolver
from mapf.solvers.decentralized import DecentralizedNegotiationSolver
from mapf.solvers.eecbs import CentralizedEECBSSolver
from mapf.solvers.prioritized import CentralizedPrioritizedSolver
from mapf.solvers.registry import get_solver, list_solvers, register_solver

__all__ = [
    "BaseBinarySolver",
    "CentralizedCBSSolver",
    "CentralizedEECBSSolver",
    "CentralizedPrioritizedSolver",
    "DecentralizedNegotiationSolver",
    "ExternalBinarySolver",
    "MAPFInstance",
    "MAPFSolution",
    "MAPFSolverProtocol",
    "get_solver",
    "list_solvers",
    "register_solver",
]
