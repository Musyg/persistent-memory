"""Twelve independent family tests against the active Linux installation."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

spec=importlib.util.spec_from_file_location('independent_package_probe',Path(__file__).with_name('public_admission_probe.py'))
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class InstalledBoundaryTests(unittest.TestCase):
    def check_family(self,group):
        self.assertTrue(sys.platform.startswith('linux'),'Linux installation required')
        rows=probe.run_group(group)
        print(json.dumps({'family':group,'results':rows},ensure_ascii=True),flush=True)
        self.assertTrue(all(r['passed'] for r in rows),json.dumps([{'variant':r['variant'],'error':r.get('failed_check',r.get('error_type'))} for r in rows if not r['passed']]))
    def test_p01_installed_opt_in(self): self.check_family('P01')
    def test_p02_shared_graph_import_orders(self): self.check_family('P02')
    def test_p03_ambient_and_reserved_homonyms(self): self.check_family('P03')
    def test_p04_resource_integrity_and_cleanup(self): self.check_family('P04')
    def test_p05_reviewed_one_and_four_facts(self): self.check_family('P05')
    def test_p06_counter_and_mechanical_boundaries(self): self.check_family('P06')
    def test_p07_unneeded_revoked_source(self): self.check_family('P07')
    def test_p08_epistemic_notices(self): self.check_family('P08')
    def test_p09_access_loss_sanitization(self): self.check_family('P09')
    def test_p10_transform_and_final_authority(self): self.check_family('P10')
    def test_p11_unknown_sink_without_retry(self): self.check_family('P11')
    def test_p12_snapshot_and_sink_copy_isolation(self): self.check_family('P12')

if __name__=='__main__':unittest.main(verbosity=2)
