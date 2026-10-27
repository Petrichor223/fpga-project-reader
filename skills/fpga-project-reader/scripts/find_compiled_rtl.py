#!/usr/bin/env python3
"""Inventory existing Quartus elaboration artifacts without running Quartus.

Discovery is not netlist extraction or freshness verification. Database candidates
require a compatible tool; reports cannot supply absent connectivity.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def discover(project, revision):
    project = Path(project).resolve()
    candidates = []
    for directory in [project/'output_files', project]:
        if not directory.is_dir():
            continue
        for p in sorted(directory.glob(revision+'.*')):
            if not p.is_file() or p.suffix not in {'.rpt', '.summary'}:
                continue
            kind = 'elaboration_report' if p.name.endswith('.syn.ae.rpt') else 'compile_report'
            raw = p.read_bytes()
            head = raw[:16384].decode('utf-8', errors='replace')
            version = re.search(r'(?:Quartus Prime Version\s*:?|Version)\s*([\d.]+)', head)
            candidates.append({'path':p.relative_to(project).as_posix(), 'kind':kind,
                'stage':'elaborated' if kind=='elaboration_report' else 'not_established',
                'tool_version':version[1] if version else None,
                'sha256':hashlib.sha256(raw).hexdigest(),
                'identity':'requires_revision_top_device_and_input_verification',
                'connectivity':'not_available_from_report_alone'})
    checkpoint = project/'dni/checkpoints'/revision/'user_runs/default_run/elaborated'
    if checkpoint.is_dir():
        candidates.insert(0, {'path':checkpoint.relative_to(project).as_posix(),
            'kind':'native_checkpoint','stage':'elaborated','identity':'unverified',
            'connectivity':'requires_compatible_quartus_read_only_query'})
    qdb = project/'qdb'
    if qdb.is_dir():
        candidates.append({'path':'qdb','kind':'native_database_directory',
            'stage':'unknown','identity':'unverified','connectivity':'directory_presence_is_not_rtl_viewer_data'})
    has_elab=any(c['stage']=='elaborated' for c in candidates)
    return {'schema':'fpga-reader-compiled-rtl-discovery/v1','project_root':project.as_posix(),
        'revision':revision,'candidates':candidates,
        'decision':'inspect_elaborated_candidates_first' if has_elab else 'inspect_other_compile_artifacts' if candidates else 'static_fallback_no_candidates',
        'limits':'No compilation, extraction, database decoding, source-freshness proof or implicit synthesis.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('project', type=Path)
    p.add_argument('--revision', required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',a.revision):
        p.error('revision must be a simple revision name')
    result=discover(a.project,a.revision)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'candidates':len(result['candidates']),'decision':result['decision']}))


if __name__=='__main__':main()
