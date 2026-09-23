# Licensing and attribution

You may use, modify and redistribute DEC-MAPF's original implementation under [MIT](../LICENSE), including commercial use, while retaining its copyright and permission notice. This grant does not replace third-party licenses. The [third-party notice index](../THIRD_PARTY_NOTICES.md) identifies those boundaries.

| What you distribute | Notices to retain |
| --- | --- |
| Source repository or source archive | `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `docs/licenses/` |
| Installed Python wheel | Project license in package metadata; GUI notices and inventory under `mapf/gui/static/workspace/` |
| Built browser workspace | `THIRD_PARTY_NOTICES.txt`, `license-inventory.json`, and existing license comments in the bundle |
| Rendered documentation | Project license, this page, and the [complete documentation notices](licenses/documentation.txt); retain theme attribution |
| A Python environment or container | The above plus licenses of all dependencies installed into that environment |
| Optional native reconstruction | The [pinned upstream licenses](licenses/native.txt), source notices and the patch/build receipt; review upstream usage restrictions first |

## What is included

The GUI's [inventory](licenses/frontend.json) covers the complete locked production dependency closure and Vite's injected runtime helper. It conservatively includes type/optional packages; it is not a claim that every file from every listed package appears in the browser bundle. Lucide's full notice includes its Feather attribution. The `@pixi/colord` package omits its standalone license, so the notice is preserved from its pinned upstream commit and checked by hash.

The English documentation ships local JavaScript, CSS and images with no external web-font dependency. [Documentation notices](licenses/documentation.txt) include the MkDocs BSD license, Material MIT license, bundled JavaScript/style licenses and icon attribution. English search uses the embedded Lunr implementation. Unused non-English language/segmenter files are excluded; changing the search language requires reviewing their notices before building.

EECBS and CBSH2-RTC are optional research baselines with USC's own license terms. **The project's MIT license does not authorize commercial use of these third-party solvers.** The default Python installation does not download or require them. [Native baseline instructions](NATIVE-BASELINES.md) describe their source revisions, prerequisites and reconstruction boundary. Boost is also separately acquired and retains the [Boost Software License](https://www.boost.org/LICENSE_1_0.txt).

The two papers should be [cited](../README.md#citations) when their methods are used. Citation is a scholarly request; it does not add a condition to the MIT license. Article PDFs, externally downloaded maps and historical benchmark data are not part of the source or wheel release.

## Maintaining the notices

Build from the lockfiles. `npm run build` checks installed package versions and complete license text against the committed GUI inventory before copying notices into the output. After reviewing a dependency upgrade:

```bash
npm --prefix frontend ci
node scripts/frontend_licenses.mjs --write
.venv/bin/python scripts/check_licenses.py --docs
.venv/bin/python scripts/build_docs.py
```

For a documentation dependency upgrade, review the installed package license files, theme source maps and its exact upstream package lock; update `docs/licenses/documentation.txt` and `documentation.json` together. The inventory records source URLs, package versions, original notice hashes and all distributed theme asset hashes. The checker rejects an unreviewed version or asset change. Keep upstream license/NOTICE text intact. A new license or missing notice requires review; changing only an SPDX label is insufficient.

`check_distributions.py` rejects source/wheel artifacts without the required notices. The installed GUI exposes them through its **Open-source notices** link. None of these checks determines the rights to a dataset that you supply yourself.

Next: [installation](INSTALLATION.md), [contribution guide](../CONTRIBUTING.md), or [native baselines](NATIVE-BASELINES.md).
