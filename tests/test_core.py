import base64
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from opencal.core import *


def definitions():
    return {'schema':'opencal.definitions','version':1,'signatures':[
        {'name':'Synthetic fixture','family':'TEST ONLY','address':0,'hex':'4f43414c','source':'Original synthetic fixture','license':'MIT'}],
        'maps':[{'id':'curve','name':'Synthetic curve','address':16,'rows':2,'columns':4,'type':'u16','endian':'little',
                 'factor':0.5,'offset':-10,'unit':'demo units','category':'demo','verification':'synthetic',
                 'source':'Original synthetic fixture','license':'MIT','minimum':-10,'maximum':1000}]}


class CoreTests(unittest.TestCase):
    def test_preservation_and_undo(self):
        d=Document(bytes(range(128))); d.edit(12,b'\xff\xfe')
        self.assertEqual(d.original,bytes(range(128)))
        self.assertEqual(list(differences(d.original,d.data)),[(12,14)])
        d.undo(); self.assertEqual(d.data,d.original)
        d.redo(); self.assertEqual(d.data[12:14],b'\xff\xfe')
        d.undo(); d.edit(0,b'\xff'); self.assertFalse(d.redo_stack)

    def test_edit_bounds(self):
        d=Document(b'abcd')
        for a,b in [(-1,b'a'),(4,b'a'),(0,b''),(3,b'abc')]:
            with self.assertRaises(ValueError): d.edit(a,b)
        self.assertEqual(d.data,b'abcd')

    def test_search(self):
        d=Document(b'ababab'); self.assertEqual(d.find(b'ab',1),2)
        self.assertEqual(d.find(b'ff'),-1)
        with self.assertRaises(ValueError): d.find(b'')

    def test_diff_sizes(self):
        self.assertEqual(list(differences(b'ab',b'abcd')),[(2,4)])
        self.assertEqual(list(differences(b'abcd',b'ab')),[(2,4)])
        self.assertEqual(list(differences(b'abc',b'axz')),[(1,3)])
        self.assertEqual(list(differences(b'abc',b'abc')),[])

    def test_map_scaling_and_endian(self):
        d=Document(bytes(64)); m=definitions()['maps'][0]
        d.set_map_cell(m,2,15); self.assertEqual(d.data[20:22],b'2\0')
        self.assertEqual(map_values(d.data,m)[2],15)
        self.assertEqual(list(differences(d.original,d.data)),[(20,21)])
        m=copy.deepcopy(m); m['endian']='big'; m['type']='i16'
        d.set_map_cell(m,0,20); self.assertEqual(d.data[16:18],b'\0<')
        with self.assertRaises(ValueError): d.set_map_cell(m,0,2000)
        with self.assertRaises(ValueError): d.set_map_cell(m,0,float('nan'))
        with self.assertRaises(ValueError): d.set_map_cell(m,8,20)

    def test_definitions(self):
        good=definitions(); self.assertEqual(validate_definitions(good,64),good)
        self.assertEqual(validate_definitions(json.loads(json.dumps(good)),64),good)
        for key,value in [('address',63),('factor',0),('factor',float('inf')),('rows',0),('rows',1.5),('endian','native'),('type','u64'),('license','')]:
            bad=copy.deepcopy(good); bad['maps'][0][key]=value
            with self.assertRaises(ValueError): validate_definitions(bad,64)
        bad=copy.deepcopy(good); bad['maps']*=2
        with self.assertRaises(ValueError): validate_definitions(bad,64)

    def test_identification_evidence(self):
        defs=definitions()
        self.assertFalse(identify(bytes(64),defs))
        result=identify(b'OCAL'+bytes(60),defs)
        self.assertEqual(result[0]['family'],'TEST ONLY')
        self.assertIn('0x0',result[0]['evidence'])

    def test_axis_scan(self):
        data=struct.pack('<12H',*range(100,1300,100))+bytes(20)
        found=scan_axes(data)
        self.assertEqual(found[0]['address'],0); self.assertEqual(found[0]['length'],12)
        self.assertEqual(found[0]['status'],'candidate')
        self.assertEqual(scan_axes(bytes(64)),[])
        with self.assertRaises(ValueError): scan_axes(data,-1)

    def test_safe_export(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'original.bin'; src.write_bytes(b'abcdef')
            d=Document(read_binary(src),src); d.edit(1,b'Z')
            with self.assertRaises(ValueError): d.export(src)
            out=Path(temp)/'modified.bin'; report=d.export(out)
            self.assertEqual(out.read_bytes(),b'aZcdef'); self.assertEqual(src.read_bytes(),b'abcdef')
            self.assertEqual(report['checksum']['status'],'unverified')
            self.assertEqual(json.loads(Path(str(out)+'.audit.json').read_text())['changed_ranges'],[[1,2]])
            with self.assertRaises(FileExistsError): d.export(out)

    def test_export_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'existing.bin'; p.write_bytes(b'important')
            with self.assertRaises(FileExistsError): Document(b'abc').export(p)
            self.assertEqual(p.read_bytes(),b'important')
            self.assertFalse(Path(str(p)+'.audit.json').exists())

    def test_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'project.ocproj'; d=Document(b'OCAL'+bytes(60))
            d.definitions=definitions(); d.edit(5,b'123'); d.profiles['one']=bytes(d.data); d.undo()
            d.save_project(p); loaded=Document.load_project(p)
            self.assertEqual(loaded.original,d.original); self.assertEqual(loaded.data,d.data)
            self.assertEqual(loaded.definitions,d.definitions); self.assertEqual(loaded.profiles,d.profiles)
            loaded.redo(); self.assertEqual(loaded.data[5:8],b'123')
            loaded.undo(); self.assertEqual(loaded.data,d.data)
            with self.assertRaises(ValueError): loaded.export(p)

    def test_project_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'bad.ocproj'; d=Document(bytes(64)); d.save_project(p)
            good=json.loads(p.read_text())
            for key,value in [('original',base64.b64encode(b'bad').decode()),('version',99),('profiles',{'x':base64.b64encode(b'bad').decode()}),('undo',[[100,'00','01','x']])]:
                obj=copy.deepcopy(good); obj[key]=value; p.write_text(json.dumps(obj))
                with self.assertRaises(ValueError): Document.load_project(p)

    def test_source_project_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'orig.bin'; src.write_bytes(bytes(64)); d=Document(src.read_bytes(),src)
            with self.assertRaises(ValueError): d.save_project(src)
            self.assertEqual(src.read_bytes(),bytes(64))

    def test_invalid_files(self):
        with self.assertRaises(ValueError): Document(b'')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'empty'; p.touch()
            with self.assertRaises(ValueError): read_binary(p)


if __name__=='__main__': unittest.main()
