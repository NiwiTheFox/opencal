import struct
import unittest
from opencal.checksums import calculate_2002,SIGNATURE
from opencal.edc15 import dtc_records,discover_heuristic
from tests.test_edc15 import dtc_fixture

class AuditRegressionTests(unittest.TestCase):
 def test_checksum_ranges_reject_partial_rounds(self):
  for data,start,end in [(b'\0'*6,0,4),(b'\0'*8,0,4),(b'\0'*8,2,7)]:
   with self.subTest(start=start,end=end,size=len(data)):
    with self.assertRaises(ValueError):calculate_2002(data,start,end,0,0)
 def test_each_dtc_bank_requires_sufficient_evidence(self):
  data,codes=dtc_fixture()
  data[0x50001:0x5000c]=SIGNATURE
  data[0x4e800:0x4e808]=data[0x6e800:0x6e808]
  with self.assertRaises(ValueError):dtc_records(data)
 def test_overlapping_dtc_candidates_refused(self):
  data,codes=dtc_fixture()
  # The first code's high byte becomes the second candidate's type byte.
  a=0x6f100
  data[a:a+8]=data[0x6e800:0x6e808]
  data[a+8:a+11]=b'\x23'+struct.pack('<H',codes[1])
  with self.assertRaises(ValueError):dtc_records(data)
 def test_smoke_selector_requires_checked_index_array(self):
  data=bytearray(0x80000);data[0x70001:0x7000c]=SIGNATURE
  p=0x6d000
  axes=struct.pack('<HH16H',0xf900,16,*range(0,4800,300))+struct.pack('<HH13H',0xda00,13,*range(0,1300,100))
  selector=struct.pack('<HH2H2H',0xc100,2,2731,3731,0xffff,0xffff)
  data[p:p+len(axes)+len(selector)+832]=axes+selector+struct.pack('<416H',*([2000]*416))
  maps=discover_heuristic(data)['maps']
  self.assertFalse(any(m.get('selector_address')==p+len(axes) for m in maps))


 def test_independent_compiled_csharp_vectors(self):
  import json
  from pathlib import Path
  from opencal.checksums import calculate_tdi41
  fixture=json.loads((Path(__file__).parent/'checksum-csharp-vectors.json').read_text())
  data=bytes.fromhex(fixture['data_hex'])
  for v in fixture['tdi41_2002']:
   self.assertEqual(calculate_2002(data,v['start'],v['end'],*v['seeds'],v['first']),v['expected'])
  for v in fixture['tdi41']:
   self.assertEqual(calculate_tdi41(data,v['start'],v['end'],*v['seeds']),v['expected'])
