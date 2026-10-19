import tkinter as tk,unittest
from unittest.mock import patch
from opencal.workbench import App
from opencal.core import Document
from opencal.hex_view import scroll,render,visible_rows,select_byte


class HexTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.app=App(self.root);self.app.doc=Document(bytes(range(256))*2048)
        self.app.refresh();self.app.tabs.select(self.app.hex_tab);self.root.update();render(self.app)
    def tearDown(self):self.root.destroy()

    def test_filewide_scrollbar_reaches_end_and_start(self):
        scroll(self.app,'moveto',1);last=len(self.app.doc.data)-16
        self.assertIn(f'{last:08X}',self.app.hex.get('1.0','end'))
        self.assertEqual(float(self.app.hex_scroll.get()[1]),1)
        scroll(self.app,'moveto',0);self.assertEqual(self.app.page,0)
        self.assertLess(float(self.app.hex_scroll.get()[1]),.01)
        self.assertEqual(self.app.doc.data,self.app.doc.original)

    def test_wheel_and_keyboard_cross_old_page_boundary(self):
        for _ in range(15):self.app.hex.event_generate('<MouseWheel>',delta=-120)
        self.assertGreater(self.app.page,512)
        before=self.app.page;scroll(self.app,'scroll',1,'pages');self.assertGreater(self.app.page,before)
        scroll(self.app,'scroll',-100000,'pages');self.assertEqual(self.app.page,0)

    def test_go_click_edit_and_undo_select_correct_byte(self):
        self.app.address.set('0x12345');self.app.goto();self.root.update();self.assertEqual(self.app.page,0x12340)
        # Click the third byte's rendered position, then edit through the real dialog command.
        box=self.app.hex.bbox('1.16');self.assertIsNotNone(box);select_byte(self.app,box[0]+2,box[1]+2)
        self.assertEqual(self.app.address.get(),'0x12342')
        with patch('opencal.gui.sd.askstring',return_value='FF'):self.app.edit_hex()
        self.assertEqual(self.app.doc.data[0x12342],255);self.assertTrue(self.app.hex.tag_ranges('changed'))
        self.app.undo();self.assertEqual(self.app.doc.data,self.app.doc.original)

    def test_short_bin_resize_and_last_partial_line(self):
        self.app.doc=Document(b'abcde');self.app.page=100;render(self.app)
        self.assertEqual(self.app.page,0);self.assertIn('61 62 63 64 65',self.app.hex.get('1.0','end'))
        self.root.geometry('1080x700');self.root.update();self.assertEqual(self.app.hex_scroll.get(),(0.0,1.0))
