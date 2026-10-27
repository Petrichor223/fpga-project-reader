#!/usr/bin/env python3
"""Normalize the bundled Vivado/Quartus clock queries. Never infers physical wiring."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys

from build_clock_tree import digest, dump, read_json, validate


def node_id(name):
    return 'clk-' + hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]


def flag(value):
    if str(value).lower() in {'1', 'true', 'yes'}:
        return True
    if str(value).lower() in {'0', 'false', 'no'}:
        return False
    return None


def normalize(raw_path, context_path):
    raw_path, context_path = Path(raw_path).resolve(), Path(context_path).resolve()
    raw, model = read_json(raw_path), copy.deepcopy(read_json(context_path))
    if raw.get('format') != 'fpga-clock-query-v1':
        raise ValueError('unsupported raw query format')
    vendor = raw.get('vendor')
    if vendor not in {'vivado', 'quartus'} or model['config']['vendor'] != vendor:
        raise ValueError('vendor mismatch between query and context')
    root = Path(model['source_root'])
    if not root.is_absolute():
        root = context_path.parent / root
    root = root.resolve()
    model['source_root'] = str(root)
    session = raw.get('session', {})
    for key in ('project', 'revision', 'top', 'device'):
        actual, expected = str(session.get(key, '')), str(model['config'].get(key, ''))
        if actual and expected and expected != 'unknown' and actual != expected:
            raise ValueError(f'session/context {key} mismatch: {actual!r} != {expected!r}')
    if model.get('nodes') or model.get('edges'):
        raise ValueError('context must not contain an existing graph; merge evidence explicitly')
    model['schema_version'] = 1
    model['nodes'], model['edges'] = [], []
    model['analysis']['method'] = 'native'
    model['analysis'].setdefault('limitations', [])
    model['analysis']['limitations'].append('仅提取工具时钟对象与派生关系；未提取实际时钟路由、中间原语或消费者，不代表板上测量。')
    if any(not session.get(k) for k in ('project', 'revision', 'top', 'device')):
        model['analysis']['limitations'].append('部分会话身份字段不可查询；相应身份由 context 证据补充，未自动确认。')
    model['query'] = {k: raw.get(k) for k in ('vendor', 'tool_version', 'exported_utc', 'session', 'warnings')}
    if raw.get('warnings'):
        model['analysis']['limitations'].append(f'原生属性查询有 {len(raw["warnings"])} 条警告，原值见 query.warnings。')
    file = os.path.relpath(raw_path, root).replace('\\', '/')
    inputs = model.setdefault('inputs', [])
    existing = [i for i in inputs if i['file'] == file]
    if existing and existing[0]['sha256'] != digest(raw_path):
        raise ValueError('raw query identity disagrees with context input')
    if not existing:
        inputs.append({'file': file, 'sha256': digest(raw_path)})
    evidence = model.setdefault('evidence', {})
    rows = raw.get('clocks')
    if not isinstance(rows, list):
        raise ValueError('raw clocks must be an array')
    names = [row.get('name') for row in rows]
    if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        raise ValueError('empty or duplicate clock names in raw query')
    ids = {name: node_id(name) for name in names}
    if len(set(ids.values())) != len(ids):
        raise ValueError('clock ID hash collision')
    ev_by_name = {}
    for index, row in enumerate(rows):
        name = row['name']
        eid = 'Q-' + ids[name]
        if eid in evidence:
            raise ValueError('context evidence ID collision: ' + eid)
        evidence[eid] = {'kind': 'tool', 'file': file, 'locator': f'clocks[{index}] name={name}'}
        ev_by_name[name] = eid
        virtual, generated = flag(row.get('virtual')), flag(row.get('generated'))
        kind = 'virtual' if virtual else 'clock' if generated is not None else 'unknown'
        if vendor == 'quartus' and row.get('type') not in {'base', 'generated', 'virtual_base', 'virtual_generated'}:
            kind = 'unknown'
        try:
            period = float(row['period_ns'])
            frequency = 1000.0 / period if math.isfinite(period) and period > 0 else None
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            frequency = None
        if frequency is not None and not math.isfinite(frequency):
            frequency = None
        model['nodes'].append({'id': ids[name], 'label': name, 'kind': kind,
                               'status': 'confirmed' if kind != 'unknown' else 'unknown',
                               'evidence': [eid], 'attributes': row,
                               'frequencies': [{'value_mhz': frequency, 'basis': 'tool_timing_model',
                                                'status': 'confirmed' if frequency is not None else 'unknown',
                                                'evidence': [eid], 'note': '1000 / PERIOD(ns)；仅描述工具时序模型'}]})
    for row in rows:
        name, eid = row['name'], ev_by_name[row['name']]
        masters = row.get('masters', [])
        if not isinstance(masters, list) or any(not isinstance(x, str) or not x for x in masters):
            raise ValueError(name + ': masters must be a JSON array of clock names')
        if not masters and flag(row.get('generated')) is True:
            masters = ['<unknown master of ' + name + '>']
        for master in masters:
            if master not in ids:
                pid = node_id(master)
                if pid in ids.values():
                    raise ValueError('clock ID collision for unresolved parent')
                ids[master] = pid
                model['nodes'].append({'id': pid, 'label': master, 'kind': 'unknown', 'status': 'unknown',
                                       'evidence': [eid], 'frequencies': [],
                                       'notes': '父时钟未出现在查询结果中，保留未解析来源；不推断物理源。'})
            model['edges'].append({'id': 'rel-' + str(len(model['edges'])), 'source': ids[master],
                                   'target': ids[name], 'kind': 'derivation', 'status': 'confirmed' if master in ev_by_name else 'unknown',
                                   'evidence': [eid], 'label': '工具 MASTER_CLOCK 关系'})
    errors, _, _ = validate(model, root)
    if errors:
        raise ValueError('; '.join(errors))
    return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw')
    parser.add_argument('--context', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        target = Path(args.output)
        if target.exists():
            raise ValueError('output exists; use a new model path to preserve existing data')
        model = normalize(args.raw, args.context)
        dump(target, model)
        print(json.dumps({'output': str(target.resolve()), 'nodes': len(model['nodes']), 'edges': len(model['edges'])}))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
