import json,struct,unittest,copy
from pathlib import Path
from opencal.core import Document,digest,differences
from opencal.solutions import AXIS,launch_control_state,launch_control_maps,preview_launch_control,apply_preview
from opencal.checksums import SIGNATURE,correct,inspect
from tests.private_fixtures import STOCK,V9


def fixture():
    data=bytearray(0x80000);data[0x70001:0x7000c]=SIGNATURE;s=0x6c100
    data[s:s+16]=bytes.fromhex('80 C2 02 00 80 00 00 0A FF FF 02 00 00 00 70 17')
    struct.pack_into('<25H',data,s+36,*range(400,5400,200))
    return data,s


class SolutionTests(unittest.TestCase):
    def test_preview_patch_undo_redo_restore_and_maps(self):
        data,s=fixture();preview=preview_launch_control(data)
        self.assertEqual(len(preview['edits']),1);self.assertFalse(launch_control_maps(data))
        self.assertEqual(data,fixture()[0])
        d=Document(data);apply_preview(d,preview)
        self.assertEqual(d.data[s+2:s+32],AXIS)
        self.assertEqual(d.data[:s+2],data[:s+2]);self.assertEqual(d.data[s+32:],data[s+32:])
        self.assertEqual(launch_control_state(d.data)['status'],'active')
        self.assertEqual(len(launch_control_maps(d.data)),1)
        self.assertFalse(preview_launch_control(d.data)['edits'])
        d.undo();self.assertEqual(d.data,data);d.redo();self.assertEqual(d.data[s+2:s+32],AXIS)
        restore=preview_launch_control(d.data,d.original);apply_preview(d,restore);self.assertEqual(d.data,data)

    def test_stale_and_corrupt_previews_fail_without_partial_write(self):
        data,s=fixture();d=Document(data);p=preview_launch_control(data);d.edit(100,b'x');before=bytes(d.data)
        with self.assertRaises(ValueError):apply_preview(d,p)
        self.assertEqual(d.data,before)
        d=Document(data);p=copy.deepcopy(p);p['result_sha256']='0'*64
        with self.assertRaises(ValueError):apply_preview(d,p)
        self.assertEqual(d.data,data)

    def test_layout_and_axis_guards_and_legacy_active_header(self):
        data,s=fixture();data[s+36:s+86]=bytes(50)
        self.assertFalse(launch_control_state(data)['sites'])
        self.assertEqual(launch_control_state(bytes(0x100000))['status'],'unsupported')
        data,s=fixture();data[s+2:s+32]=b'\x00\x0e'+AXIS[2:]
        self.assertEqual(launch_control_state(data)['status'],'active')

    @unittest.skipUnless(STOCK.exists() and V9.exists(),'Private copies unavailable')
    def test_private_files_match_upstream_typescript_oracle(self):
        oracle=Path(__file__).resolve().parents[3]/'work/lc-oracle.json'
        if not oracle.exists():self.skipTest('Development oracle unavailable')
        for item in json.loads(oracle.read_text()):
            data=Path(item['copy']).read_bytes();d=Document(data);preview=preview_launch_control(data)
            self.assertEqual(digest(data),item['input_sha256'])
            self.assertEqual(len(preview['edits']),len(item['patches']))
            apply_preview(d,preview);self.assertEqual(digest(d.data),item['result_sha256'])
            self.assertEqual(len(launch_control_maps(d.data)),len(item['applied_maps']))
            self.assertEqual(inspect(correct(d.data,data))['status'],'matched')
            apply_preview(d,preview_launch_control(d.data,data));self.assertEqual(d.data,data)
