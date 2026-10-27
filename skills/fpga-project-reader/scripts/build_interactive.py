#!/usr/bin/env python3
"""Validate an evidence-backed hierarchy and build a self-contained offline HTML.

No RTL parser, elaborator, network, package installer or external Python dependencies.
Usage: python build_interactive.py architecture.json --output interactive.html
Optional --validation validation.json; --validate-only checks without generating HTML.
"""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
STATES = {'confirmed', 'inferred', 'unknown'}
CATEGORIES = {'data', 'control', 'clock', 'reset', 'debug'}
VISIBILITY = {'analyzed', 'not_analyzed', 'encrypted', 'blackbox', 'missing'}


def validate(model):
    if model.get('schema') != 'fpga-reader-architecture/v1':
        raise ValueError('Unsupported schema')
    nodes, ports, parents, edges = {}, {}, {}, []
    evidence = model.get('evidence', {})
    if not model.get('config') or not model.get('scope') or model.get('mode') not in {'quick', 'detailed'} or not model.get('project_root'):
        raise ValueError('Configuration and coverage scope are required')
    for key, item in evidence.items():
        if not item.get('file') or not isinstance(item.get('line'), int) or item['line'] < 1:
            raise ValueError(f'Invalid evidence location: {key}')
        if not re.fullmatch(r'[0-9a-f]{64}',item.get('sha256', '')):
            raise ValueError(f'Missing source identity: {key}')
        path=item['file'].replace('\\','/')
        if path.startswith('/') or re.match(r'^[A-Za-z]:',path) or '..' in path.split('/'):
            raise ValueError(f'Evidence must be project-relative: {key}')
    config_refs=model.get('configuration_evidence', [])
    if not config_refs or any(ref not in evidence for ref in config_refs):
        raise ValueError('Configuration evidence is required')

    def claim(item, label):
        if item.get('status') not in STATES:
            raise ValueError(f'Missing conclusion status: {label}')
        refs = item.get('evidence', [])
        if item['status'] != 'unknown' and not refs:
            raise ValueError(f'No evidence: {label}')
        if any(ref not in evidence for ref in refs):
            raise ValueError(f'Invalid evidence reference: {label}')

    def visit(node, parent):
        ident = node['id']
        if ident in nodes:
            raise ValueError(f'Duplicate instance ID: {ident}')
        nodes[ident], parents[ident] = node, parent
        claim(node, ident)
        if node.get('visibility') not in VISIBILITY:
            raise ValueError(f'Invalid implementation visibility: {ident}')
        if node.get('category', 'data') not in CATEGORIES:
            raise ValueError(f'Invalid category: {ident}')
        if node['visibility'] in {'encrypted', 'blackbox', 'missing', 'not_analyzed'} and node.get('children'):
            raise ValueError(f'Opaque/unread node cannot claim children: {ident}')
        local, physical = {}, set()
        for port in node.get('ports', []):
            if port['id'] in local or port.get('direction') not in {'input', 'output', 'inout'}:
                raise ValueError(f'Invalid/duplicate interface: {ident}/{port["id"]}')
            if port.get('side', 'WEST') not in {'WEST','EAST','NORTH','SOUTH'}:
                raise ValueError(f'Invalid port side: {ident}/{port["id"]}')
            members = port.get('members', [])
            if not members or len({m['name'] for m in members}) != len(members):
                raise ValueError(f'Missing/duplicate physical members: {ident}/{port["id"]}')
            names={m['name'] for m in members}
            if physical & names:
                raise ValueError(f'Physical member belongs to multiple interfaces: {ident}/{port["id"]}')
            physical.update(names)
            local[port['id']] = port
        ports[ident] = local
        for clock in node.get('clocks', []):
            claim(clock, f'{ident}/clock')
            hz = clock.get('frequency_hz')
            if hz is not None and (not isinstance(hz, (int, float)) or isinstance(hz, bool) or hz <= 0):
                raise ValueError(f'Invalid clock frequency: {ident}')
            if hz is not None and clock['status'] == 'unknown':
                raise ValueError(f'Unknown clock must have null frequency: {ident}')
        for child in node.get('children', []):
            visit(child, ident)
        for edge in node.get('edges', []):
            claim(edge, edge['id'])
            edges.append((ident, edge))

    visit(model['root'], None)
    for record in model.get('coverage', []):
        ident=record['instance']
        if ident not in nodes:
            raise ValueError(f'Coverage refers to missing container: {ident}')
        actual={n['label'] for n in nodes[ident].get('children', [])}
        enabled=record['enabled_components'];matched=record['matched_components'];missing=record['missing_components']
        if len(enabled)!=len(set(enabled)) or set(matched)&set(missing) or set(matched)|set(missing)!=set(enabled):
            raise ValueError(f'Inconsistent configuration coverage: {ident}')
        if set(matched)!=actual&set(enabled) or set(missing)!=set(enabled)-actual:
            raise ValueError(f'Coverage does not match actual child instances: {ident}')
        if record['rtl_direct_instances']!=len(actual) or set(record['generated_infrastructure'])!=actual-set(enabled):
            raise ValueError(f'Inconsistent generated instance coverage: {ident}')
        if not record.get('evidence') or any(e not in evidence for e in record['evidence']):
            raise ValueError(f'Missing coverage provenance: {ident}')
    edge_ids = set()
    boundary_count = 0
    for owner, edge in edges:
        if edge['id'] in edge_ids or edge['id'] in nodes:
            raise ValueError(f'Duplicate edge ID: {edge["id"]}')
        edge_ids.add(edge['id'])
        if edge.get('category') not in CATEGORIES:
            raise ValueError(f'Invalid edge category: {edge["id"]}')
        for side in ('source', 'target'):
            endpoint = edge[side]
            ident, port = endpoint['node'], endpoint['port']
            if ident not in nodes or port not in ports[ident]:
                raise ValueError(f'Dangling endpoint: {edge["id"]}/{side}')
            if ident != owner and parents[ident] != owner:
                raise ValueError(f'Edge crosses hierarchy without boundary mapping: {edge["id"]}')
            direction = ports[ident][port]['direction']
            expected = ('input' if side == 'source' else 'output') if ident == owner else ('output' if side == 'source' else 'input')
            if direction not in {expected, 'inout'}:
                raise ValueError(f'Wrong physical signal direction: {edge["id"]}/{side}')
        if owner in {edge['source']['node'], edge['target']['node']}:
            boundary_count += 1
        if not edge.get('signals'):
            raise ValueError(f'No physical signal mapping: {edge["id"]}')
        for signal in edge['signals']:
            for side in ('source', 'target'):
                endpoint = edge[side]
                names = {p['name'] for p in ports[endpoint['node']][endpoint['port']]['members']}
                if signal.get(side) not in names:
                    raise ValueError(f'Unknown mapped physical port: {edge["id"]}/{side}')
            if not signal.get('net'):
                raise ValueError(f'Missing net expression: {edge["id"]}')
    presentation = validate_presentation(model, nodes, ports, parents, edges, claim)
    return {'schema': model['schema'], 'nodes': len(nodes), 'interfaces': sum(map(len, ports.values())),
            'edges': len(edges), 'boundary_mappings': boundary_count,
            'evidence_locations': len(evidence), 'presentation': presentation, 'result': 'passed',
            'limits': 'Schema/connectivity invariants only; no HDL elaboration, timing or functional proof.'}


def validate_presentation(model, rtl, physical_ports, rtl_parents, raw_edges, claim):
    """Check a separate board/bus projection without weakening physical-direction checks."""
    view = model.get('presentation')
    if not view:
        return None
    nodes, parents, ports, buses = {}, {}, {}, []
    board = view['root']['id']
    raw = {e['id']: (owner, e) for owner, e in raw_edges}
    def visit(n, parent):
        ident = n['id']
        if ident in nodes:
            raise ValueError('Duplicate presentation node: ' + ident)
        nodes[ident], parents[ident] = n, parent
        claim(n, ident)
        kind = n.get('kind')
        if n.get('hidden_by_default'):
            if kind != 'rtl' or n.get('display_role') != 'auxiliary_system' or not n.get('hide_reason'):
                raise ValueError('Only explicit auxiliary system IP may be hidden: ' + ident)
            if n.get('category') in {'clock', 'reset'}:
                raise ValueError('Clock/reset IP must remain visible: ' + ident)
        if kind == 'rtl':
            if ident not in rtl or parent != (rtl_parents[ident] or board):
                raise ValueError('Presentation changes RTL hierarchy: ' + ident)
            if {c['id'] for c in n.get('children', [])} != {c['id'] for c in rtl[ident].get('children', [])}:
                raise ValueError('Presentation drops direct IP: ' + ident)
        elif kind == 'external':
            if ident in rtl or parent != board or n.get('children'):
                raise ValueError('External device confused with RTL: ' + ident)
        elif kind != 'board' or ident != board or parent is not None or ident in rtl:
            raise ValueError('Invalid board presentation node: ' + ident)
        local, mapped = {}, set()
        for p in n.get('ports', []):
            if p['id'] in local or p.get('direction') not in {'input', 'output', 'inout'}:
                raise ValueError('Invalid logical interface: ' + ident)
            claim(p, ident + '/' + p['id'])
            refs = p.get('physical_ports', [])
            if kind == 'rtl' and (not refs or len(refs) != len(set(refs)) or mapped.intersection(refs) or any(x not in physical_ports[ident] for x in refs)):
                raise ValueError('Invalid/overlapping interface membership: ' + ident)
            mapped.update(refs)
            local[p['id']] = p
        ports[ident] = local
        for child in n.get('children', []):
            visit(child, ident)
        buses.extend((ident, e) for e in n.get('edges', []))
    visit(view['root'], None)
    if {k for k,n in nodes.items() if n['kind']=='rtl'} != set(rtl):
        raise ValueError('Presentation RTL coverage differs')
    seen, used = set(), set()
    for owner, bus in buses:
        ident = bus['id']
        claim(bus, ident)
        if ident in seen or ident in nodes or bus.get('category') not in CATEGORIES or bus.get('flow') not in {'forward', 'bidirectional', 'tap'}:
            raise ValueError('Invalid logical bus: ' + ident)
        seen.add(ident)
        for side in ('source', 'target'):
            ep = bus[side]
            if ep['node'] not in nodes or ep['port'] not in ports[ep['node']] or (ep['node'] != owner and parents[ep['node']] != owner):
                raise ValueError('Invalid bus boundary: ' + ident)
        member_ids = bus.get('member_edges', [])
        if len(member_ids) != len(set(member_ids)) or used.intersection(member_ids):
            raise ValueError('Physical edge counted in multiple buses: ' + ident)
        for member in member_ids:
            if member not in raw or raw[member][0] != owner:
                raise ValueError('Unknown/wrong-owner bus member: ' + ident)
            original = raw[member][1]
            endpoints = [bus['source'], bus['target']]
            for side in ('source', 'target'):
                ep = original[side]
                if not any(p['node']==ep['node'] and ep['port'] in ports[p['node']][p['port']].get('physical_ports', []) for p in endpoints):
                    raise ValueError('Bus member belongs to another interface: ' + ident)
        used.update(member_ids)
        mappings = bus.get('mappings', [])
        if not member_ids and not mappings:
            raise ValueError('Bus has no connection evidence: ' + ident)
        for mapping in mappings:
            if not mapping.get('expression'):
                raise ValueError('Missing explicit bus mapping expression: ' + ident)
            for side in ('source', 'target'):
                ep = bus[side]
                if nodes[ep['node']]['kind'] == 'rtl':
                    names = {m['name'] for p in ports[ep['node']][ep['port']]['physical_ports'] for m in physical_ports[ep['node']][p]['members']}
                    if mapping.get(side) not in names:
                        raise ValueError('Unknown bus physical signal: ' + ident)
    omitted = view.get('omitted_edges', [])
    excluded = {x['id'] for x in omitted}
    if len(excluded) != len(omitted) or excluded & used or excluded | used != set(raw) or any(not x.get('reason') for x in omitted):
        raise ValueError('Unaccounted physical edges in presentation')
    return {'rtl_instances': len(rtl), 'external_devices': sum(n['kind']=='external' for n in nodes.values()),
            'logical_buses': len(buses), 'mapped_physical_edges': len(used), 'omitted_physical_edges': len(excluded)}


def build(model, output):
    template = (ASSETS / 'interactive.html').read_text(encoding='utf-8')
    vendor = ASSETS / 'vendor'
    libs = '\n'.join((vendor / name).read_text(encoding='utf-8') for name in
                     ('d3.min.js', 'elk.bundled.js', 'd3-hwschematic.js'))
    # Keep source-provided strings out of executable JS and HTML markup.
    payload = json.dumps(model, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    licenses = '\n\n'.join((vendor / name).read_text(encoding='utf-8') for name in
                           ('NOTICE.txt', 'D3-LICENSE.txt', 'ELK-LICENSE.txt', 'HWSCHEMATIC-LICENSE.txt'))
    replacements = {'@@TITLE@@': html.escape(model.get('title', 'FPGA architecture')),
                    '@@VENDOR_CSS@@': (vendor / 'd3-hwschematic.css').read_text(encoding='utf-8'),
                    '@@VENDOR_JS@@': re.sub('</script',r'<\\/script',libs,flags=re.I),
                    '@@DATA@@': payload, '@@LICENSES@@': html.escape(licenses)}
    template=re.sub('|'.join(map(re.escape,replacements)),lambda m:replacements[m[0]],template)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--validation', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    model = json.loads(args.model.read_text(encoding='utf-8-sig'))
    result = validate(model)
    result['model_sha256'] = hashlib.sha256(args.model.read_bytes()).hexdigest()
    if not args.validate_only:
        if args.output is None:
            parser.error('--output is required unless --validate-only')
        if args.output.resolve() == args.model.resolve():
            parser.error('Output must not overwrite the model')
        build(model, args.output)
    if args.validation:
        args.validation.parent.mkdir(parents=True, exist_ok=True)
        args.validation.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
