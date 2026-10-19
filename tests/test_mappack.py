import unittest
from opencal.mappack import import_mappack,decode_json,upgrade_legacy_axes
from opencal.core import map_values


class MappackTests(unittest.TestCase):
    def test_actual_export_latin1_and_utf8_bom(self):
        self.assertEqual(decode_json(b'{"Name":"temperature \xb0C"}')['Name'],'temperature °C')
        self.assertEqual(decode_json(b'\xef\xbb\xbf{"maps":[]}'),{'maps':[]})
    def entry(self):
        return {'Name':'Synthetic map','Rows':'2','Columns':'2','DataOrg':'eLoHi','bSigned':'1',
                'Fieldvalues.StartAddr.Cpu':'$10','Fieldvalues.Factor':'0.5','Fieldvalues.Offset':'-1',
                'AxisX.DataAddr.Cpu':'$4','AxisX.Factor':'0.1','AxisX.DataOrg':'eLoHi'}

    def test_flat_and_nested_roundtrip(self):
        data=bytearray(64); data[4:8]=bytes.fromhex('0a 00 14 00'); data[16:24]=bytes.fromhex('fe ff 04 00 06 00 08 00')
        doc,skipped=import_mappack({'maps':[self.entry()]},data)
        self.assertEqual(skipped,[]); m=doc['maps'][0]
        self.assertEqual(map_values(data,m),[-2,1,2,3]); self.assertEqual(m['x_axis']['values'],[1,2])
        entry=self.entry(); del entry['Fieldvalues.StartAddr.Cpu']; entry['Fieldvalues']={'StartAddr':{'Cpu':'0x10'},'Factor':'0.5','Offset':'-1'}
        nested,_=import_mappack([entry],data); self.assertEqual(nested['maps'][0]['address'],16)

    def test_legacy_import_recovers_axis_encoding(self):
        doc,_=import_mappack([self.entry()],bytes(64));axis=doc['maps'][0]['x_axis']
        for key in ('type','endian','factor','offset'):del axis[key]
        upgrade_legacy_axes(doc,bytes(64))
        self.assertEqual(axis['type'],'u16');self.assertEqual(axis['factor'],.1)

    def test_unsupported_fields_are_explained(self):
        data=bytes(64); entries=[self.entry()]
        for key,value in [('DataOrg','unknown'),('Rows','1.5'),('SkipBytes','2'),('Fieldvalues.StartAddr.Cpu','$100'),('AxisX.DataAddr.Cpu','$100')]:
            bad=self.entry(); bad[key]=value; entries.append(bad)
        result,skipped=import_mappack({'maps':entries},data)
        self.assertEqual(len(result['maps']),1); self.assertEqual(len(skipped),5)


if __name__=='__main__': unittest.main()
