# Third-party resources and source availability

The root MIT license applies to project-owned material for which the project authors can grant that license. The third-party files in this folder retain their own licenses and notices. The following source locations are provided for the bundled distributions; this record does not resolve upstream licensing ambiguities.

| Resource | Bundled version | Source and license information |
|---|---|---|
| `d3.min.js` | d3 6.7.0 | [D3 v6.7.0 source](https://github.com/d3/d3/tree/v6.7.0), [bundled license](D3-LICENSE.txt) |
| `elk.bundled.js` | elkjs 0.8.2 | [elkjs 0.8.2 source](https://github.com/kieler/elkjs/tree/0.8.2), [release notes](https://github.com/kieler/elkjs/releases/tag/0.8.2), [bundled license](ELK-LICENSE.txt). The release notes state that it is based on ELK 0.8.1; [ELK v0.8.1 source](https://github.com/eclipse-elk/elk/tree/v0.8.1). |
| `d3-hwschematic.js`, `d3-hwschematic.css` | d3-hwschematic 0.1.6 | The `src/`, package metadata, build files, README and license from the locally installed 0.1.6 package are provided in [source/d3-hwschematic-0.1.6/](source/d3-hwschematic-0.1.6/). [Original npm release](https://www.npmjs.com/package/d3-hwschematic/v/0.1.6), [upstream project](https://github.com/Nic30/d3-hwschematic), [bundled license](HWSCHEMATIC-LICENSE.txt). |

The distributed JavaScript and CSS were checked byte-for-byte against the locally installed packages of the versions listed above. For `d3-hwschematic`, the 0.1.6 package metadata names EPL-1.0, while its accompanying `LICENSE` text says EPL-2.0. This discrepancy remains unresolved; both are recorded without asserting which one controls. The current upstream default branch differs from the locally installed 0.1.6 sources, so it must not be assumed to be the exact source of the bundled file.

The original [NOTICE.txt](NOTICE.txt) uses `v0.8.2` in the elkjs GitHub URL. The verified elkjs tag is `0.8.2` as linked above. Check each upstream license, source-availability requirement and the notices when redistributing the bundled assets or generated HTML.
