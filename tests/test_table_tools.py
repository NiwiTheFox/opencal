import copy,json,struct,tempfile,unittest
from pathlib import Path
from opencal.core import Document,map_values,axis_values,refresh_axes,validate_definitions,differences
from opencal.table_tools import *
from opencal.checksums import SIGNATURE
from tests.test_core import definitions


def document():
    d=Document(bytes(128));d.definitions=definitions();m=d.definitions['maps'][0]
    m.update(factor=1,offset=0)
    struct.pack_into('<8H',d.data,16,10,90,30,40,20,80,60,100)
    struct.pack_into('>4h',d.data,40,0,10,30,40)
    struct.pack_into('<2H',d.data,52,1000,2000)
    m['x_axis']={'address':40,'type':'i16','endian':'big','factor':.5,'offset':-2,'values':[-2,3,13,18],'unit':'demo X'}
    m['y_axis']={'address':52,'type':'u16','endian':'little','factor':1,'offset':0,'values':[1000,2000],'unit':'rpm'}
    # Initial bytes are an artificial fixture, not an unrecorded edit.
    return_data=bytes(d.data);d=Document(return_data);d.definitions={'schema':'opencal.definitions','version':1,'maps':[m]}
    return d,m


class TableTests(unittest.TestCase):
    def test_batch_operations_are_atomic_and_undoable(self):
        for operation,amount,expected in [('Set',50,[50,50]),('Add',5,[15,95]),('Percent',10,[11,99])]:
            d,m=document();p=operation_preview(d.data,m,operation,amount,indexes=[0,1],definitions=d.definitions)
            self.assertEqual(d.data,d.original);apply_table_preview(d,p)
            self.assertEqual(map_values(d.data,m)[:2],expected);self.assertEqual(map_values(d.data,m)[2:],[30,40,20,80,60,100])
            self.assertEqual(len(d.undo_stack),1);d.undo();self.assertEqual(d.data,d.original)
            d.redo();self.assertEqual(map_values(d.data,m)[:2],expected)
            apply_table_preview(d,operation_preview(d.data,m,'Restore original',original=d.original));self.assertEqual(d.data,d.original)

    def test_invalid_last_cell_never_changes_bytes(self):
        d,m=document()
        for values in ([20]*7+[float('nan')],[20]*7+[65536],[20]*7+[-20]):
            with self.assertRaises(ValueError):value_preview(d.data,m,values)
            self.assertEqual(d.data,d.original);self.assertFalse(d.undo_stack)
        for indexes in ([-1],[8],[True],[0,0]):
            with self.assertRaises(ValueError):operation_preview(d.data,m,'Add',5,indexes)

    def test_csv_roundtrip_shape_and_nonfinite_errors(self):
        d,m=document();p=csv_preview(d.data,m,'1,2,3,4\n5,6,7,8\n');apply_table_preview(d,p)
        self.assertEqual(map_values(d.data,m),list(range(1,9)))
        for text in ('1,2\n3,4','a,2,3,4\n5,6,7,8','1,2,3,4\n5,6,7,nan','1,2,3,4\n5,6,7,inf'):
            with self.assertRaises(ValueError):csv_preview(d.data,m,text)

    def test_interpolation_uses_current_axis_spacing(self):
        d,m=document();p=interpolation_preview(d.data,m,rows=[0]);apply_table_preview(d,p)
        self.assertEqual(map_values(d.data,m),[10,18,32,40,20,80,60,100])
        d.undo();d.edit(42,struct.pack('>h',20))
        apply_table_preview(d,interpolation_preview(d.data,m,rows=[0]))
        self.assertEqual(map_values(d.data,m)[:4],[10,25,32,40])

    def test_column_interpolation_and_reversed_display(self):
        d,m=document();m.update(rows=4,columns=1);m.pop('x_axis');m['y_axis']={'values':[100,50,25,0],'display_backwards':True}
        p=interpolation_preview(d.data,m);apply_table_preview(d,p)
        self.assertEqual(map_values(d.data,m),[10,25,32,40])
        with self.assertRaises(ValueError):interpolation_preview(d.data,m,rows=[0])

    def test_stale_binary_and_definitions_refused(self):
        d,m=document();p=operation_preview(d.data,m,'Set',40,definitions=d.definitions)
        d.edit(0,b'X');before=bytes(d.data)
        with self.assertRaises(ValueError):apply_table_preview(d,p)
        self.assertEqual(d.data,before)
        d.undo();m['factor']=2
        with self.assertRaises(ValueError):apply_table_preview(d,p)
        self.assertEqual(d.data,d.original)

    def test_axis_signed_big_endian_and_shared_storage(self):
        d,m=document();other=copy.deepcopy(m);other.update(id='other',name='Shared map',address=64);d.definitions['maps'].append(other)
        p=axis_preview(d.data,m,'x_axis',[-2,8,13,18],d.definitions)
        self.assertEqual(p['shared_maps'],[m['name'],'Shared map']);apply_table_preview(d,p)
        self.assertEqual(list(differences(d.original,d.data)),[(43,44)])
        refresh_axes(d.data,d.definitions);self.assertEqual(other['x_axis']['values'],[-2,8,13,18])
        self.assertEqual(struct.unpack_from('>h',d.data,42)[0],20)
        d.undo();refresh_axes(d.data,d.definitions);self.assertEqual(m['x_axis']['values'],[-2,3,13,18])
        d.redo();self.assertEqual(axis_values(d.data,m,'x_axis'),[-2,8,13,18])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'axis.ocproj';d.save_project(path);loaded=Document.load_project(path)
            self.assertEqual(axis_values(loaded.data,loaded.definitions['maps'][0],'x_axis'),[-2,8,13,18]);loaded.undo();self.assertEqual(loaded.data,d.original)

    def test_axis_metadata_and_storage_guards(self):
        d,m=document()
        for key,val in [('type','u64'),('factor',0),('address',127),('endian','native')]:
            bad=copy.deepcopy(d.definitions);bad['maps'][0]['x_axis'][key]=val
            with self.assertRaises(ValueError):validate_definitions(bad,len(d.data))
        del m['x_axis']['type']
        with self.assertRaises(ValueError):axis_preview(d.data,m,'x_axis',[1,2,3,4],d.definitions)
        self.assertEqual(d.data,d.original)

    def test_map_encoding_refuses_stored_rounding_outside_limits(self):
        d,m=document();m.update(factor=2,minimum=1,maximum=19)
        with self.assertRaises(ValueError):value_preview(d.data,m,[19]*8)
        m.update(factor=1e-320)
        with self.assertRaises(ValueError):value_preview(d.data,m,[10]*8)

    def test_bank_copy_checks_definitions_axes_and_one_step_undo(self):
        data=bytearray(0x80000);maps=[]
        for i,base in enumerate((0x50000,0x60000,0x70000)):
            data[base+1:base+12]=SIGNATURE
            m=copy.deepcopy(definitions()['maps'][0]);m.update(id=str(i),address=base+0x100,factor=1,offset=0,unit='mg/st')
            m['x_axis']={'address':base+0x84,'type':'u16','endian':'little','factor':1,'offset':0,'values':[1,2,3,4]}
            struct.pack_into('<6H',data,base+0x80,0xec00,4,1,2,3,4);struct.pack_into('<8H',data,base+0x100,*([10+i]*8));maps.append(m)
        d=Document(data);d.definitions={'schema':'opencal.definitions','version':1,'maps':maps}
        p=bank_copy_preview(d.data,maps[0],d.definitions);self.assertEqual(p['destination_banks'],2);apply_table_preview(d,p)
        for m in maps:self.assertEqual(map_values(d.data,m),[10]*8)
        self.assertEqual(len(d.undo_stack),1);d.undo();self.assertEqual(d.data,data)
        d.edit(0x60084,b'\x02')
        with self.assertRaises(ValueError):bank_copy_preview(d.data,maps[0],d.definitions)
        self.assertEqual(len(d.undo_stack),1)
        d.undo();maps[2]['factor']=2
        with self.assertRaises(ValueError):bank_copy_preview(d.data,maps[0],d.definitions)

    def test_damaged_undo_redo_stacks_do_not_load(self):
        d,m=document();d.edit(10,b'A');d.edit(12,b'B');d.undo()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'history.ocproj';d.save_project(p);good=json.loads(p.read_text())
            for stack,field in [('undo',1),('undo',2),('redo',1)]:
                bad=copy.deepcopy(good);bad[stack][0][field]='ff';p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):Document.load_project(p)
            bad=copy.deepcopy(good);bad['undo']=[];p.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):Document.load_project(p)
