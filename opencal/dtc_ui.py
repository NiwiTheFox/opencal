"""English grouped DTC controls with independent white-text state buttons."""
import tkinter as tk
from tkinter import ttk,filedialog as fd
from pathlib import Path
from .core import read_binary,digest
from .edc15 import dtc_records
from .dtc import grouped,apply,reference_records
from .codeblocks import metadata_id

BG='#101218'; PANEL='#181b23'; FG='#e6e9f0'; MUTED='#969ead'
COLOURS={'Enabled':'#63dba0','Disabled':'#ff777e','Mixed':'#ffd18c'}
BUTTONS={'Enabled':'#18563f','Disabled':'#782e37','Mixed':'#635023'}


class DTCPanel:
    def __init__(self,app,host):
        self.app=app;self.document=None;self.loaded=False;self.records=[];self.expanded=set();self.folded=set();self.cache=None
        self.query=tk.StringVar();self.state=tk.StringVar(value='All states');self.summary=tk.StringVar(value='Read the DTC records to inspect this BIN.')
        self.reference=tk.StringVar(value='Re-enable uses exact enabled bytes from the loaded original.')
        top=ttk.Frame(host,padding=(12,10));top.pack(fill='x')
        ttk.Label(top,text='Diagnostic trouble codes',style='Title.TLabel').pack(anchor='w')
        ttk.Label(top,text='Buttons change project monitoring, not live faults. Shared fault paths affect every code named on that path.',style='Muted.TLabel').pack(anchor='w',pady=(5,10))
        controls=ttk.Frame(top);controls.pack(fill='x')
        ttk.Button(controls,text='Read DTC records',command=lambda:app.run(self.read)).pack(side='left',padx=(0,8))
        ttk.Label(controls,text='Search').pack(side='left',padx=(0,6))
        ttk.Entry(controls,textvariable=self.query,width=27).pack(side='left',fill='x',expand=True,padx=(0,8))
        picker=ttk.Combobox(controls,textvariable=self.state,values=('All states','Enabled','Disabled','Mixed'),state='readonly',width=13);picker.pack(side='left')
        ttk.Label(top,textvariable=self.summary,style='Muted.TLabel').pack(anchor='w',pady=(9,0))
        self.outer=ttk.Frame(host);self.outer.pack(fill='both',expand=True,padx=12)
        self.canvas=tk.Canvas(self.outer,background=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(self.outer,orient='vertical',command=self.canvas.yview)
        self.canvas.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y');self.canvas.configure(yscrollcommand=scroll.set)
        self.content=tk.Frame(self.canvas,bg=BG);self.item=self.canvas.create_window(0,0,window=self.content,anchor='nw')
        self.content.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',self.resize)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.buttons={};self.row_labels={};self.wrap_labels=[]
        bottom=ttk.Frame(host,padding=12);bottom.pack(fill='x')
        ttk.Button(bottom,text='Load stock DTC reference…',command=lambda:app.run(self.load_reference)).pack(anchor='w')
        ttk.Label(bottom,textvariable=self.reference,style='Muted.TLabel',wraplength=900).pack(anchor='w',pady=(7,0))
        self.query.trace_add('write',lambda *_:self.render(reset=True));self.state.trace_add('write',lambda *_:self.render(reset=True))
        self.placeholder('Open a BIN, then read its supported DTC records.')

    def wheel(self,event):
        self.canvas.yview_scroll(-int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1),'units')
        return 'break'

    def resize(self,event):
        self.canvas.itemconfigure(self.item,width=event.width)
        for label,indent in self.wrap_labels:label.configure(wraplength=max(180,event.width-indent))

    def clear_widgets(self):
        for widget in self.content.winfo_children():widget.destroy()
        self.buttons={};self.row_labels={};self.wrap_labels=[]

    def placeholder(self,text):
        self.clear_widgets();tk.Label(self.content,text=text,fg=MUTED,bg=BG,padx=15,pady=28,anchor='w').pack(fill='x')

    def refresh(self):
        if self.document is not self.app.doc:
            self.document=self.app.doc;self.loaded=False;self.records=[];self.cache=None;self.expanded.clear();self.folded.clear()
            self.summary.set('Read the DTC records to inspect this BIN.');self.reference.set('Re-enable uses exact enabled bytes from the loaded original.')
            self.placeholder('Read DTC records to inspect the current BIN.');return
        if self.loaded:
            key=digest(self.document.data)
            if key!=self.cache:
                try:self.records=dtc_records(self.document.data)
                except ValueError as error:
                    self.records=[];self.cache=key;self.summary.set(str(error));self.placeholder('DTC layout no longer matches. Undo the relevant edit or read a supported BIN.');return
                self.cache=key;self.render()

    def read(self):
        document=self.app.need();records=dtc_records(document.data)
        if self.document is not document:self.expanded.clear();self.folded.clear()
        self.document=document;self.loaded=True;self.records=records;self.cache=digest(document.data);self.render()
        self.app.tabs.select(self.app.ecu_tab)

    def render(self,reset=False):
        if not self.loaded:return
        view=self.canvas.yview();focus=self.app.root.focus_get();focus_key=next((k for k,b in self.buttons.items() if b is focus),None)
        self.clear_widgets();groups=grouped(self.records);query=self.query.get().strip().casefold();state=self.state.get()
        shown=[]
        for group in groups:
            blocks=' '.join(f'codeblock {metadata_id(self.document.data,r["codeblock_base"])} 0x{r["address"]:06x}' for r in group['records'])
            text=f'{group["code"]} {group["vag_code"]} {group["description"]} {group["system"]} {blocks}'
            if query and query not in text.casefold():continue
            if state!='All states' and state!=group['state']:continue
            shown.append(group)
        enabled=sum(g['state']=='Enabled' for g in groups);disabled=sum(g['state']=='Disabled' for g in groups);mixed=len(groups)-enabled-disabled
        self.summary.set(f'{len(groups)} codes · {len(self.records)} records · {enabled} enabled · {disabled} disabled · {mixed} mixed     |     Showing {len(shown)} codes')
        last=None
        for group in shown:
            system=group['system']
            if system!=last:
                last=system
                title=tk.Button(self.content,text=('▸' if system in self.folded else '▾')+'  '+system,anchor='w',bg='#252b37',fg=FG,activebackground='#32394a',activeforeground=FG,relief='flat',bd=0,padx=12,pady=8,font=('Segoe UI Semibold',11),command=lambda s=system:self.fold(s))
                title.pack(fill='x',pady=(10,4));title.bind('<MouseWheel>',self.wheel)
            if system in self.folded:continue
            self.add_group(group)
        if not shown:self.placeholder('No DTCs match this search and state filter.')
        self.content.update_idletasks();self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.canvas.yview_moveto(0 if reset else view[0] if view else 0)
        if focus_key in self.buttons:self.buttons[focus_key].focus_set()
        if getattr(self.document,'dtc_reference',None) is not None:self.reference.set('Matching stock reference attached · saved inside the project for exact DTC restoration.')

    def fold(self,system):
        if system in self.folded:self.folded.remove(system)
        else:self.folded.add(system)
        self.render()

    def expand(self,code):
        if code in self.expanded:self.expanded.remove(code)
        else:self.expanded.add(code)
        self.render()

    def button(self,parent,state,key,command):
        button=tk.Button(parent,text=state,fg='white',bg=BUTTONS[state],activeforeground='white',activebackground=BUTTONS[state],disabledforeground='white',width=11,relief='flat',bd=0,padx=8,pady=8,font=('Segoe UI Semibold',10),takefocus=True,command=command)
        self.buttons[key]=button;button.bind('<MouseWheel>',self.wheel)
        return button

    def add_group(self,group):
        code=group['vag_code'];state=group['state'];colour=COLOURS[state]
        frame=tk.Frame(self.content,bg=PANEL,padx=10,pady=7);frame.pack(fill='x',pady=2)
        frame.columnconfigure(1,weight=1)
        expand=tk.Button(frame,text='▾' if code in self.expanded else '▸',fg=colour,bg=PANEL,activeforeground=colour,activebackground=PANEL,relief='flat',bd=0,width=2,command=lambda:self.expand(code));expand.grid(row=0,column=0,rowspan=2,sticky='ns')
        text=tk.Label(frame,text=f'{group["code"]}   /   VAG {code}    ·    {group["description"]}',bg=PANEL,fg=colour,anchor='w',justify='left',font=('Segoe UI',10),wraplength=max(180,self.canvas.winfo_width()-210));text.grid(row=0,column=1,sticky='ew',padx=(4,12))
        self.row_labels[(code,None)]=text;self.wrap_labels.append((text,210))
        details=tk.Label(frame,text=f'{group["enabled"]}/{group["total"]} records enabled · click arrow for codeblocks and individual control',bg=PANEL,fg=colour,anchor='w',font=('Segoe UI',9));details.grid(row=1,column=1,sticky='w',padx=4,pady=(3,0))
        details.configure(justify='left',wraplength=max(180,self.canvas.winfo_width()-210));self.wrap_labels.append((details,210))
        button=self.button(frame,state,(code,None),lambda:self.app.run(lambda:self.toggle(code)))
        button.grid(row=0,column=2,rowspan=2,sticky='ne')
        for widget in (frame,expand,text,details):widget.bind('<MouseWheel>',self.wheel)
        if code in self.expanded:
            for record in group['records']:
                address=record['address'];record_state='Enabled' if record['enabled'] else 'Disabled';block=metadata_id(self.document.data,record['codeblock_base'])
                row=tk.Frame(self.content,bg='#151820',padx=14,pady=5);row.pack(fill='x',padx=(25,0),pady=1);row.columnconfigure(0,weight=1)
                label=tk.Label(row,text=f'Codeblock {block if block is not None else "unknown"} · bank 0x{record["codeblock_base"]:05X} · record 0x{address:06X}',fg=COLOURS[record_state],bg='#151820',anchor='w',justify='left',wraplength=max(180,self.canvas.winfo_width()-205));label.grid(row=0,column=0,sticky='ew',padx=(0,12))
                self.row_labels[(code,address)]=label;self.wrap_labels.append((label,205))
                self.button(row,record_state,(code,address),lambda a=address,c=code:self.app.run(lambda:self.toggle(c,a))).grid(row=0,column=1,sticky='ne')
                row.bind('<MouseWheel>',self.wheel);label.bind('<MouseWheel>',self.wheel)

    def toggle(self,code,address=None):
        if self.document is not self.app.need():raise ValueError('The project changed; read its DTCs first.')
        records=[r for r in dtc_records(self.document.data) if r['vag_code']==code and (address is None or r['address']==address)]
        if not records:raise ValueError('DTC record is no longer present.')
        # Mixed group -> enable all. Enabled group -> disable all.
        enable=not all(r['enabled'] for r in records)
        operation=apply(self.document,code,enable,None if address is None else [address])
        self.app.refresh();self.app.status.set(f'{operation["name"]} · {len(operation["edits"])} record(s) changed · Undo available')

    def load_reference(self):
        document=self.app.need()
        path=fd.askopenfilename(title='Select a copied matching stock BIN for DTC restoration',filetypes=[('ECU binary','*.bin *.ori'),('All files','*.*')])
        if not path:return
        data=read_binary(path);mapping=reference_records(document.data,data)
        document.dtc_reference=bytes(data);document.protected_paths.add(str(Path(path).resolve()))
        self.reference.set(f'Matching stock reference · {Path(path).name} · {len(mapping)} checked records · save project to keep it')
        self.app.status.set('Stock DTC reference attached. No BIN bytes changed.');self.cache=None
        if not self.loaded:self.read()
        else:self.refresh()
