#!/usr/bin/env python3
"""Entry point to launch the DEC-MAPF simulation workspace."""

import uvicorn
from mapf.gui.app import app

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("   DEC-MAPF Simulation Workspace")
    print("   URL: http://localhost:8000")
    print("   Decentralized MAPF and centralized solver comparisons")
    print("=" * 65 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
