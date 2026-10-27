"""Clock graph behavior tests. Vendor calls use mocks, not EDA compatibility tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from build_clock_tree import build, digest, dump, validate
from import_clock_query import normalize


def fixture(root):
    root = Path(root)
    source = root / 'clock-sources.txt'
    source.write_text('SYNTHETIC TEST DATA; NOT A HARDWARE DESIGN\nref: 50 MHz board nominal; 100 MHz constraint\npll: 200 MHz configuration; 160 MHz constraint\nmux: ref or pll under select\nconsumer: top/video\nfeedback: pll to pll input through fb buffer\n', encoding='utf-8')
    evidence = {'E1': {'kind': 'fixture', 'file': source.name, 'locator': 'L1-L6 synthetic clock facts'},
                'E2': {'kind': 'missing', 'reason': 'test deliberately has unknown source', 'checked': 'fixture text'}}
    model = {'schema_version': 1, 'source_root': str(root),
             'config': {'id': 'CFG-TEST', 'vendor': 'quartus', 'project': 'demo', 'revision': 'rev_a', 'top': 'top', 'device': 'unitpart'},
             'analysis': {'mode': 'quick', 'method': 'static', 'stage': 'source', 'identity_match': 'unverified',
                          'scope': '合成示例：两个候选源、反馈、虚拟时钟与未知来源',
                          'limitations': ['仅用于验证绘图功能，非实际 FPGA 工程；未进行原生工具验证']},
             'inputs': [{'file': source.name, 'sha256': digest(source)}], 'evidence': evidence, 'nodes': [], 'edges': []}
    def frequency(value, basis='ip_configuration', mode=''):
        return {'value_mhz': value, 'basis': basis, 'mode': mode, 'status': 'confirmed', 'evidence': ['E1']}
    for nid, kind, label, fs in [
        ('ref', 'source', 'ref_clk', [frequency(50, 'external_spec'), frequency(100, 'constraint')]),
        ('pll', 'pll_output', 'top/u_pll/out0', [frequency(200), frequency(160, 'constraint')]),
        ('mux', 'mux', 'top/u_clock_select', [frequency(50, mode='select=0'), frequency(200, mode='select=1')]),
        ('load', 'consumer', 'top/video/clock', []),
        ('fb', 'buffer', 'top/u_pll/feedback_buffer', []),
        ('virtual', 'virtual', 'virtual_io_clock', [frequency(125, 'constraint')]),
        ('unknown', 'unknown', 'unresolved_rx_clock', [])]:
        model['nodes'].append({'id': nid, 'kind': kind, 'label': label,
                               'status': 'unknown' if kind == 'unknown' else 'confirmed',
                               'evidence': ['E2'] if kind == 'unknown' else ['E1'], 'frequencies': fs})
    for i, (s, t, kind, condition) in enumerate([
        ('ref', 'pll', 'distribution', ''), ('ref', 'pll', 'derivation', ''),
        ('ref', 'mux', 'distribution', 'select=0'), ('pll', 'mux', 'distribution', 'select=1'),
        ('mux', 'load', 'distribution', ''), ('pll', 'fb', 'distribution', ''), ('fb', 'pll', 'feedback', '')]):
        model['edges'].append({'id': 'e' + str(i), 'source': s, 'target': t, 'kind': kind,
                               'condition': condition, 'status': 'confirmed', 'evidence': ['E1']})
    return model


class ClockTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fpga-clock-test-', dir=os.environ.get('FPGA_CLOCK_TEST_DIR'))
        self.root = Path(self.tmp.name)
        self.model = fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def check_model(self, model):
        return validate(model, self.root)

    def test_mux_feedback_virtual_and_frequency_conflict_preserved(self):
        errors, warnings, _ = self.check_model(self.model)
        self.assertFalse(errors)
        self.assertTrue(any('频率声明' in w for w in warnings))
        path = self.root / 'model.json'
        dump(path, self.model)
        output = self.root / 'quick'
        report = build(path, output)
        self.assertTrue(report['passed'], report)
        svg = ET.parse(output / 'reports/clock-tree.svg')
        self.assertEqual(len(svg.findall('.//{http://www.w3.org/2000/svg}g[@class="node"]')), 7)
        cells = ET.parse(output / 'reports/clock-tree.drawio').findall('.//mxCell')
        self.assertEqual(sum(c.get('edge') == '1' for c in cells), 7)
        self.assertEqual(sum(c.get('vertex') == '1' for c in cells), 8)
        self.assertIn('160 MHz', (output / 'reports/clock-tree.md').read_text(encoding='utf-8'))
        self.assertTrue(build(path, output)['passed'])

    def test_stale_inputs_block_build_and_can_be_repaired(self):
        path, out = self.root / 'model.json', self.root / 'quick'
        dump(path, self.model)
        self.assertTrue(build(path, out)['passed'])
        old_svg = digest(out / 'reports/clock-tree.svg')
        with (self.root / 'clock-sources.txt').open('a') as f:
            f.write('changed input')
        result = build(path, out)
        self.assertFalse(result['passed'])
        self.assertTrue(any('stale' in e for e in result['errors']))
        self.assertEqual(old_svg, digest(out / 'reports/clock-tree.svg'))
        self.model['inputs'][0]['sha256'] = digest(self.root / 'clock-sources.txt')
        dump(path, self.model)
        self.assertTrue(build(path, out)['passed'])

    def test_unowned_and_manually_edited_outputs_not_overwritten(self):
        path, out = self.root / 'model.json', self.root / 'quick'
        dump(path, self.model)
        (out / 'reports').mkdir(parents=True)
        target = out / 'reports/clock-tree.md'
        target.write_text('manual notes', encoding='utf-8')
        self.assertFalse(build(path, out)['passed'])
        self.assertEqual(target.read_text(encoding='utf-8'), 'manual notes')

    def test_dangling_cycles_duplicate_edges_and_virtual_loads_fail(self):
        cases = []
        m = copy.deepcopy(self.model); m['edges'][0]['target'] = 'missing'; cases.append(m)
        m = copy.deepcopy(self.model); m['edges'][-1]['kind'] = 'distribution'; cases.append(m)
        m = copy.deepcopy(self.model); e = copy.deepcopy(m['edges'][0]); e['id'] = 'dup'; m['edges'].append(e); cases.append(m)
        m = copy.deepcopy(self.model); m['edges'][0]['source'] = 'virtual'; cases.append(m)
        for model in cases:
            with self.subTest(model=model['edges'][-1]):
                self.assertTrue(self.check_model(model)[0])

    def test_bad_frequency_and_unresolved_evidence_fail(self):
        for value in (0, -1, float('nan'), float('inf'), True):
            model = copy.deepcopy(self.model)
            model['nodes'][0]['frequencies'][0]['value_mhz'] = value
            self.assertTrue(self.check_model(model)[0])
        model = copy.deepcopy(self.model)
        model['edges'][0]['evidence'] = ['invented']
        self.assertTrue(self.check_model(model)[0])
        model = copy.deepcopy(self.model)
        model['analysis']['identity_match'] = 'confirmed'
        self.assertTrue(self.check_model(model)[0])
        model = copy.deepcopy(self.model)
        model['nodes'][0]['evidence'] = ['E2']
        self.assertTrue(self.check_model(model)[0])

    def test_report_cannot_replace_a_declared_source_file(self):
        out = self.root / 'quick'
        target = out / 'reports/clock-tree.md'
        target.parent.mkdir(parents=True)
        target.write_text('source document', encoding='utf-8')
        self.model['inputs'].append({'file': str(target), 'sha256': digest(target)})
        model_path = self.root / 'model.json'
        dump(model_path, self.model)
        result = build(model_path, out)
        self.assertFalse(result['passed'])
        self.assertIn('collides', result['errors'][0])
        self.assertEqual(target.read_text(encoding='utf-8'), 'source document')

    def test_hostile_source_text_is_text_in_html_svg_and_drawio(self):
        hostile = '</script><img src=x onerror="window.INJECTED=1"> & \" [0]'
        self.model['nodes'][0]['label'] = hostile
        self.model['nodes'][0]['attributes'] = {'hostile': hostile}
        path, out = self.root / 'model.json', self.root / 'quick'
        dump(path, self.model)
        self.assertTrue(build(path, out)['passed'])
        text = (out / 'reports/clock-tree.html').read_text(encoding='utf-8')
        self.assertNotIn('</script><img', text)
        self.assertNotIn('<img src=x', text)
        ET.parse(out / 'reports/clock-tree.svg')
        ET.parse(out / 'reports/clock-tree.drawio')

    def query_fixture(self, vendor):
        context = copy.deepcopy(self.model)
        context['config']['vendor'] = vendor
        context.pop('nodes'); context.pop('edges')
        root_name = 'root [0] "clock"'
        raw = {'format': 'fpga-clock-query-v1', 'vendor': vendor, 'tool_version': 'MOCK',
               'session': {k: context['config'][k] for k in ('project', 'revision', 'top', 'device')},
               'warnings': [], 'clocks': [
                   {'name': root_name, 'period_ns': '10', 'generated': '0', 'virtual': '0', 'type': 'base', 'masters': [], 'targets': ['clk[0]']},
                   {'name': 'derived', 'period_ns': '5', 'generated': '1', 'virtual': '0', 'type': 'generated', 'masters': [root_name], 'targets': ['u_pll|outclk[0]']}]}
        raw_path, context_path = self.root / (vendor + '.json'), self.root / 'context.json'
        dump(raw_path, raw); dump(context_path, context)
        return raw, context, raw_path, context_path

    def test_import_both_vendors_no_physical_wiring_invented(self):
        for vendor in ('vivado', 'quartus'):
            _, _, raw, ctx = self.query_fixture(vendor)
            result = normalize(raw, ctx)
            self.assertEqual(len(result['nodes']), 2)
            self.assertEqual(len(result['edges']), 1)
            self.assertEqual(result['edges'][0]['kind'], 'derivation')
            self.assertEqual(result['nodes'][1]['frequencies'][0]['value_mhz'], 200)
            self.assertTrue(all(n['kind'] == 'clock' for n in result['nodes']))

    def test_import_unknown_parent_and_bad_period_remain_unknown(self):
        raw, _, raw_path, ctx = self.query_fixture('quartus')
        raw['clocks'][1].update(masters=['absent master'], period_ns='bad')
        dump(raw_path, raw)
        result = normalize(raw_path, ctx)
        self.assertEqual(result['nodes'][1]['frequencies'][0]['value_mhz'], None)
        self.assertEqual(result['nodes'][-1]['kind'], 'unknown')
        self.assertEqual(result['edges'][0]['status'], 'unknown')

    def test_import_rejects_wrong_revision_and_duplicate_names(self):
        raw, _, raw_path, ctx = self.query_fixture('quartus')
        raw['session']['revision'] = 'wrong'
        dump(raw_path, raw)
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            normalize(raw_path, ctx)
        raw['session']['revision'] = 'rev_a'
        raw['clocks'].append(raw['clocks'][0])
        dump(raw_path, raw)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            normalize(raw_path, ctx)

    def test_tcl_collectors_json_collections_and_query_failures(self):
        try:
            import tkinter
        except ImportError:
            self.skipTest('Tcl runtime unavailable; no native EDA validation asserted')
        for vendor in ('vivado', 'quartus'):
            with self.subTest(vendor=vendor):
                interp = tkinter.Tcl()
                root_name = 'root [0] "clock" \\ 中文\nline'
                generated_name = 'generated {1}'
                tcl_root = str(self.root / (vendor + '-tcl.json'))
                interp.setvar('fpga_reader_clock_export', tcl_root)
                interp.createcommand('get_clocks', lambda *args: ('c0', 'c1'))
                if vendor == 'vivado':
                    interp.createcommand('current_design', lambda *args: 'top')
                    interp.createcommand('current_project', lambda *args: 'project-object')
                    interp.createcommand('version', lambda *args: 'MOCK-VIVADO')
                    def get_property(prop, obj):
                        if obj == 'top':
                            return 'unitpart'
                        if obj == 'project-object':
                            return 'demo'
                        values = {'NAME': root_name if obj == 'c0' else generated_name, 'PERIOD': '10' if obj == 'c0' else '5',
                                  'IS_GENERATED': '0' if obj == 'c0' else '1', 'IS_VIRTUAL': '0',
                                  'MASTER_CLOCK': '' if obj == 'c0' else root_name,
                                  'SOURCE_PINS': ('top/clk[0]',), 'WAVEFORM': ('0', '5')}
                        return values.get(prop, '')
                    interp.createcommand('get_property', get_property)
                else:
                    interp.setvar('quartus(version)', 'MOCK-QUARTUS')
                    interp.eval('proc foreach_in_collection {var collection body} {upvar 1 $var item; if {[string match COL_* $collection]} {set collection [resolve_mock_collection $collection]}; foreach item $collection {uplevel 1 $body}}')
                    interp.createcommand('resolve_mock_collection', lambda value: ('n0', 'n1'))
                    interp.createcommand('get_current_project', lambda: 'demo')
                    interp.createcommand('get_current_revision', lambda: 'rev_a')
                    interp.createcommand('get_global_assignment', lambda *args: 'top' if args[-1] == 'TOP_LEVEL_ENTITY' else 'unitpart')
                    def get_clock_info(option, obj):
                        if option == '-phase':
                            raise tkinter.TclError('unsupported optional phase (mock)')
                        values = {'-name': root_name if obj == 'c0' else generated_name,
                                  '-period': '10' if obj == 'c0' else '5',
                                  '-type': 'base' if obj == 'c0' else 'generated',
                                  '-master_clock': root_name, '-targets': 'COL_TARGETS', '-waveform': ('0', '5')}
                        return values.get(option, '')
                    interp.createcommand('get_clock_info', get_clock_info)
                    interp.createcommand('get_node_info', lambda option, obj: {'n0': 'u_pll|outclk[0]', 'n1': 'pin with spaces'}[obj])
                interp.call('source', str(SCRIPTS / ('export_' + vendor + '_clocks.tcl')))
                raw = json.loads(Path(tcl_root).read_text(encoding='utf-8'))
                self.assertEqual(raw['clocks'][1]['masters'], [root_name])
                self.assertEqual(raw['clocks'][0]['name'], root_name)
                self.assertEqual(raw['clocks'][0]['waveform_ns'], ['0', '5'])
                if vendor == 'quartus':
                    self.assertEqual(raw['clocks'][0]['targets'], ['u_pll|outclk[0]', 'pin with spaces'])
                    self.assertTrue(raw['warnings'])
                with self.assertRaises(tkinter.TclError):
                    interp.call('source', str(SCRIPTS / ('export_' + vendor + '_clocks.tcl')))


if __name__ == '__main__':
    unittest.main()
