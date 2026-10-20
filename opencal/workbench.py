"""OpenCal desktop workbench. Original UI, GPL-3.0-only, no reference assets."""
import csv
import json
import math
import re
import struct
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
from tkinter import ttk,filedialog as fd,messagebox as mb,simpledialog as sd
from .gui import App as BaseApp
from .core import Document,read_binary,number,map_values,validate_definitions,digest,atomic_json,refresh_axes
from .checksums import inspect as checksum_inspect
from .edc15 import discover,identity
from .catalog import CATALOG,make_profile
from .mappack import decode_json
from . import __version__

BG='#101218'; PANEL='#181b23'; CARD='#20242f'; FG='#e6e9f0'; MUTED='#969ead'; ACCENT='#fa633b'


class App(BaseApp):
    def __init__(self,root):
        self.root=root; self.doc=None; self.page=0; self.project=None; self.saved_state=None
        self.active_map=None; self._drawing=False; self._filtering=False
        root.title(f'OpenCal {__version__} • Calibration workbench'); root.geometry('1440x900'); root.minsize(1080,700)
        root.configure(background=BG); root.protocol('WM_DELETE_WINDOW',self.close)
        # A global *Font option overrides even the Brand/Scalar style fonts.
        # Set the named default instead, keeping each visual hierarchy intact.
        tkfont.nametofont('TkDefaultFont').configure(family='Segoe UI',size=10)
        self.theme()
        header=ttk.Frame(root,padding=(20,12)); header.pack(fill='x')
        ttk.Label(header,text='OpenCal',style='Brand.TLabel').pack(side='left')
        ttk.Label(header,text='   /   Offline calibration workbench',style='Muted.TLabel').pack(side='left')
        for label,fn in [('Close project',self.close_project),('Redo',self.redo),('Undo',self.undo)]:
            ttk.Button(header,text=label,command=lambda f=fn:self.run(f)).pack(side='right',padx=4)
        body=ttk.Panedwindow(root,orient='horizontal'); body.pack(fill='both',expand=True,padx=12,pady=(0,6))
        self.panes=body
        self.sidebar=ttk.Frame(body,padding=12,style='Panel.TFrame'); body.add(self.sidebar,weight=0)
        self.sidebar.configure(width=320)
        self.project_name=tk.StringVar(value='No project open')
        ttk.Label(self.sidebar,text='PROJECT',style='Muted.Panel.TLabel').pack(anchor='w')
        ttk.Label(self.sidebar,textvariable=self.project_name,style='Title.Panel.TLabel',wraplength=285).pack(anchor='w',pady=(5,10))
        self.ecu_name=tk.StringVar(value='Open a BIN to identify its software')
        ttk.Label(self.sidebar,textvariable=self.ecu_name,style='Muted.Panel.TLabel',wraplength=285).pack(anchor='w')
        self.checksum_badge=tk.StringVar(value='Checksums · not checked')
        ttk.Button(self.sidebar,textvariable=self.checksum_badge,command=lambda:self.run(self.verify_checksums)).pack(fill='x',pady=12)
        actions=ttk.Frame(self.sidebar,style='Panel.TFrame'); actions.pack(fill='x')
        for i,(label,fn) in enumerate([('Open BIN',self.open_bin),('Open project',self.open_project),('Save project',self.save_project),('Export BIN',self.export)]):
            ttk.Button(actions,text=label,style='Accent.TButton' if label=='Export BIN' else 'TButton',command=lambda f=fn:self.run(f)).grid(row=i//2,column=i%2,sticky='ew',padx=2,pady=3)
        actions.columnconfigure((0,1),weight=1)
        ttk.Separator(self.sidebar).pack(fill='x',pady=13)
        self.search=tk.StringVar(); search=ttk.Entry(self.sidebar,textvariable=self.search)
        search.pack(fill='x'); self.search.trace_add('write',lambda *_:self.filter_maps())
        ttk.Label(self.sidebar,text='Search maps, category or address',style='Muted.Panel.TLabel').pack(anchor='w',pady=(4,10))
        packbar=ttk.Frame(self.sidebar,style='Panel.TFrame'); packbar.pack(fill='x')
        self.pack_count=tk.StringVar(value='MAPPACK · 0')
        ttk.Label(packbar,textvariable=self.pack_count,style='Title.Panel.TLabel').pack(side='left')
        ttk.Button(packbar,text='Export',command=lambda:self.run(self.export_defs)).pack(side='right')
        map_frame=ttk.Frame(self.sidebar,style='Panel.TFrame'); map_frame.pack(fill='both',expand=True,pady=(8,0))
        self.maps=ttk.Treeview(map_frame,show='tree',selectmode='browse',height=12)
        self.maps.column('#0',width=540,minwidth=200,stretch=False); self.maps.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(map_frame,orient='vertical',command=self.maps.yview); vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(map_frame,orient='horizontal',command=self.maps.xview); horizontal.grid(row=1,column=0,sticky='ew')
        self.maps.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        map_frame.columnconfigure(0,weight=1); map_frame.rowconfigure(0,weight=1)
        self.maps.bind('<<TreeviewSelect>>',lambda e:self.run(self.view_map))
        self.maps.bind('<Double-1>',lambda e:self.run(self.view_map))
        self.workspace=ttk.Frame(body,padding=(12,0,0,0)); body.add(self.workspace,weight=1)
        self.tabs=ttk.Notebook(self.workspace); self.tabs.pack(fill='both',expand=True)
        self.map_tab=ttk.Frame(self.tabs); self.tabs.add(self.map_tab,text='  Map editor  ')
        self.solutions_tab=ttk.Frame(self.tabs);self.tabs.add(self.solutions_tab,text='  Solutions  ')
        self.hex_tab=ttk.Frame(self.tabs); self.tabs.add(self.hex_tab,text='  Hexdump  ')
        self.ecu_tab=ttk.Frame(self.tabs); self.tabs.add(self.ecu_tab,text='  ECU tools & DTCs  ')
        self.analysis_tab=ttk.Frame(self.tabs); self.tabs.add(self.analysis_tab,text='  Analysis & compare  ')
        self.profile_tab=ttk.Frame(self.tabs); self.tabs.add(self.profile_tab,text='  Versions  ')
        self.build_map_workspace(); self.build_hex(); self.build_ecu(); self.build_analysis(); self.build_profiles()
        from .solutions_ui import build_solutions
        build_solutions(self)
        self.status=tk.StringVar(value='Ready · open a BIN or a codex project to begin')
        footer=ttk.Frame(root,padding=(15,6)); footer.pack(fill='x')
        ttk.Label(footer,textvariable=self.status,style='Muted.TLabel').pack(side='left')
        ttk.Button(footer,text=f'{__version__} · GPL / About',command=self.about).pack(side='right')
        self.analysis.configure(background=BG,foreground=FG,insertbackground=FG,relief='flat')
        self.profiles.configure(background=PANEL,foreground=FG,selectbackground='#583728',relief='flat')
        self._sidebar_initialised=False
        body.bind('<Configure>',self.initial_sidebar_width,add='+')

    def initial_sidebar_width(self,event):
        if not self._sidebar_initialised and event.width>=600:
            self.panes.sashpos(0,min(340,int(event.width*.28)))
            self._sidebar_initialised=True

    def theme(self):
        s=ttk.Style(self.root); s.theme_use('clam')
        s.configure('.',background=BG,foreground=FG,font=('Segoe UI',10),bordercolor='#313643',lightcolor=BG,darkcolor=BG)
        s.configure('TFrame',background=BG); s.configure('Panel.TFrame',background=PANEL)
        s.configure('TLabel',background=BG,foreground=FG)
        s.configure('Muted.TLabel',foreground=MUTED)
        s.configure('Muted.Panel.TLabel',background=PANEL,foreground=MUTED)
        s.configure('Title.Panel.TLabel',background=PANEL,foreground=FG,font=('Segoe UI Semibold',11))
        s.configure('Brand.TLabel',foreground=ACCENT,font=('Segoe UI Semibold',21))
        s.configure('Title.TLabel',foreground=FG,font=('Segoe UI Semibold',16))
        s.configure('TButton',background=CARD,foreground=FG,padding=(10,7),borderwidth=1)
        s.map('TButton',background=[('active','#32394a')])
        s.configure('Accent.TButton',background=ACCENT,foreground='white')
        s.map('Accent.TButton',background=[('active','#e34f28')])
        s.configure('TEntry',fieldbackground=CARD,foreground=FG,insertcolor=FG,padding=7)
        s.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=FG,rowheight=29,borderwidth=0)
        s.map('Treeview',background=[('selected','#59372e')],foreground=[('selected','white')])
        s.configure('Treeview.Heading',background=CARD,foreground=MUTED,padding=7)
        s.configure('Map.Treeview',font=('Consolas',10),rowheight=30)
        s.configure('Map.Treeview.Heading',font=('Segoe UI Semibold',10),foreground=FG,padding=(8,9))
        s.configure('TNotebook',background=BG,borderwidth=0)
        s.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,padding=(10,10))
        s.map('TNotebook.Tab',background=[('selected',CARD)],foreground=[('selected',FG)])
        s.configure('TCombobox',fieldbackground=CARD,background=CARD,foreground=FG)
        s.map('TCombobox',fieldbackground=[('readonly',CARD)],foreground=[('readonly',FG)],selectbackground=[('readonly',CARD)],selectforeground=[('readonly',FG)])
        s.configure('Scalar.TLabel',foreground=FG,font=('Segoe UI Semibold',30))

    def build_map_workspace(self):
        bar=ttk.Frame(self.map_tab,padding=(0,12)); bar.pack(fill='x')
        for label,fn in [('Detect maps',self.discover_edc),('Import mappack',self.import_defs),('Use ORI mappack',self.use_ori),('Definition editor',self.edit_defs),('Learn profile',self.learn_profile)]:
            ttk.Button(bar,text=label,command=lambda f=fn:self.run(f)).pack(side='left',padx=(0,5))
        shortcuts=ttk.Frame(self.map_tab); shortcuts.pack(fill='x',pady=(0,8))
        ttk.Label(shortcuts,text='Go to:',style='Muted.TLabel').pack(side='left',padx=(0,8))
        for token,label in [('SVRL','SVRL · RPM limiter'),('SVBL','SVBL · Boost limiter')]:
            ttk.Button(shortcuts,text=label,command=lambda t=token:self.run(lambda:self.jump_to_map(t))).pack(side='left',padx=(0,5))
        self.detection_label=tk.StringVar(value='No binary loaded')
        ttk.Label(self.map_tab,textvariable=self.detection_label,style='Muted.TLabel',wraplength=950).pack(anchor='w',pady=(0,8))
        self.editor=ttk.Frame(self.map_tab,padding=12); self.editor.pack(fill='both',expand=True)
        self.show_welcome()

    def build_hex(self):
        from .hex_view import build
        build(self)

    def build_ecu(self):
        bar=ttk.Frame(self.ecu_tab,padding=12);bar.pack(fill='x')
        for label,fn in [('Identify ECU',self.identify),('Verify checksums',self.verify_checksums),('Correct checksums…',self.correct_checksums)]:
            ttk.Button(bar,text=label,command=lambda f=fn:self.run(f)).pack(side='left',padx=(0,6))
        from .dtc_ui import DTCPanel
        self.dtc_panel=DTCPanel(self,self.ecu_tab)

    def read_dtcs(self):
        self.dtc_panel.read()

    def compare(self):
        d=self.need()
        path=fd.askopenfilename(title='Select a copied read-only comparison BIN',filetypes=[('ECU binary','*.bin *.ori'),('All files','*.*')])
        if not path:return
        self.open_comparison(read_binary(path),path)

    def open_comparison(self,data,path):
        from .compare_ui import Comparison
        d=self.need()
        if not 0<len(data)<=32*1024*1024:raise ValueError('Comparison must be nonempty and at most 32 MiB.')
        d.protected_paths.add(str(Path(path).resolve()))
        if not hasattr(self,'comparisons'):self.comparisons=[]
        session=Comparison(self,data,path);self.comparisons.append(session)
        return session

    def close(self):
        if self.can_leave():
            for session in list(getattr(self,'comparisons',[])):session.close()
            self.root.destroy()

    def render_hex(self):
        from .hex_view import render
        render(self)

    def show_welcome(self):
        for widget in self.editor.winfo_children(): widget.destroy()
        ttk.Label(self.editor,text='Your calibration workspace',style='Title.TLabel').pack(anchor='w',pady=(45,10))
        ttk.Label(self.editor,text='Open a BIN to load its matched reference mappack.\nBrowse categories on the left, then select a map to inspect or edit it.\n\nUnrecognised files stay clearly labelled. You can import a permitted JSON\nmappack and learn its layout for future files.',style='Muted.TLabel',justify='left').pack(anchor='w')

    def open_bin(self):
        p=fd.askopenfilename(filetypes=[('ECU binary','*.bin *.ori'),('All files','*.*')])
        if not p or not self.can_leave(): return
        d=Document(read_binary(p),p)
        try: d.definitions=validate_definitions(discover(d.data),len(d.data))
        except ValueError: pass
        self.doc=d; self.project=None; self.saved_state=None; self.active_map=None; self.page=0
        self.search.set(''); self.show_welcome(); self.refresh(); self.tabs.select(self.map_tab)

    def open_project(self):
        super().open_project()
        if self.doc:
            self.active_map=None; self.search.set(''); self.show_welcome(); self.refresh(); self.tabs.select(self.map_tab)

    def close_project(self):
        if not self.can_leave(): return
        self.doc=None; self.project=None; self.saved_state=None; self.active_map=None; self.page=0
        self.maps.delete(*self.maps.get_children()); self.project_name.set('No project open'); self.ecu_name.set('Open a BIN to identify its software')
        self.pack_count.set('MAPPACK · 0'); self.detection_label.set('No binary loaded'); self.checksum_badge.set('Checksums · not checked')
        self.status.set('Project closed'); self.show_welcome()
        self.hex.configure(state='normal'); self.hex.delete('1.0','end'); self.hex.configure(state='disabled')
        self.dtc_panel.refresh()
        for session in list(getattr(self,'comparisons',[])):session.refresh()
        self.profiles.delete(0,'end'); self.analysis.configure(state='normal'); self.analysis.delete('1.0','end'); self.analysis.configure(state='disabled')
        from .solutions_ui import refresh_solutions
        refresh_solutions(self)

    def filter_maps(self):
        if self._filtering: return
        self._filtering=True
        try:
            selected_items=self.maps.selection()
            selected=selected_items[0] if selected_items else str(self.active_map) if self.active_map is not None else None
            focused=self.maps.focus()
            scroll=self.maps.yview()
            open_state={}
            def remember(parent=''):
                for item in self.maps.get_children(parent):
                    if not item.isdigit():open_state[item]=bool(self.maps.item(item,'open'));remember(item)
            remember()
            self.maps.delete(*self.maps.get_children())
            if not self.doc: return
            from .codeblocks import codeblock,map_name
            from .checksums import standard_bases
            multiple=len(standard_bases(self.doc.data))>1
            query=self.search.get().strip().lower(); categories={};blocks={}
            for i,m in enumerate(self.doc.definitions['maps']):
                label=map_name(self.doc.data,m)
                if query and query not in (label+' '+m['category']+' '+hex(number(m['address']))).lower(): continue
                block=codeblock(self.doc.data,m);parent=''
                if block:
                    parent=f'codeblock:{block["base"]}'
                    if parent not in blocks:
                        blocks[parent]=block
                        block_label=str(block['number']) if block['number'] is not None else 'ID unknown'
                        self.maps.insert('','end',iid=parent,text=f'Codeblock {block_label} · 0x{block["start"]:05X}–0x{block["end"]-1:05X}',open=True if query else open_state.get(parent,not multiple))
                category=m['category'] or 'Other'
                key=(parent,category)
                if key not in categories:
                    cid=f'category:{parent}:{category}'; categories[key]=cid
                    self.maps.insert(parent,'end',iid=cid,text=category,open=True if query else open_state.get(cid,True))
                self.maps.insert(categories[key],'end',iid=str(i),text=f'{number(m["address"]):05X}  {label}',values=(i,))
            for (_,category),cid in categories.items(): self.maps.item(cid,text=f'{category}  ·  {len(self.maps.get_children(cid))}')
            if selected and self.maps.exists(selected): self.maps.selection_set(selected)
            if focused and self.maps.exists(focused): self.maps.focus(focused)
            elif selected and self.maps.exists(selected): self.maps.focus(selected)
            if scroll:self.maps.yview_moveto(scroll[0])
        finally: self._filtering=False

    def map_leaf_ids(self):
        def leaves(parent=''):
            for item in self.maps.get_children(parent):
                if item.isdigit():yield item
                else:yield from leaves(item)
        return list(leaves())

    def jump_to_map(self,token):
        d=self.need()
        matches=[i for i,m in enumerate(d.definitions['maps']) if re.search(r'\b'+re.escape(token)+r'\b',m['name'],re.I)]
        if not matches: raise ValueError(f'{token} is not present in this mappack.')
        # Prefer the bank currently being inspected; do not confuse bank count
        # with evidence of ECU switching support.
        current=d.definitions['maps'][self.active_map]['address'] if self.active_map is not None else None
        from .checksums import standard_bases
        bank=next((b for b in standard_bases(d.data) if current is not None and b-0x4000<=current<b+0xc000),None)
        index=next((i for i in matches if bank is not None and bank-0x4000<=d.definitions['maps'][i]['address']<bank+0xc000),matches[0])
        self.search.set(''); self.maps.selection_set(str(index)); self.maps.see(str(index)); self.view_map()

    def discover_edc(self):
        d=self.need(); defs=validate_definitions(discover(d.data),len(d.data))
        if d.definitions['maps'] and not mb.askyesno('Replace mappack','Replace the current definitions with this detection result? Binary edits are preserved.'): return
        d.definitions=defs; self.active_map=None; self.show_welcome(); self.refresh(); self.tabs.select(self.map_tab)

    def learn_profile(self):
        d=self.need()
        if not d.definitions['maps'] or not all('original_fields' in m for m in d.definitions['maps']):
            raise ValueError('Import a permitted ZedSuite/WinOLS JSON mappack first. Learning requires the original map descriptors.')
        name=sd.askstring('Learn reference profile','Profile name:',initialvalue=Path(d.source).stem if d.source else 'User profile')
        if not name: return
        pack={'maps':[m['original_fields'] for m in d.definitions['maps']]}
        profile=make_profile(d.data,pack,name,'User-learned mappack: '+name)
        catalog=json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else {'schema':'opencal.reference-catalog','version':1,'profiles':[]}
        catalog['profiles']=[p for p in catalog['profiles'] if p['name']!=name]+[profile]
        atomic_json(CATALOG,catalog)
        self.status.set(f'Learned profile {name}. Matching checks code and axes, not filename or size alone.')

    def use_ori(self):
        from .transfer import transfer_ori
        from .mappack import import_mappack
        d=self.need()
        original=fd.askopenfilename(title='Select copied ORI BIN',filetypes=[('ECU binary','*.bin *.ori'),('All files','*.*')])
        if not original: return
        pack=fd.askopenfilename(title='Select ORI JSON mappack',filetypes=[('JSON mappack','*.json')])
        if not pack: return
        d.protected_paths.update({str(Path(original).resolve()),str(Path(pack).resolve())})
        transferred=transfer_ori(read_binary(original),d.data,decode_json(Path(pack).read_bytes()))
        defs,skipped=import_mappack(transferred,d.data,'Matching ORI mappack: '+Path(pack).name)
        if skipped: raise ValueError('Transfer did not import completely.')
        if d.definitions['maps'] and not mb.askyesno('Use ORI mappack',f'Replace definitions with {len(defs["maps"])} ORI-derived definitions? ECU, hardware, software and axis headers match.'): return
        defs['transfer']=transferred['opencal_transfer']; d.definitions=defs
        self.active_map=None; self.show_welcome(); self.refresh()
        self.status.set(f'Loaded {len(defs["maps"])} ORI definitions; BIN bytes unchanged.')

    def verify_checksums(self):
        result=checksum_inspect(self.need().data)
        self.checksum_badge.set(f'Checksums · {result["status"]}'+(f' {result["matched"]}/{result["found"]}' if 'found' in result else ''))
        self.output(json.dumps(result,indent=2))

    def refresh(self):
        d=self.need()
        refresh_axes(d.data,d.definitions)
        from .solutions import launch_control_maps
        from .solutions_ui import refresh_solutions
        # Generated solution definitions must follow current bytes after undo,
        # restore or raw edits. Never keep an active label based on history alone.
        active_id=d.definitions['maps'][self.active_map]['id'] if self.active_map is not None and self.active_map<len(d.definitions['maps']) else None
        d.definitions['maps']=[m for m in d.definitions['maps'] if not m['id'].startswith('launch-control-')]+launch_control_maps(d.data,d.original)
        if active_id is not None:
            self.active_map=next((i for i,m in enumerate(d.definitions['maps']) if m['id']==active_id),None)
            if self.active_map is None:self.show_welcome()
        # Reuse the binary/history rendering, but grouped map tree is owned here.
        self._filtering=True
        try: super().refresh()
        finally: self._filtering=False
        self.project_name.set(Path(self.project or d.source or 'Embedded project').stem)
        ids=identity(d.original)
        self.ecu_name.set(('Bosch EDC15 / '+ids[0]['name']+'\n' if ids else 'ECU identity unverified\n')+f'{len(d.data)//1024:,} KiB · {digest(d.original)[:12]}…')
        self.pack_count.set(f'MAPPACK · {len(d.definitions["maps"])}')
        detection=d.definitions.get('detection',{})
        if detection.get('method')=='reference-profile': self.detection_label.set(f'Reference profile matched · {detection["name"]} · {len(d.definitions["maps"])} maps · source semantics remain unverified')
        elif detection.get('method')=='heuristic': self.detection_label.set(f'Experimental structural scan · {len(d.definitions["maps"])} named candidates · {detection.get("unclassified_structures_hidden",0)} unclassified structures hidden')
        else: self.detection_label.set(f'Imported mappack · {len(d.definitions["maps"])} definitions · inspect source and software compatibility')
        self.filter_maps()
        self.checksum_badge.set('Checksums · click to verify')
        refresh_solutions(self)
        self.dtc_panel.refresh()
        if self.active_map is not None and self.active_map<len(d.definitions['maps']): self.render_map(self.active_map)
        for session in list(getattr(self,'comparisons',[])):session.refresh()

    def view_map(self):
        if self._filtering or not self.doc: return
        selected=self.maps.selection()
        if not selected or not selected[0].isdigit(): return
        self.active_map=int(selected[0]); self.render_map(self.active_map); self.tabs.select(self.map_tab)

    def render_map(self,index):
        from .map_editor import render_editor
        render_editor(self,index)


def main():
    root=tk.Tk(); App(root); root.mainloop()
