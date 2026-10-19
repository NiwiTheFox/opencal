"""Tk desktop interface; all analysis and editing is local."""
import csv
import json
import struct
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog as fd, messagebox as mb, simpledialog as sd
from .core import Document, read_binary, differences, digest, number, validate_definitions, map_values, identify, scan_axes, atomic_json
from .checksums import inspect as inspect_checksums, correct as correct_checksums
from .edc15 import discover, dtc_records, disable_dtc, restore_dtc
from .multimap import inspect_multimap
from .mappack import import_mappack, decode_json


class App:
    def __init__(self, root):
        self.root = root
        self.doc = None
        self.page = 0
        self.project = None
        self.saved_state = None
        root.title('OpenCal • Offline calibration workbench')
        root.geometry('1180x800')
        root.minsize(850, 600)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TButton', padding=(9, 6))
        toolbar = ttk.Frame(root, padding=8); toolbar.pack(fill='x')
        for label, fn in [('Open BIN', self.open_bin), ('Open project', self.open_project), ('Save project', self.save_project),
                          ('Export BIN…', self.export), ('Undo', self.undo), ('Redo', self.redo)]:
            ttk.Button(toolbar, text=label, command=lambda f=fn: self.run(f)).pack(side='left', padx=3)
        self.status = tk.StringVar(value='Open a BIN file to begin. Originals are preserved. EDC15 discovery and checksum tools are available for matched layouts.')
        ttk.Label(root, textvariable=self.status, padding=10, wraplength=1100).pack(fill='x')
        self.tabs = ttk.Notebook(root); self.tabs.pack(fill='both', expand=True, padx=10, pady=5)
        self.hex_tab = ttk.Frame(self.tabs); self.tabs.add(self.hex_tab, text='Hex inspector')
        self.map_tab = ttk.Frame(self.tabs); self.tabs.add(self.map_tab, text='Maps & definitions')
        self.analysis_tab = ttk.Frame(self.tabs); self.tabs.add(self.analysis_tab, text='Analysis & comparison')
        self.profile_tab = ttk.Frame(self.tabs); self.tabs.add(self.profile_tab, text='Calibration profiles')
        self.ecu_tab = ttk.Frame(self.tabs); self.tabs.add(self.ecu_tab, text='EDC15 tools & DTCs')
        self.build_hex(); self.build_maps(); self.build_analysis(); self.build_profiles()
        self.build_ecu()
        ttk.Button(root, text='OpenCal 0.3 • GPL-3.0-only • Credits & license / no warranty', command=self.about).pack(fill='x')

    def about(self):
        w=tk.Toplevel(self.root); w.title('OpenCal — credits and license'); w.geometry('800x650')
        text=tk.Text(w,wrap='word'); text.pack(fill='both',expand=True)
        folder=Path(__file__).resolve().parent.parent
        text.insert('1.0',(folder/'NOTICE').read_text(encoding='utf-8')+'\n\n'+(folder/'LICENSE').read_text(encoding='utf-8'))
        text.configure(state='disabled')

    def run(self, fn):
        try:
            fn()
        except (ValueError, TypeError, KeyError, OSError, OverflowError, struct.error, IndexError) as exc:
            mb.showerror('OpenCal', str(exc), parent=self.root)

    def need(self):
        if not self.doc:
            raise ValueError('Open a BIN or project first.')
        return self.doc

    def state(self):
        if not self.doc:
            return None
        d = self.doc
        return (digest(d.data), json.dumps(d.definitions, sort_keys=True), tuple((k, digest(v)) for k, v in sorted(d.profiles.items())), len(d.history), digest(d.dtc_reference) if d.dtc_reference is not None else None)

    def can_leave(self):
        return self.state() == self.saved_state or mb.askyesno('Unsaved project', 'Discard unsaved project changes?', parent=self.root)

    def close(self):
        if self.can_leave():
            self.root.destroy()

    def open_bin(self):
        p = fd.askopenfilename(filetypes=[('Binary files', '*.bin *.ori'), ('All files', '*.*')])
        if p and self.can_leave():
            d = Document(read_binary(p), p)
            self.doc = d; self.project = None; self.page = 0
            self.saved_state = None  # New input should be saved as a project.
            self.refresh()

    def open_project(self):
        p = fd.askopenfilename(filetypes=[('OpenCal project', '*.ocproj')])
        if p and self.can_leave():
            d = Document.load_project(p)
            self.doc = d; self.project = p; self.page = 0
            self.saved_state = self.state(); self.refresh()

    def save_project(self):
        d = self.need()
        p = fd.asksaveasfilename(defaultextension='.ocproj', initialfile='codex '+Path(d.source or 'project').stem.removeprefix('codex ')+'.ocproj', filetypes=[('OpenCal project', '*.ocproj')])
        if p:
            # Existing project may be atomically replaced, but never a source BIN.
            protected = d.protected_paths.copy()
            d.protected_paths.discard(str(Path(self.project).resolve()) if self.project else '')
            try:
                d.save_project(p)
            finally:
                d.protected_paths = protected
            self.project = p
            d.protected_paths.add(str(Path(p).resolve()))
            self.saved_state = self.state(); self.refresh()

    def export(self):
        d = self.need()
        checksum=inspect_checksums(d.data)
        if not mb.askyesno('Export analysis binary', f'Checksum status: {checksum["status"]}.\nExport a separate BIN and audit report? Checksum matching does not validate ECU execution or flashing.'):
            return
        p = fd.asksaveasfilename(defaultextension='.bin', initialfile='codex modified-analysis.bin')
        if p:
            d.export(p)
            mb.showinfo('Export complete', f'Created {p}\nAudit: {p}.audit.json\nOriginal preserved. Checksum status: {checksum["status"]}.')

    def undo(self):
        self.need().undo(); self.refresh()

    def redo(self):
        self.need().redo(); self.refresh()

    def build_hex(self):
        bar = ttk.Frame(self.hex_tab, padding=5); bar.pack(fill='x')
        self.address = tk.StringVar(value='0x0')
        ttk.Label(bar, text='Offset (0x hex / decimal)').pack(side='left')
        ttk.Entry(bar, textvariable=self.address, width=14).pack(side='left', padx=4)
        for label, fn in [('Go', self.goto), ('Previous', lambda: self.move(-512)), ('Next', lambda: self.move(512)), ('Edit bytes…', self.edit_hex), ('Find hex…', self.find)]:
            ttk.Button(bar, text=label, command=lambda f=fn: self.run(f)).pack(side='left', padx=2)
        self.hex = tk.Text(self.hex_tab, font=('Consolas', 11), wrap='none', state='disabled', background='#182431', foreground='#d9e5ee', padx=12, pady=12)
        self.hex.pack(fill='both', expand=True)
        self.hex.tag_configure('changed', foreground='#ffcf69', background='#493d28')
        ttk.Label(self.hex_tab, text='512 bytes per page. Yellow bytes differ from original. Edit bytes uses the offset above; enter space-separated hexadecimal bytes.', padding=6).pack(fill='x')

    def goto(self):
        a = number(self.address.get())
        if not 0 <= a < len(self.need().data):
            raise ValueError('Offset outside binary.')
        self.page = a // 16 * 16; self.refresh()

    def move(self, delta):
        self.page = max(0, min((len(self.need().data) - 1) // 16 * 16, self.page + delta))
        self.address.set(hex(self.page)); self.refresh()

    def edit_hex(self):
        d = self.need(); a = number(self.address.get())
        s = sd.askstring('Edit bytes', f'Overwrite bytes at 0x{a:X} with hex:', parent=self.root)
        if s is not None:
            d.edit(a, bytes.fromhex(s)); self.refresh()

    def find(self):
        d = self.need(); s = sd.askstring('Find hex bytes', 'Hex pattern (for example 00 FF 10):')
        if s:
            a = d.find(bytes.fromhex(s), number(self.address.get()))
            if a < 0:
                mb.showinfo('Search', 'Pattern not found from current offset.')
            else:
                self.address.set(hex(a)); self.goto()

    def build_maps(self):
        bar = ttk.Frame(self.map_tab, padding=5); bar.pack(fill='x')
        for label, fn in [('Import JSON', self.import_defs), ('Export JSON', self.export_defs), ('Definition editor', self.edit_defs), ('View selected map', self.view_map)]:
            ttk.Button(bar, text=label, command=lambda f=fn: self.run(f)).pack(side='left', padx=3)
        self.maps = ttk.Treeview(self.map_tab, columns=('address', 'shape', 'status', 'category'), show='tree headings')
        self.maps.heading('#0', text='Map name')
        for c in ('address', 'shape', 'status', 'category'):
            self.maps.heading(c, text=c.title()); self.maps.column(c, width=140)
        self.maps.pack(fill='both', expand=True)
        self.maps.bind('<Double-1>', lambda e: self.run(self.view_map))
        ttk.Label(self.map_tab, text='Only supplied open definitions are used. Verification labels come from their author; importing a label does not prove ECU compatibility.', padding=8, wraplength=1000).pack(fill='x')

    def import_defs(self):
        d = self.need(); p = fd.askopenfilename(filetypes=[('Definitions JSON', '*.json')])
        if p:
            if Path(p).stat().st_size > 4 * 1024 * 1024:
                raise ValueError('Definition JSON exceeds 4 MiB.')
            obj=decode_json(Path(p).read_bytes())
            if isinstance(obj,dict) and obj.get('schema')=='opencal.definitions':
                defs=validate_definitions(obj,len(d.data))
            else:
                defs,skipped=import_mappack(obj,d.data,source=f'User import: {Path(p).name}')
                mb.showinfo('Mappack import',f'Imported {len(defs["maps"])} candidates; skipped {len(skipped)} unsupported maps.\n'+json.dumps(skipped[:8],indent=2))
            d.definitions = defs; d.protected_paths.add(str(Path(p).resolve())); self.refresh()

    def export_defs(self):
        d = self.need(); p = fd.asksaveasfilename(defaultextension='.json')
        if p:
            atomic_json(d.protect(p), d.definitions)

    def edit_defs(self):
        d = self.need(); w = tk.Toplevel(self.root); w.title('Open definition editor — validated JSON'); w.geometry('850x650')
        text = tk.Text(w, font=('Consolas', 10), undo=True); text.pack(fill='both', expand=True)
        text.insert('1.0', json.dumps(d.definitions, indent=2))
        def apply():
            defs = validate_definitions(json.loads(text.get('1.0', 'end')), len(d.data))
            d.definitions = defs; self.refresh(); w.destroy()
        ttk.Button(w, text='Validate and apply', command=lambda: self.run(apply)).pack(pady=6)

    def view_map(self):
        d = self.need(); selected = self.maps.selection()
        if not selected:
            raise ValueError('Select a map.')
        m = d.definitions['maps'][int(selected[0])]
        w = tk.Toplevel(self.root); w.title(f'{m["name"]} • {m["verification"]}'); w.geometry('1000x680')
        ttk.Label(w, text=f'{m["unit"]} | {m["type"]} {m["endian"]} | factor {m["factor"]}, offset {m["offset"]} | source: {m["source"]}', padding=6).pack(fill='x')
        cols = [str(i) for i in range(m['columns'])]
        tree = ttk.Treeview(w, columns=cols, show='headings', height=10)
        for col in cols:
            x=m.get('x_axis',{}).get('values',[])
            tree.heading(col, text=f'{x[int(col)]:g}' if x else f'Column {int(col)+1}'); tree.column(col, width=110, stretch=False)
        tree.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(w, orient='horizontal', command=tree.xview); scroll.pack(fill='x'); tree.configure(xscrollcommand=scroll.set)
        canvas = tk.Canvas(w, height=200, background='#182431'); canvas.pack(fill='x')
        ttk.Label(w, text='Cells show modified (original). Double-click to edit physical value. Graph shows flattened row-major values; axes use sample indices.', padding=5).pack(fill='x')
        if 'y_axis' in m:
            ttk.Label(w,text='Row axis: '+', '.join(f'{v:g}' for v in m['y_axis']['values']),wraplength=950,padding=4).pack(fill='x')
        def redraw():
            tree.delete(*tree.get_children()); vals = map_values(d.data, m); orig = map_values(d.original, m)
            for row in range(m['rows']):
                base = row * m['columns']
                tree.insert('', 'end', iid=str(row), values=[f'{vals[i]:g} ({orig[i]:g})' for i in range(base, base+m['columns'])])
            canvas.delete('all'); points = vals[:4096]
            if points and all(__import__('math').isfinite(v) for v in points):
                lo, hi = min(points), max(points); coords=[]
                for i, v in enumerate(points):
                    coords.extend((20 + i * 920 / max(1,len(points)-1), 175 - (v-lo)*145/max(hi-lo, 1e-12)))
                if len(coords) >= 4:
                    canvas.create_line(*coords, fill='#63d8c8', width=2)
                canvas.create_text(12, 12, text=f'{lo:g} … {hi:g} {m["unit"]} (first 4096 cells)', anchor='nw', fill='white')
        def edit(event):
            row = tree.identify_row(event.y); col = tree.identify_column(event.x)
            if not row or col == '#0':
                return
            index = int(row)*m['columns'] + int(col[1:])-1
            v = sd.askfloat('Edit physical value', f'New value ({m["unit"]}):', initialvalue=map_values(d.data,m)[index], parent=w)
            if v is not None:
                d.set_map_cell(m,index,v); redraw(); self.refresh()
        tree.bind('<Double-1>', lambda e: self.run(lambda: edit(e)))
        def csv_export():
            p = fd.asksaveasfilename(defaultextension='.csv')
            if p:
                d.protect(p)
                vals = map_values(d.data,m)
                with open(p,'x',newline='',encoding='utf-8') as f:
                    writer=csv.writer(f)
                    for r in range(m['rows']):
                        writer.writerow(vals[r*m['columns']:(r+1)*m['columns']])
        ttk.Button(w,text='Export physical values as CSV',command=lambda:self.run(csv_export)).pack(pady=4)
        redraw()

    def build_analysis(self):
        bar = ttk.Frame(self.analysis_tab, padding=5); bar.pack(fill='x')
        for label, fn in [('Identify ECU', self.identify), ('Compare BIN…', self.compare), ('Scan axis candidates', self.scan), ('Export audit JSON', self.audit)]:
            ttk.Button(bar,text=label,command=lambda f=fn:self.run(f)).pack(side='left',padx=3)
        self.analysis = tk.Text(self.analysis_tab, font=('Consolas',10), wrap='word', state='disabled'); self.analysis.pack(fill='both', expand=True)

    def build_ecu(self):
        bar=ttk.Frame(self.ecu_tab,padding=5); bar.pack(fill='x')
        for label,fn in [('Discover EDC15 maps',self.discover_edc),('Verify checksums',self.verify_checksums),('Correct checksums…',self.correct_checksums),('Read DTC records',self.read_dtcs)]:
            ttk.Button(bar,text=label,command=lambda f=fn:self.run(f)).pack(side='left',padx=2)
        self.dtc_tree=ttk.Treeview(self.ecu_tab,columns=('code','vag','address','bank','state','description'),show='headings')
        for c,width in [('code',70),('vag',70),('address',85),('bank',85),('state',90),('description',500)]:
            self.dtc_tree.heading(c,text=c.title()); self.dtc_tree.column(c,width=width)
        self.dtc_tree.pack(fill='both',expand=True)
        bottom=ttk.Frame(self.ecu_tab,padding=5); bottom.pack(fill='x')
        for label,fn in [('Disable selected code in matching banks…',self.disable_selected_dtc),('Restore exact original record…',self.restore_selected_dtc)]:
            ttk.Button(bottom,text=label,command=lambda f=fn:self.run(f)).pack(side='left',padx=3)
        ttk.Label(self.ecu_tab,text='Classic 8-byte table subset only. Detection is structural, not a live diagnostic scan. Edits remain in memory until separate export.',padding=8,wraplength=1050).pack(fill='x')

    def discover_edc(self):
        d=self.need(); defs=validate_definitions(discover(d.data),len(d.data))
        current={m['id']:m for m in d.definitions['maps']}
        manual_addresses={number(m['address']) for m in current.values() if not m['id'].startswith('edc15-')}
        replaced=sum(m['id'] in current for m in defs['maps'])
        if replaced and not mb.askyesno('Replace detected definitions',f'Replace {replaced} existing detector definitions? Other manual definitions remain.'):
            return
        current.update({m['id']:m for m in defs['maps'] if m['address'] not in manual_addresses})
        d.definitions={**d.definitions,'maps':list(current.values())}
        self.refresh(); self.tabs.select(self.map_tab)
        mb.showinfo('Discovery',f'{len(defs["maps"])} candidate definitions found. Names and scaling are heuristic and need independent verification. Includes unclassified structures; this is not the full ZedSuite detector.')

    def verify_checksums(self):
        self.output(json.dumps(inspect_checksums(self.need().data),indent=2))

    def correct_checksums(self):
        d=self.need(); result=correct_checksums(d.data,d.original)
        count=sum(a!=b for a,b in zip(d.data,result))
        if not count:
            mb.showinfo('Checksums','All supported region sums already match. No bytes changed.'); return
        if mb.askyesno('Checksum correction preview',f'Change {count} checksum bytes in the working copy? Protected data outside checksum fields will stay unchanged. Undo is available.'):
            d.edit(0,result,'EDC15 standard V4.1 checksum correction'); self.refresh(); self.verify_checksums()

    def read_dtcs(self):
        records=dtc_records(self.need().data)
        self.dtc_tree.delete(*self.dtc_tree.get_children())
        for i,r in enumerate(records):
            self.dtc_tree.insert('','end',iid=str(i),values=(r['code'],r['vag_code'],hex(r['address']),hex(r['codeblock_base']),'Enabled' if r['enabled'] else 'Disabled',r['description']))
        self.tabs.select(self.ecu_tab)

    def selected_dtc(self):
        selection=self.dtc_tree.selection()
        if not selection: raise ValueError('Read DTC records and select a code first.')
        return int(self.dtc_tree.item(selection[0],'values')[1])

    def disable_selected_dtc(self):
        d=self.need(); code=self.selected_dtc(); result,records=disable_dtc(d.data,code)
        if mb.askyesno('DTC edit preview',f'Disable VAG code {code} in {len(records)} matching records? This changes fault monitoring in the working copy. Review the result and correct checksums before export.'):
            d.edit(0,result,f'Disable DTC {code}'); self.refresh(); self.read_dtcs()

    def restore_selected_dtc(self):
        d=self.need(); code=self.selected_dtc(); result=restore_dtc(d.data,d.original,code)
        if mb.askyesno('Restore exact original',f'Restore original monitoring bytes for VAG code {code}? If the input was already disabled, the restored state will still be disabled.'):
            d.edit(0,result,f'Restore original DTC {code}'); self.refresh(); self.read_dtcs()

    def output(self, text):
        self.analysis.configure(state='normal'); self.analysis.delete('1.0','end'); self.analysis.insert('1.0',text); self.analysis.configure(state='disabled')
        self.tabs.select(self.analysis_tab)

    def identify(self):
        d = self.need(); matches = identify(d.original,d.definitions)
        self.output(json.dumps(matches,indent=2) if matches else 'ECU UNKNOWN. No supplied signature matched. Size and filename are not identification evidence.\nImport an independently verified definition to add exact-byte signatures.')

    def compare(self):
        d = self.need(); p=fd.askopenfilename()
        if p:
            other=read_binary(p); ranges=list(differences(d.data,other)); d.protected_paths.add(str(Path(p).resolve()))
            self.output(f'Working: {len(d.data)} bytes | Other: {len(other)} bytes\n{len(ranges)} differing ranges (end exclusive)\n' + '\n'.join(f'0x{a:08X} — 0x{b:08X} ({b-a} bytes)' for a,b in ranges[:1000]) + ('\nDisplay limited to 1000 ranges.' if len(ranges)>1000 else ''))

    def scan(self):
        d = self.need()
        start=sd.askstring('Scan start','Start byte offset:',initialvalue='0x0')
        if start is None: return
        end=sd.askstring('Scan end','End offset (exclusive):',initialvalue=hex(len(d.data)))
        if end is None: return
        results=scan_axes(d.data,number(start),number(end))
        self.output('EXPERIMENTAL: generic monotonic axis candidates, not EDC15 map discovery. Maximum 200 results.\n\n'+json.dumps(results,indent=2))

    def audit(self):
        d=self.need(); p=fd.asksaveasfilename(defaultextension='.json')
        if p: atomic_json(d.protect(p),d.report())

    def build_profiles(self):
        ttk.Label(self.profile_tab,text='Named calibration snapshots. These do not implement ECU multimap switching or ECU code patches.',padding=10).pack(fill='x')
        self.profiles=tk.Listbox(self.profile_tab,font=('Consolas',11)); self.profiles.pack(fill='both',expand=True,padx=8)
        bar=ttk.Frame(self.profile_tab,padding=8); bar.pack(fill='x')
        for label,fn in [('Capture working copy',self.capture),('Compare selected',self.compare_profile),('Restore selected',self.restore_profile)]:
            ttk.Button(bar,text=label,command=lambda f=fn:self.run(f)).pack(side='left',padx=3)
        ttk.Button(bar,text='Inspect ECU switching evidence',command=lambda:self.run(lambda:self.output(json.dumps(inspect_multimap(self.need().data),indent=2)))).pack(side='left',padx=3)

    def capture(self):
        d=self.need(); name=sd.askstring('Capture profile','Unique profile name:')
        if name:
            if name in d.profiles: raise ValueError('Profile name already exists.')
            d.profiles[name]=bytes(d.data); self.refresh()

    def selected_profile(self):
        d=self.need(); selected=self.profiles.curselection()
        if not selected: raise ValueError('Select a profile.')
        return d.profiles[self.profiles.get(selected[0])]

    def compare_profile(self):
        data=self.selected_profile(); ranges=list(differences(self.need().data,data))
        self.output('Profile comparison (end exclusive)\n'+json.dumps(ranges[:1000],indent=2))

    def restore_profile(self):
        data=self.selected_profile()
        if mb.askyesno('Restore profile','Replace working values with this profile? This operation can be undone.'):
            self.doc.edit(0,data,'Restore calibration profile'); self.refresh()

    def refresh(self):
        d=self.need()
        self.status.set(f'{Path(d.source).name if d.source else "Embedded original"} • {len(d.data):,} bytes • {sum(a != b for a,b in zip(d.original,d.data)):,} changed bytes • Checksums: use Verify under EDC15 tools')
        if hasattr(self,'dtc_tree'): self.dtc_tree.delete(*self.dtc_tree.get_children())
        if hasattr(self,'render_hex'):self.render_hex()
        if not getattr(self,'_filtering',False):
            self.maps.delete(*self.maps.get_children())
            for i,m in enumerate(d.definitions['maps']):
                self.maps.insert('','end',iid=str(i),text=m['name'],values=(hex(number(m['address'])),f'{m["rows"]} × {m["columns"]}',m['verification'],m['category']))
        self.profiles.delete(0,'end')
        for name in d.profiles: self.profiles.insert('end',name)

    def render_hex(self):
        """Compatibility renderer for the original base UI."""
        d=self.need();self.hex.configure(state='normal');self.hex.delete('1.0','end')
        for a in range(self.page,min(self.page+512,len(d.data)),16):
            self.hex.insert('end',f'{a:08X}  ')
            for i in range(a,min(a+16,len(d.data))):
                self.hex.insert('end',f'{d.data[i]:02X} ','changed' if d.data[i]!=d.original[i] else ())
            self.hex.insert('end','\n')
        self.hex.configure(state='disabled')


def main():
    root=tk.Tk(); App(root); root.mainloop()
