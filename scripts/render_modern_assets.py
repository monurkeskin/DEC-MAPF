#!/usr/bin/env python3
"""Redirect the obsolete aggregate plotter to the qualified experiment workflow.

The old input schema did not carry complete planned denominators or paired cost
cohorts. It cannot support an article comparison or verified-result captions.
"""


def main() -> None:
    raise SystemExit(
        "This aggregate plotter is retired. Use mapf batch export/analyze with a "
        "saved workspace; see docs/HEADLESS.md. Existing result files are untouched."
    )


if __name__ == "__main__":
    main()
