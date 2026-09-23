# Alpha status and scientific scope

**DEC-MAPF is an alpha simulation and experimentation framework for Decentralized Multi-Agent Path Finding.** It combines decentralized methods and centralized comparators with shared scenario inputs, headless experiment management, independent solution validation and an optional local GUI. Researchers can run the examples, supply their own scenarios, compare methods and extend the framework through documented interfaces.

## Start with a complete workflow

- Run the [eight-trial headless comparison](HEADLESS.md) or follow the [GUI walkthrough](GUI-GUIDE.md) from configuration through validation, replay and export.
- Inspect [solved examples from the article settings](GALLERY.md): 16×16 with 80 agents and 32×32 with approximately 20% obstacles and 80 agents.
- Use the [public Python API](PUBLIC-API.md), [extension contracts](EXTENDING.md) and [contribution checks](../CONTRIBUTING.md) to develop a change.
- Interpret outputs with the [scientific assumptions](SCIENCE.md), [metric definitions](METRICS.md) and [experiment workflow](EXPERIMENTS.md).

## Included methods and extension scope

HeatMap and PathAware implement the current token-based negotiation approach. CBS and Prioritized Planning provide built-in centralized methods; native EECBS/CBSH2-RTC adapters are optional. The shared solver contract supports additional method implementations. Auction-based and other coordination protocols require their own solver logic and any additional configuration, capability or telemetry integration described in [Extending](EXTENDING.md).

## Identity and compatibility

| Name or version | Meaning |
| --- | --- |
| `DEC-MAPF` | Repository and documentation name |
| `dec-mapf`, version `0.1.0a2` | Python distribution and current alpha version |
| `0.1.0-alpha.1` | Frontend package version |
| `mapf` | Python import and CLI entry point |
| API 1 / bundle 1.0 | Separate interface and data contracts; see [compatibility](COMPATIBILITY.md) |

Alpha means that interfaces and behavior may evolve. Record the exact source commit, dependency lock, method identity and effective inputs for a study. Preserve its environment while runs are active. The compatibility guide distinguishes supported entry points from implementation details and describes artifact version checks.

## What the evidence establishes

Software tests and installed-package checks exercise finite workflows; they do not prove algorithmic correctness or universal scalability. The gallery contains independently valid selected solutions, with capture and trajectory provenance. It is conditional on solving and is not a success-rate estimate. Agent occupancy and obstacle density measure different properties.

The Python implementation is related to the JAAMAS 2024 and EUMAS 2021 papers. For studies using their settings, the [reproducibility guide](../REPRODUCIBILITY.md) explains how to record scenarios, method versions, solver settings, budgets and analysis denominators. Software qualification and numerical evaluation answer different questions.

The GUI runs locally. See [installation](INSTALLATION.md) for source and wheel workflows, and [reporting an issue](MAINTENANCE.md) for support.
