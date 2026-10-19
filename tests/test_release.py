import json,tempfile,unittest,zipfile,hashlib
from pathlib import Path
from tools.package_release import package,public_files


class ReleaseTests(unittest.TestCase):
    def test_package_empties_private_catalog_and_verifies_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';(root/'opencal/data').mkdir(parents=True);(root/'examples').mkdir()
            (root/'README.md').write_text('Synthetic test');(root/'examples/synthetic.bin').write_bytes(b'OCAL')
            catalog=root/'opencal/data/reference-profiles.json';catalog.write_text(json.dumps({'profiles':[{'private':'data'}]}))
            output=Path(temp)/'public.zip';count,sha=package(root,output,'test')
            self.assertEqual(count,3);self.assertEqual(sha,hashlib.sha256(output.read_bytes()).hexdigest())
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(json.loads(archive.read('OpenCal-test/opencal/data/reference-profiles.json'))['profiles'],[])
                for name,value in json.loads(archive.read('OpenCal-test/SOURCE-MANIFEST.json')).items():
                    self.assertEqual(value,hashlib.sha256(archive.read('OpenCal-test/'+name)).hexdigest())
            self.assertTrue(json.loads(catalog.read_text())['profiles'])

    def test_unexpected_firmware_and_projects_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'examples').mkdir()
            for name in ('customer.bin','project.ocproj','file.ori','file.bin.audit.json'):
                path=root/'examples'/name;path.write_bytes(b'private')
                with self.assertRaises(ValueError):list(public_files(root))
                path.unlink()
