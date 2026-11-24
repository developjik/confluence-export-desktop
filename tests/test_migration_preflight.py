import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
spec=importlib.util.spec_from_file_location('migration_preflight',Path(__file__).resolve().parents[1]/'scripts/migration_preflight.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MigrationPreflightTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.old=self.root/'legacy';self.old.mkdir();self.new=self.root/'v2'
 def test_legacy_detected_without_inventing_schema_or_writing(self):
  p=self.old/'confluence-lock.json';body=json.dumps({'private':'DO_NOT_PRINT','pages':[1]});p.write_text(body);r=m.preflight(self.old,self.new);self.assertTrue(r['ready_for_manual_guide']);self.assertFalse(r['automatic_checksum_reuse']);self.assertEqual(r['locks'][p.name]['status'],'legacy-present');self.assertNotIn('DO_NOT_PRINT',json.dumps(r));self.assertEqual(p.read_text(),body);self.assertFalse(self.new.exists())
 def test_v2_shape_count_only(self):
  (self.old/'confluence-export.lock.json').write_text(json.dumps({'schema_version':2,'pages':{'secret-id':{}}}));r=m.preflight(self.old,self.new);self.assertEqual(r['locks']['confluence-export.lock.json']['page_entries'],1);self.assertNotIn('secret-id',json.dumps(r))
 def test_unknown_and_malformed_refused(self):
  p=self.old/'confluence-export.lock.json'
  for body in ['{bad','null','{}','{"schema_version":99,"pages":{}}']:
   p.write_text(body);self.assertFalse(m.preflight(self.old,self.new)['ready_for_manual_guide'])
 def test_regular_file_and_bounds(self):
  p=self.old/'confluence-lock.json';p.mkdir();self.assertFalse(m.preflight(self.old,self.new)['ready_for_manual_guide']);p.rmdir();p.write_bytes(b'x'*(m.LIMIT+1));self.assertFalse(m.preflight(self.old,self.new)['ready_for_manual_guide'])
 def test_separate_target_required(self):
  for target in [self.old,self.old/'child',self.root]:
   with self.assertRaises(ValueError):m.preflight(self.old,target)
 def test_case_aliases_conservatively_refused(self):
  for target in [self.root/'LEGACY',self.root/'LEGACY'/'child']:
   with self.assertRaises(ValueError):m.preflight(self.old,target)
 def test_file_ancestor_refused(self):
  p=self.root/'file';p.write_text('keep')
  with self.assertRaises(ValueError):m.preflight(self.old,p/'child')
  self.assertEqual(p.read_text(),'keep')
 def test_empty_target_only(self):
  self.new.mkdir();self.assertTrue(m.preflight(self.old,self.new)['ready_for_manual_guide']);(self.new/'keep').write_text('keep')
  with self.assertRaises(ValueError):m.preflight(self.old,self.new)
  self.assertEqual((self.new/'keep').read_text(),'keep')
 @unittest.skipIf(sys.platform=='win32','symlink privilege varies on Windows')
 def test_symlinks_refused(self):
  data=self.root/'data';data.write_text('{}');(self.old/'confluence-lock.json').symlink_to(data);self.assertFalse(m.preflight(self.old,self.new)['ready_for_manual_guide']);self.new.symlink_to(self.root/'other')
  with self.assertRaises(ValueError):m.preflight(self.old,self.new)
 def test_cli_codes_and_private_paths_not_echoed(self):
  cmd=[sys.executable,str(Path(m.__file__)),'--legacy-dir',str(self.old),'--v2-target',str(self.new)]
  r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0);self.assertNotIn(str(self.root),r.stdout+r.stderr)
  (self.old/'confluence-lock.json').write_text('bad');self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,1)
  r=subprocess.run(cmd[:-1]+[str(self.old)],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertNotIn(str(self.root),r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
