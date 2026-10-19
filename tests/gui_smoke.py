"""Real Tk widget smoke test using original synthetic data; no mouse automation."""
import tempfile
from pathlib import Path
import tkinter as tk
from unittest.mock import patch
from opencal.workbench import App
from opencal.core import Document
from tests.test_core import definitions

root=tk.Tk(); root.withdraw(); app=App(root)
app.doc=Document(b'OCAL'+bytes(508)); app.doc.definitions=definitions(); app.refresh(); root.update()
assert '4F 43 41 4C' in app.hex.get('1.0','end')
app.address.set('0x10')
with patch('opencal.gui.sd.askstring',return_value='64 00'):
    app.edit_hex()
assert app.doc.data[16:18]==b'\x64\0'
app.undo(); assert app.doc.data[16:18]==bytes(2)
app.redo(); assert app.doc.data[16:18]==b'\x64\0'
app.maps.selection_set('0'); app.view_map(); root.update()
with patch('opencal.gui.sd.askstring',return_value='Profile 1'):
    app.capture()
assert 'Profile 1' in app.doc.profiles
app.identify(); assert 'TEST ONLY' in app.analysis.get('1.0','end')
with tempfile.TemporaryDirectory() as temp:
    project=str(Path(temp)/'codex test.ocproj')
    with patch('opencal.gui.fd.asksaveasfilename',return_value=project): app.save_project()
    with patch('opencal.gui.fd.askopenfilename',return_value=project): app.open_project()
    assert app.doc.data[16:18]==b'\x64\0'
root.destroy()
print('GUI smoke passed: widgets, hex edit, undo/redo, map window/graph, profile, identification, project save/reopen.')

# Optional real-file GUI workflow: never writes the user's BIN.
from tests.private_fixtures import STOCK as stock
if stock.exists():
    root=tk.Tk(); root.withdraw(); app=App(root); app.doc=Document(stock.read_bytes(),stock)
    with patch('opencal.workbench.mb.showinfo'):
        app.discover_edc()
    assert len(app.map_leaf_ids())==71
    app.read_dtcs(); assert len(app.dtc_panel.records)==168
    app.verify_checksums(); assert '"matched": 5' in app.analysis.get('1.0','end')
    data=bytes(app.doc.data); app.doc.edit(0x6c900,bytes([app.doc.data[0x6c900]^1]))
    with patch('opencal.gui.mb.askyesno',return_value=True): app.correct_checksums()
    assert '"status": "matched"' in app.analysis.get('1.0','end')
    app.undo(); app.undo(); assert app.doc.data==data
    pack=stock.parent/'codex stock ZedSuite mappack.json'
    if pack.exists():
        with patch('opencal.gui.fd.askopenfilename',return_value=str(pack)),patch('opencal.gui.mb.showinfo'):
            app.import_defs()
        assert len(app.map_leaf_ids())==71
        app.maps.selection_set('0'); app.view_map(); root.update()
        print('Private JSON workflow passed: all 71 ZedSuite-exported definitions imported and map window rendered.')
    root.destroy()
    print('Private GUI workflow passed: discovery, 168 DTC records, checksums, correction preview/apply and undo; source BIN unchanged.')
