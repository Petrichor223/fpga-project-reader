#!/usr/bin/env python3
"""Validate an evidence-backed clock graph and build offline SVG/draw.io/HTML.

No HDL parser or vendor software is invoked. Python standard library only.
"""
import argparse
from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import sys
import textwrap
import xml.etree.ElementTree as ET

KINDS = {'source', 'clock', 'pll_output', 'buffer', 'mux', 'gate', 'divider',
         'recovered', 'consumer', 'virtual', 'unknown'}
BASES = {'external_spec', 'ip_configuration', 'constraint', 'tool_timing_model',
         'simulation', 'measurement', 'unknown'}
STATES = {'confirmed': '已确认', 'inferred': '推断', 'unknown': '未知'}
COLORS = {'source': '#d9f2e3', 'clock': '#e0eaff', 'pll_output': '#e8ddfa',
          'buffer': '#e4edf2', 'mux': '#fff0cb', 'gate': '#ffeadb',
          'divider': '#e8ddfa', 'recovered': '#d8f3f5', 'consumer': '#e7edf5',
          'virtual': '#f0e8fc', 'unknown': '#ffdfdf'}
BASIS_NAMES = dict(external_spec='外部规格', ip_configuration='IP 配置',
                   constraint='约束目标', tool_timing_model='工具时序模型',
                   simulation='仿真激励', measurement='测量', unknown='未知')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def validate(model, root):
    errors, warnings = [], []

    def need(test, message):
        if not test:
            errors.append(message)
        return test

    def refs(obj, location):
        values = obj.get('evidence')
        if not need(isinstance(values, list) and bool(values), location + ': evidence must be nonempty'):
            return
        for eid in values:
            need(isinstance(eid, str) and eid in evidence, location + ': unresolved evidence ' + str(eid))
        if obj.get('status') == 'confirmed':
            need(any(isinstance(eid, str) and isinstance(evidence.get(eid), dict) and evidence[eid].get('kind') != 'missing'
                     for eid in values), location + ': confirmed statement needs non-missing evidence')

    if not isinstance(model, dict):
        return ['model must be an object'], [], {}
    need(model.get('schema_version') == 1, 'schema_version must be 1')
    config = model.get('config', {})
    analysis = model.get('analysis', {})
    if not isinstance(config, dict) or not isinstance(analysis, dict):
        return ['config and analysis must be objects'], [], {}
    for key in ('id', 'vendor', 'project', 'revision', 'top', 'device'):
        need(isinstance(config.get(key), str) and bool(config[key].strip()), 'config.' + key + ' required (use unknown explicitly)')
    need(config.get('vendor') in {'vivado', 'quartus', 'other'}, 'unsupported vendor')
    need(analysis.get('mode') in {'quick', 'detailed'}, 'analysis.mode must be quick/detailed')
    need(analysis.get('method') in {'static', 'native', 'mixed'}, 'invalid analysis.method')
    need(analysis.get('identity_match') in {'confirmed', 'unverified', 'historical'}, 'invalid identity_match')
    for key in ('stage', 'scope'):
        need(isinstance(analysis.get(key), str) and bool(analysis[key].strip()), 'analysis.' + key + ' required')
    limits = analysis.get('limitations')
    need(isinstance(limits, list) and bool(limits) and all(isinstance(x, str) for x in limits), 'analysis.limitations must list coverage/validation boundary')
    if analysis.get('identity_match') != 'confirmed':
        warnings.append('编译输入匹配性未确认或为历史结果；不能称为当前完整网表事实。')
    evidence = model.get('evidence', {})
    if not isinstance(evidence, dict):
        return errors + ['evidence must be an object'], warnings, {}
    inputs = model.get('inputs', [])
    if not need(isinstance(inputs, list) and bool(inputs), 'inputs must contain scoped source identities'):
        inputs = []
    checked = {}
    for item in inputs:
        if not isinstance(item, dict):
            errors.append('input must be an object')
            continue
        file = item.get('file')
        sha = item.get('sha256')
        if not need(isinstance(file, str) and file and isinstance(sha, str) and len(sha) == 64,
                    'input requires file and SHA256'):
            continue
        need(file not in checked, 'duplicate input: ' + file)
        try:
            actual = digest(root / file)
            checked[file] = actual
            need(actual == sha.lower(), 'stale input SHA256: ' + file)
        except OSError as exc:
            errors.append('unreadable input: ' + file + ': ' + str(exc))
    for eid, ev in evidence.items():
        if not isinstance(ev, dict):
            errors.append('invalid evidence: ' + eid)
            continue
        if ev.get('kind') == 'missing':
            need(bool(ev.get('reason')) and bool(ev.get('checked')), eid + ': missing evidence needs reason and checked scope')
        else:
            need(ev.get('file') in checked and bool(ev.get('locator')), eid + ': evidence file must be an input with locator')
    if analysis.get('identity_match') == 'confirmed':
        refs({'status': 'confirmed', 'evidence': analysis.get('identity_evidence')}, 'analysis.identity_evidence')
    nodes, edges = model.get('nodes', []), model.get('edges', [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return errors + ['nodes and edges must be arrays'], warnings, checked
    if not nodes:
        warnings.append('未导入任何时钟节点；这不证明工程没有时钟。')
    by_id = {}
    for n in nodes:
        if not isinstance(n, dict):
            errors.append('node must be an object')
            continue
        nid = n.get('id')
        if not need(isinstance(nid, str) and bool(nid), 'node.id required'):
            continue
        need(nid not in by_id, 'duplicate node: ' + nid)
        by_id[nid] = n
        need(isinstance(n.get('label'), str) and bool(n['label']), nid + ': label required')
        need(n.get('kind') in KINDS, nid + ': unsupported kind')
        need(n.get('status') in STATES, nid + ': invalid status')
        refs(n, nid)
        frequencies = n.get('frequencies', [])
        if not need(isinstance(frequencies, list), nid + ': frequencies must be an array'):
            continue
        if not frequencies and n.get('kind') != 'consumer':
            warnings.append(nid + ': 频率未知。')
        seen_values = defaultdict(set)
        for f in frequencies:
            if not isinstance(f, dict):
                errors.append(nid + ': invalid frequency object')
                continue
            need(f.get('basis') in BASES, nid + ': invalid frequency basis')
            need(f.get('status') in STATES, nid + ': invalid frequency status')
            refs(f, nid + '.frequency')
            value = f.get('value_mhz')
            if value is None:
                need(f.get('status') == 'unknown', nid + ': null frequency must be unknown')
                continue
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
            need(valid, nid + ': frequency must be positive finite MHz or null')
            need(f.get('status') != 'unknown', nid + ': unknown frequency must use null')
            if valid:
                seen_values[(f.get('basis'), f.get('mode', ''))].add(value)
        if any(len(v) > 1 for v in seen_values.values()):
            warnings.append(nid + ': 同一性质/模式存在冲突频率；已全部保留。')
        all_values = {f.get('value_mhz') for f in frequencies if isinstance(f, dict) and isinstance(f.get('value_mhz'), (int, float))}
        if len(all_values) > 1:
            warnings.append(nid + ': 多个频率声明，需按性质/模式核对差异。')
    indegree = {nid: 0 for nid in by_id}
    successors = defaultdict(list)
    edge_ids, keys = set(), set()
    for e in edges:
        if not isinstance(e, dict):
            errors.append('edge must be an object')
            continue
        eid, source, target = e.get('id'), e.get('source'), e.get('target')
        if not need(isinstance(eid, str) and bool(eid), 'edge.id required'):
            continue
        need(eid not in edge_ids, 'duplicate edge id: ' + eid)
        edge_ids.add(eid)
        if not need(isinstance(source, str) and source in by_id and isinstance(target, str) and target in by_id, eid + ': missing endpoint'):
            continue
        need(e.get('kind') in {'derivation', 'distribution', 'feedback'}, eid + ': invalid edge kind')
        need(e.get('status') in STATES, eid + ': invalid status')
        refs(e, eid)
        need(source != target, eid + ': self edge is not supported')
        key = (source, target, e.get('kind'), e.get('condition', ''))
        need(key not in keys, eid + ': duplicate relation (use condition for alternate modes)')
        keys.add(key)
        if e.get('kind') in {'distribution', 'feedback'}:
            need(all(by_id[x].get('kind') != 'virtual' for x in (source, target)), eid + ': virtual clock cannot have physical wiring')
        if e.get('kind') != 'feedback':
            indegree[target] += 1
            successors[source].append(target)
    queue = deque(n for n, count in indegree.items() if count == 0)
    seen = 0
    while queue:
        n = queue.popleft()
        seen += 1
        for child in successors[n]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    need(seen == len(by_id), 'cycle in derivation/distribution graph; inspect feedback separately')
    for n in nodes:
        if isinstance(n, dict) and n.get('kind') in {'mux', 'unknown'}:
            warnings.append(n.get('id', '?') + ': 检查候选输入、选择条件或未解析来源。')
    return errors, warnings, checked


def freq_text(node):
    fs = node.get('frequencies', [])
    if not fs:
        return ['频率未知'] if node['kind'] != 'consumer' else []
    lines = []
    for f in fs:
        value = '未知' if f['value_mhz'] is None else f"{f['value_mhz']:.6g} MHz"
        mode = ' / ' + f['mode'] if f.get('mode') else ''
        lines.append(value + ' · ' + BASIS_NAMES[f['basis']] + mode)
    return lines


def layout(model):
    nodes = {n['id']: n for n in model['nodes']}
    adj, indegree, depth = defaultdict(list), dict.fromkeys(nodes, 0), dict.fromkeys(nodes, 0)
    for e in model['edges']:
        if e['kind'] != 'feedback':
            adj[e['source']].append(e['target'])
            indegree[e['target']] += 1
    queue = deque(sorted(n for n in nodes if not indegree[n]))
    while queue:
        nid = queue.popleft()
        for target in adj[nid]:
            depth[target] = max(depth[target], depth[nid] + 1)
            indegree[target] -= 1
            if not indegree[target]:
                queue.append(target)
    columns = defaultdict(list)
    for nid in nodes:
        columns[depth[nid]].append(nid)
    boxes = {}
    for col, ids in columns.items():
        y = 170
        for nid in sorted(ids):
            n = nodes[nid]
            lines = []
            for line in [n['label'], n['kind'] + ' · ' + STATES[n['status']]] + freq_text(n):
                lines.extend(textwrap.wrap(line, width=30, replace_whitespace=True) or [''])
            height = max(92, 28 + 21 * len(lines))
            boxes[nid] = {'x': 50 + col * 590, 'y': y, 'w': 400, 'h': height, 'lines': lines}
            y += height + 62
    width = max((b['x'] + b['w'] for b in boxes.values()), default=800) + 100
    height = max((b['y'] + b['h'] for b in boxes.values()), default=300) + 100
    return boxes, width, height


def render_svg(model, boxes, width, height):
    esc = lambda x: html.escape(str(x), quote=True)
    c, a = model['config'], model['analysis']
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="FPGA 时钟树">',
              '<defs><marker id="clock-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="context-stroke"/></marker></defs>',
              '<style>text{font-family:Segoe UI,Microsoft YaHei,sans-serif;fill:#16243b} .node{cursor:pointer}.node:focus rect{stroke:#111;stroke-width:3}.selected rect{stroke:#c45700;stroke-width:4}.dim{opacity:.15}</style>',
              f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
              '<text x="50" y="36" font-size="23" font-weight="bold">FPGA 时钟树 / Clock topology</text>']
    title = f"{c['id']} · {c['vendor']} · {c['top']} · {c['revision']} · {a['stage']} · 匹配性 {a['identity_match']}"
    for i, line in enumerate(textwrap.wrap(title, max(45, int(width / 15)))[:3]):
        pieces.append(f'<text x="50" y="{62+i*19}" font-size="13">{esc(line)}</text>')
    pieces.append('<text x="50" y="132" font-size="13">紫色虚线：派生关系 / 蓝色实线：分配路径 / 灰色点线：反馈；完整证据见 HTML / Markdown</text>')
    for index, e in enumerate(model['edges']):
        s, t = boxes[e['source']], boxes[e['target']]
        sx, sy = s['x'] + s['w'], s['y'] + s['h'] / 2
        tx, ty = t['x'], t['y'] + t['h'] / 2
        color, dash = ('#7950b3', '8 5') if e['kind'] == 'derivation' else ('#2165ae', '')
        if e['kind'] == 'feedback':
            color, dash = '#667085', '3 5'
            lane = height - 30 - (index % 5) * 8
            route = f'M {sx} {sy} L {sx+25} {sy} L {sx+25} {lane} L {tx-25} {lane} L {tx-25} {ty} L {tx} {ty}'
        else:
            # Curves stay out of unrelated boxes even when skipping depth columns.
            # A lower perimeter lane avoids crossing intermediate node columns.
            if tx - sx > 250:
                lane = height - 20 - (index % 7) * 9
                route = f'M {sx} {sy} L {sx+30} {sy} L {sx+30} {lane} L {tx-30} {lane} L {tx-30} {ty} L {tx} {ty}'
            else:
                mid = (sx + tx) / 2
                route = f'M {sx} {sy} C {mid} {sy}, {mid} {ty}, {tx} {ty}'
        label = e.get('label') or e['kind']
        pieces.append(f'<g class="edge" data-edge="{esc(e["id"])}" data-kind="{esc(e["kind"])}"><title>{esc(label)} · {esc(STATES[e["status"]])} · {esc(", ".join(e["evidence"]))}</title><path d="{route}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}" marker-end="url(#clock-arrow)"/></g>')
    for n in model['nodes']:
        b = boxes[n['id']]
        pieces.append(f'<g class="node" tabindex="0" role="button" aria-label="{esc(n["label"])}" data-node="{esc(n["id"])}" data-kind="{esc(n["kind"])}"><title>{esc(n["label"])} · {esc(", ".join(n["evidence"]))}</title>')
        pieces.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" rx="10" fill="{COLORS[n["kind"]]}" stroke="#58718a" stroke-width="1.5"/>')
        for i, line in enumerate(b['lines']):
            pieces.append(f'<text x="{b["x"]+15}" y="{b["y"]+25+i*21}" font-size="{14 if i else 16}">{esc(line)}</text>')
        pieces.append('</g>')
    pieces.append('</svg>')
    return '\n'.join(pieces)


def render_drawio(model, boxes, width, height):
    root = ET.Element('mxfile', host='app.diagrams.net', type='device')
    diagram = ET.SubElement(root, 'diagram', id='clock-tree', name='FPGA 时钟树')
    graph = ET.SubElement(diagram, 'mxGraphModel', dx=str(width), dy=str(height), grid='1', gridSize='10', page='0')
    cells = ET.SubElement(graph, 'root')
    ET.SubElement(cells, 'mxCell', id='0')
    ET.SubElement(cells, 'mxCell', id='1', parent='0')
    mapping = {n['id']: 'n' + str(i) for i, n in enumerate(model['nodes'])}
    for n in model['nodes']:
        b = boxes[n['id']]
        cell = ET.SubElement(cells, 'mxCell', id=mapping[n['id']], value='\n'.join(b['lines']),
                             style=f'rounded=1;whiteSpace=wrap;html=0;fillColor={COLORS[n["kind"]]};strokeColor=#58718a;fontSize=14;', vertex='1', parent='1')
        cell.set('clock_id', n['id'])
        cell.set('evidence', ', '.join(n['evidence']))
        ET.SubElement(cell, 'mxGeometry', x=str(b['x']), y=str(b['y']), width=str(b['w']), height=str(b['h']), **{'as': 'geometry'})
    for i, e in enumerate(model['edges']):
        color = '#7950b3' if e['kind'] == 'derivation' else '#2165ae'
        label = (e.get('label') or e['kind']) + ' · ' + STATES[e['status']]
        style = f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;strokeColor={color};dashed={int(e["kind"]!="distribution")};'
        cell = ET.SubElement(cells, 'mxCell', id='e' + str(i), value=label, style=style,
                             edge='1', parent='1', source=mapping[e['source']], target=mapping[e['target']])
        cell.set('evidence', ', '.join(e['evidence']))
        ET.SubElement(cell, 'mxGeometry', relative='1', **{'as': 'geometry'})
    title = ET.SubElement(cells, 'mxCell', id='title', value='FPGA 时钟树\n' + json.dumps(model['config'], ensure_ascii=False) + '\n' + json.dumps(model['analysis'], ensure_ascii=False), style='text;html=0;whiteSpace=wrap;align=left;fontSize=14;', vertex='1', parent='1')
    ET.SubElement(title, 'mxGeometry', x='50', y='10', width=str(width-100), height='130', **{'as': 'geometry'})
    return ET.tostring(root, encoding='unicode')


def render_markdown(model, warnings):
    def safe(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')
    c, a = model['config'], model['analysis']
    lines = ['# FPGA 时钟树', '', '> 由 build_clock_tree.py 生成；修改模型后重新构建。', '',
             '[离线交互图](clock-tree.html) · [SVG](clock-tree.svg) · [Draw.io](clock-tree.drawio)', '',
             '配置：' + safe(json.dumps(c, ensure_ascii=False)), '',
             '分析：' + safe(json.dumps(a, ensure_ascii=False)), '',
             '结构校验与输入 SHA256 检查不等于原生工具、CDC 或硬件验证。', '',
             '## 时钟与节点', '', '| ID | 名称 / 类型 | 状态 | 频率与性质 | 证据 |',
             '|---|---|---|---|---|']
    for n in model['nodes']:
        lines.append('| ' + ' | '.join(map(safe, [n['id'], n['label'] + ' / ' + n['kind'], STATES[n['status']], '; '.join(freq_text(n)), ', '.join(n['evidence'])])) + ' |')
    for n in model['nodes']:
        if n.get('notes'):
            lines.extend(['', safe(n['id']) + '：' + safe(n['notes'])])
    lines.extend(['', '## 关系台账', '', '| 来源 → 目标 | 关系 | 状态 | 条件 / 说明 | 证据 |', '|---|---|---|---|---|'])
    for e in model['edges']:
        lines.append('| ' + ' | '.join(map(safe, [e['source'] + ' → ' + e['target'], e['kind'], STATES[e['status']], str(e.get('condition', '')) + ' ' + str(e.get('label', '')), ', '.join(e['evidence'])])) + ' |')
    lines.extend(['', '## 频率逐项证据', ''])
    for n in model['nodes']:
        for f in n.get('frequencies', []):
            lines.append('- ' + safe(n['id']) + ': ' + safe(json.dumps(f, ensure_ascii=False)))
    lines.extend(['', '## 警告与边界', ''])
    lines.extend('- ' + safe(w) for w in warnings + a['limitations'])
    lines.extend(['', '## 证据索引', '', '路径基准：' + safe(model['source_root']), ''])
    for eid, ev in model['evidence'].items():
        lines.append('- ' + safe(eid) + ': ' + safe(json.dumps(ev, ensure_ascii=False)))
    return '\n'.join(lines) + '\n'


def build(model_path, output_dir, project_root=None):
    model_path, output_dir = Path(model_path).resolve(), Path(output_dir).resolve()
    data_dir = output_dir / 'data'
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'model': str(model_path),
              'errors': [], 'warnings': [], 'browser_validation': 'not_run', 'native_tool_validation': 'not_asserted'}
    validation = data_dir / 'clock-tree-validation.json'
    previous = {}
    try:
        if validation.exists():
            previous = read_json(validation)
            if not isinstance(previous, dict):
                raise ValueError('existing validation manifest must be an object')
        model = read_json(model_path)
        root = Path(project_root or model['source_root'])
        if not root.is_absolute():
            root = model_path.parent / root
        root = root.resolve()
        errors, warnings, checked = validate(model, root)
        report.update(errors=errors, warnings=warnings, checked_inputs=checked,
                      model_sha256=digest(model_path), source_root=str(root))
        # An output directory inside a source root is normal; writing over an
        # input or the graph itself is never a legitimate output operation.
        declared_inputs = {str((root / item['file']).resolve()) for item in model.get('inputs', []) if isinstance(item, dict) and isinstance(item.get('file'), str)}
        protected = declared_inputs | {str(model_path)}
        if str(validation.resolve()) in protected:
            raise ValueError('validation output collides with a declared input/model')
        if errors:
            raise ValueError('model validation failed')
        boxes, width, height = layout(model)
        svg = render_svg(model, boxes, width, height)
        template = Path(__file__).resolve().parent.parent / 'assets' / 'clock-tree.html'
        payload = json.dumps(model, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
        webpage = template.read_text(encoding='utf-8').replace('<!--CLOCK_SVG-->', svg).replace('/*CLOCK_DATA*/null', payload)
        outputs = {'clock-tree.svg': svg, 'clock-tree.drawio': render_drawio(model, boxes, width, height),
                   'clock-tree.html': webpage, 'clock-tree.md': render_markdown(model, warnings)}
        paths = {name: output_dir / 'reports' / name for name in outputs}
        if any(str(path.resolve()) in protected for path in paths.values()):
            raise ValueError('report output collides with a declared input/model')
        for name, path in paths.items():
            if path.exists() and digest(path) != previous.get('outputs', {}).get(name):
                raise ValueError('refusing to overwrite unowned or edited output: ' + str(path))
        for name, value in outputs.items():
            paths[name].parent.mkdir(parents=True, exist_ok=True)
            paths[name].write_text(value, encoding='utf-8')
        report['outputs'] = {name: digest(path) for name, path in paths.items()}
        report['passed'] = True
        dump(validation, report)
        return report
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report['passed'] = False
        if not report['errors']:
            report['errors'] = [str(exc)]
        # Preserve ownership of unchanged old outputs so an invalid intermediate
        # model doesn't prevent rebuilding after it is corrected.
        report['outputs'] = previous.get('outputs', {}) if isinstance(previous, dict) else {}
        if str(validation.resolve()) != str(model_path) and str(validation.resolve()) not in locals().get('declared_inputs', set()):
            dump(validation, report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model')
    parser.add_argument('--output-dir', required=True, help='mode directory containing reports/ and data/')
    parser.add_argument('--project-root', help='override source root after relocating project')
    args = parser.parse_args()
    result = build(args.model, args.output_dir, args.project_root)
    print(json.dumps({'passed': result['passed'], 'errors': result['errors'],
                      'warnings': result['warnings'], 'output_dir': str(Path(args.output_dir).resolve())}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
