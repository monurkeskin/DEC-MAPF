"""Reject missing, failed, skipped or flaky required qualification checks."""
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def check(python_xml: Path, browser_json: Path | None = None) -> dict[str, int]:
    root = ET.parse(python_xml).getroot()
    cases = list(root.iter('testcase'))
    failures = [node for case in cases for node in case if node.tag in {'error', 'failure', 'skipped'}]
    if not cases or failures:
        raise ValueError('Python acceptance requires nonempty cases with no failures, errors or skips')
    result = {'python_cases': len(cases)}
    if browser_json is not None:
        stats = json.loads(browser_json.read_text())['stats']
        if not stats.get('expected') or any(stats.get(k, 0) for k in ['skipped', 'unexpected', 'flaky']):
            raise ValueError('Browser acceptance requires nonempty, unskipped, nonflaky passing cases')
        result['browser_cases'] = stats['expected']
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('python_xml', type=Path)
    parser.add_argument('--browser-json', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.python_xml, args.browser_json)))
