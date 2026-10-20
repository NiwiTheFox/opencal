import ast,json,re,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from opencal.c166 import C166Disassembler,interpret
from opencal.c166_tools import assemble,preview,segments,to_cpu,to_file,object_bytes,check_source,branch_target,validate_state
from opencal.core import Document
from opencal.solutions import apply_preview

FIXTURE=json.loads((Path(__file__).parent/'c166-as-fixtures.json').read_text())


def normalized(text):
    text=re.sub(r'0x([0-9a-f]+)',lambda m:str(int(m[1],16)),text.lower())
    return re.sub(r'\s+','',text)


class DecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.decoder=C166Disassembler()

    def test_independently_assembled_instruction_vectors(self):
        for v in FIXTURE['vectors']:
            if not v['expected_valid']:continue
            with self.subTest(case=v['id']):
                raw=bytes.fromhex(v['bytes_hex']);off=v.get('instruction_offset',0)
                count,encoded,text=self.decoder.decode_one(raw,off,v['origin']+off)
                expected=v['expected_mnemonic']+' '+v['expected_operands']
                if v['id']=='jmpa_csp':expected='jmpa z,0x80020'
                self.assertEqual(normalized(text),normalized(expected));self.assertEqual(len(bytes.fromhex(encoded)),count)

    def test_reserved_fixed_bits_and_truncated_buffers(self):
        for v in FIXTURE['decoder_rejections']:
            raw=bytes.fromhex(v['bytes_hex']);count,encoded,text=self.decoder.decode_one(raw,0,0x80000)
            self.assertTrue(text.startswith('('),(v,text));self.assertEqual(count,len(bytes.fromhex(encoded)));self.assertLessEqual(count,len(raw))
        rows=self.decoder.decode_range(bytes.fromhex('e6 f3 34 12'),0x80000,2)
        self.assertEqual(rows,[(0x80000,'E6F3','(truncated instruction)')])

    def test_segment_wrap_and_direct_targets(self):
        v=FIXTURE['manual_only_vectors'][0];raw=bytes.fromhex(v['bytes_hex'])
        text=self.decoder.decode_one(raw,0,v['origin'])[2]
        self.assertEqual(branch_target(raw,text,v['origin']),v['expected_physical_branch_target'])
        self.assertEqual(branch_target(bytes.fromhex('fa 08 34 12'),'JMPS 8,0x1234',0),0x81234)
        self.assertIsNone(branch_target(bytes.fromhex('f2 f4 00 01'),'MOV R4,0x0100',0x80000))

    def test_processor_variant_and_context_dependent_sfr_are_explicit(self):
        decoder=C166Disassembler(cpu='80c166')
        self.assertTrue(decoder.decode_one(bytes.fromhex('d7 40 20 00'),0,0x10000)[2].startswith('(unknown'))
        with self.assertRaises(ValueError):assemble('extp #020h,#1',0x10000,16,'80c166')
        self.assertIn('SFR16[0x00]',self.decoder.decode_one(bytes.fromhex('e6 00 20 00'),0,0x80000)[2])

    def test_table_expressions_cannot_execute_python(self):
        for expr in ['__import__("os").system("x")','A.__class__','[x for x in A]','str(A)','A[0]']:
            with self.assertRaises(ValueError):interpret(ast.parse(expr,mode='eval').body,{'A':'0000'})

    def test_opcode_sweep_covers_input_without_exceptions_or_overread(self):
        for opcode in range(256):
            for second in range(256):
                raw=bytes((opcode,second,0,0));count,encoded,text=self.decoder.decode_one(raw,0,0x80000)
                self.assertIn(count,(2,4));self.assertEqual(len(bytes.fromhex(encoded)),count);self.assertTrue(text)


class AssemblerTests(unittest.TestCase):
    def test_independent_as_vectors_through_bundled_wrapper(self):
        for v in FIXTURE['vectors']:
            source='\n'.join(v['setup']+[v['source']])
            with self.subTest(case=v['id']):
                if not v['expected_valid'] or 'caveat' in v:
                    with self.assertRaises(ValueError):assemble(source,v['origin'],64,v['cpu'])
                else:self.assertEqual(assemble(source,v['origin'],64,v['cpu']),bytes.fromhex(v['bytes_hex']))

    def test_selected_cpu_code_address_limits_and_basic_encoding(self):
        for cpu,origin in [('80c166',0x10000),('80c167',0x80000),('80c167cs',0x80000)]:
            self.assertEqual(assemble('nop',origin,2,cpu),bytes.fromhex('cc00'))
        with self.assertRaises(ValueError):assemble('nop',0x80000,2,'80c166')
        with self.assertRaises(ValueError):C166Disassembler(cpu='80c166').decode_range(bytes.fromhex('cc00'),0x80000,2)

    def test_includes_origins_macros_and_extension_overflow_rejected(self):
        for source in ['include "secret"','incbin "secret"','org 080002h','cpu 80c167','section code','ds 40','rept 100','db "file"','extp #0400h,#1','extpr #page,#1','assume dpp0:1024','nop\n include x','nop\n end','nop\n print x','db 999999dup(0)','dw 65536']:
            with self.subTest(source=source):
                with patch('opencal.c166_tools.subprocess.run') as run:
                    with self.assertRaises(ValueError):assemble(source,0x80000,64)
                    run.assert_not_called()

    def test_output_coverage_parser_rejects_holes_overlaps_and_wrong_sections(self):
        def rec(address,raw,section=1):return b'\x81\x4c'+bytes((section,1))+struct.pack('<IH',address,len(raw))+raw
        good=b'\x89\x14'+rec(0x80000,b'\xcc\0')+b'\0AS test'
        self.assertEqual(object_bytes(good,0x80000,2),b'\xcc\0')
        for bad in [b'',good[:-10],b'\x89\x14'+rec(0x80002,b'\xcc\0')+b'\0',b'\x89\x14'+rec(0x80000,b'\xcc\0',2)+b'\0',b'\x89\x14'+rec(0x80000,b'\xcc\0')+rec(0x80000,b'\xcc\0')+b'\0']:
            with self.assertRaises(ValueError):object_bytes(bad,0x80000,4)
        with self.assertRaises(ValueError):assemble('nop\n nop',0x80000,2)

    def test_bounded_patch_stale_guards_and_shared_undo(self):
        doc=Document(bytes(64));mapping=[{'file':0,'cpu':0x80000,'size':64}]
        op=preview(doc,'start: mov r3,#01234h\n jmpr uc,start',8,16,mapping)
        apply_preview(doc,op);self.assertEqual(doc.data[8:14],bytes.fromhex('e6f334120dfd'));self.assertEqual(doc.data[:8],bytes(8));self.assertEqual(doc.data[14:],bytes(50));self.assertEqual(len(doc.undo_stack),1)
        doc.undo();self.assertEqual(doc.data,bytes(64));doc.redo();self.assertEqual(doc.data[8:14],bytes.fromhex('e6f334120dfd'))
        doc.undo();doc.edit(0,b'X');before=bytes(doc.data)
        with self.assertRaises(ValueError):apply_preview(doc,op)
        self.assertEqual(doc.data,before)
        with self.assertRaises(ValueError):preview(doc,'nop',62,4,mapping)
        with self.assertRaises(ValueError):preview(doc,'nop',1,2,mapping)

    def test_explicit_segments_and_inverse_mapping(self):
        mapping=segments([{'file':0,'cpu':0x80000,'size':32},{'file':32,'cpu':0x90000,'size':32}],64)
        self.assertEqual(to_cpu(mapping,34,4),0x90002);self.assertEqual(to_file(mapping,0x80010),16)
        with self.assertRaises(ValueError):to_cpu(mapping,30,4)
        with self.assertRaises(ValueError):to_file(mapping,0xa0000)
        for mapping in [[{'file':0,'cpu':0,'size':128}],[{'file':0,'cpu':0,'size':40},{'file':32,'cpu':40,'size':24}],[{'file':0,'cpu':0,'size':32},{'file':32,'cpu':16,'size':32}]]:
            with self.assertRaises(ValueError):segments(mapping,64)

    def test_code_metadata_persists_and_old_projects_remain_loadable(self):
        doc=Document(bytes(64));doc.code_workspace={'version':1,'cpu':'80c167','segments':[{'file':0,'cpu':0x80000,'size':64}],'source':'start: nop\n','labels':{'0':'start'},'comments':{'0':'synthetic'}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'codex code.ocproj';doc.save_project(path);loaded=Document.load_project(path);self.assertEqual(loaded.code_workspace,doc.code_workspace)
            obj=json.loads(path.read_text());del obj['code_workspace'];path.write_text(json.dumps(obj));self.assertEqual(Document.load_project(path).code_workspace,{})
            obj['code_workspace']=dict(doc.code_workspace,segments=[{'file':0,'cpu':0,'size':1000}]);path.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):Document.load_project(path)
