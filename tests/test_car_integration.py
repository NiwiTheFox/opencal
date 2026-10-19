"""Optional private fixtures. Never distribute the user's ECU binaries."""
import unittest
from pathlib import Path
from opencal.checksums import inspect,correct
from opencal.core import digest,differences,Document,validate_definitions
from opencal.edc15 import discover,dtc_records,disable_dtc,restore_dtc

from tests.private_fixtures import STOCK,V9


@unittest.skipUnless(STOCK.exists() and V9.exists(),'Private user fixtures unavailable')
class CarIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock=STOCK.read_bytes(); cls.v9=V9.read_bytes()

    def test_original_identity_and_sums(self):
        self.assertEqual(digest(self.stock),'38717815ccaf28e926640b63c888044b6c481cdbf510ed24ed004ba0aa53f72f')
        self.assertEqual(digest(self.v9),'521a8779d571224d89ed95f5a31183e1e6d2022986e21e117d2e2922b83521bf')
        self.assertEqual(inspect(self.stock)['matched'],5); self.assertEqual(inspect(self.v9)['matched'],11)

    def test_oracle_correction(self):
        for orig,expected in [(self.stock,'d443f96997fede4cc622b4b00f46ee4094fe58577e243783242a09fe3fc0ce4e'),(self.v9,'226c79c7334e7f31329dc58ab02057a12c51c3a6c78a6841c8ae5f201187d4ad')]:
            data=bytearray(orig); data[0x6c900]^=1
            fixed=correct(data,orig); self.assertEqual(digest(fixed),expected)
            self.assertEqual(inspect(fixed)['status'],'matched')

    def test_map_addresses_cross_checked_in_zedsuite_ui(self):
        defs=validate_definitions(discover(self.stock),len(self.stock)); maps={m['address']:m for m in defs['maps']}
        for address,name in [(0x6c8f6,'Driver wish'),(0x6cf80,'Torque limiter'),(0x6d0c2,'Smoke limiter'),(0x740f6,'SVRL'),(0x74376,'BIP'),(0x76cbe,'Boost target'),(0x76fca,'N75')]:
            self.assertIn(name,maps[address]['name'])
            self.assertEqual(maps[address]['verification'],'candidate')

    def test_dtc_bank_edit_preservation_and_checksums(self):
        self.assertEqual(len(dtc_records(self.stock)),168); self.assertEqual(len(dtc_records(self.v9)),504)
        for orig in (self.stock,self.v9):
            selected=next(r for r in dtc_records(orig) if r['enabled'])
            result,records=disable_dtc(orig,selected['vag_code'])
            allowed={a for r in records for a in range(r['address'],r['address']+5)}
            changed={a for start,end in differences(orig,result) for a in range(start,end)}
            self.assertTrue(changed<=allowed)
            self.assertEqual(restore_dtc(result,orig,selected['vag_code']),orig)
            self.assertEqual(inspect(correct(result,orig))['status'],'matched')

    def test_sources_unchanged(self):
        self.assertEqual(STOCK.read_bytes(),self.stock); self.assertEqual(V9.read_bytes(),self.v9)


if __name__=='__main__': unittest.main()
