"""Original OpenCal C166 workspace: mapped listing, notes, source and preview."""
import json,re,tkinter as tk
from tkinter import ttk,filedialog as fd,simpledialog as sd
from .core import number,digest
from .c166 import C166Disassembler
from . import c166_tools as engine
from .table_tools_ui import centre


validate_state=engine.validate_state


class Workspace:
    def __init__(self,app):
        self.app=app;self.document=app.need();self.closed=False;self.preview_operation=None;self.history=[];self.rows={}
        self.decoder=C166Disassembler()
        if not self.document.code_workspace:
            self.document.code_workspace={'version':1,'cpu':'80c167','segments':[{'file':0,'cpu':0,'size':min(len(self.document.data),0x1000000)}],'source':'start: nop\n','labels':{},'comments':{}}
        self.state=self.document.code_workspace;validate_state(self.state,len(self.document.data));self.decoder.cpu=self.state['cpu']
        window=self.window=tk.Toplevel(app.root);window.title('OpenCal · C166 / C167 code workspace');centre(window,app.root,1380,850);window.minsize(1020,650);window.protocol('WM_DELETE_WINDOW',self.close)
        self.address=tk.StringVar(value='0x0');self.length=tk.StringVar(value='0x200');self.capacity=tk.StringVar(value='0x40');self.cpu=tk.StringVar(value=self.state['cpu']);self.query=tk.StringVar()
        outer=ttk.Frame(window,padding=12);outer.pack(fill='both',expand=True)
        top=ttk.Frame(outer);top.pack(fill='x')
        ttk.Label(top,text='C166 / C167',style='Title.TLabel').pack(side='left')
        ttk.Button(top,text='Memory segments…',command=lambda:app.run(self.edit_segments)).pack(side='right')
        ttk.Combobox(top,textvariable=self.cpu,values=engine.CPUS,state='readonly',width=14).pack(side='right',padx=8)
        self.cpu.trace_add('write',lambda *_:self.change_cpu())
        ttk.Label(outer,text='Configure CPU addresses before assembly. The initial mapping uses CPU origin 0; it is not recovered from ECU code. DPP/EXTR-dependent data targets remain unresolved.',style='Muted.TLabel',wraplength=900).pack(anchor='w',pady=(8,10))
        bar=ttk.Frame(outer);bar.pack(fill='x')
        for label,value,width in [('File offset',self.address,13),('Decode bytes',self.length,10),('Patch capacity',self.capacity,10)]:
            ttk.Label(bar,text=label).pack(side='left',padx=(0,5));ttk.Entry(bar,textvariable=value,width=width).pack(side='left',padx=(0,10))
        navigation=ttk.Frame(outer);navigation.pack(fill='x',pady=(6,0))
        for label,fn in [('Disassemble',self.decode),('Back',self.back),('Follow branch',self.follow),('Patch at selection',self.patch_selection),('Label / comment…',self.annotate)]:ttk.Button(navigation,text=label,command=lambda f=fn:app.run(f)).pack(side='left',padx=3)
        search=ttk.Frame(outer);search.pack(fill='x',pady=(8,5))
        ttk.Label(search,text='Search listing').pack(side='left');ttk.Entry(search,textvariable=self.query,width=28).pack(side='left',padx=8)
        ttk.Button(search,text='Find next',command=lambda:app.run(self.find)).pack(side='left')
        ttk.Button(search,text='References to selection',command=lambda:app.run(self.references)).pack(side='left',padx=5)
        self.status=tk.StringVar();ttk.Label(outer,textvariable=self.status,style='Muted.TLabel').pack(anchor='w',pady=(0,5))
        panes=ttk.Panedwindow(outer,orient='vertical');panes.pack(fill='both',expand=True)
        listing=ttk.Frame(panes);panes.add(listing,weight=3)
        columns=('file','cpu','bytes','instruction','branch','label','comment')
        self.tree=ttk.Treeview(listing,columns=columns,show='headings',selectmode='browse')
        for key,title,width in [('file','File offset',85),('cpu','CPU address',90),('bytes','Bytes',100),('instruction','Instruction / encoded operands',300),('branch','Direct target',95),('label','Label',130),('comment','Comment',230)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=65,stretch=key in ('instruction','comment'))
        self.tree.grid(row=0,column=0,sticky='nsew');v=ttk.Scrollbar(listing,orient='vertical',command=self.tree.yview);v.grid(row=0,column=1,sticky='ns');h=ttk.Scrollbar(listing,orient='horizontal',command=self.tree.xview);h.grid(row=1,column=0,sticky='ew');self.tree.configure(yscrollcommand=v.set,xscrollcommand=h.set);listing.rowconfigure(0,weight=1);listing.columnconfigure(0,weight=1)
        self.tree.tag_configure('unknown',foreground='#ff777e')
        self.tree.bind('<Double-1>',lambda event:app.run(self.follow))
        editor=ttk.Frame(panes,padding=(0,8,0,0));panes.add(editor,weight=2)
        controls=ttk.Frame(editor);controls.pack(fill='x',pady=(0,6))
        ttk.Label(controls,text='Assembly source',style='Title.TLabel').pack(side='left')
        for label,fn in [('Load source…',self.load_source),('Save source…',self.save_source),('Assemble → preview…',self.assemble)]:ttk.Button(controls,text=label,command=lambda f=fn:app.run(f)).pack(side='right',padx=4)
        source_frame=ttk.Frame(editor);source_frame.pack(fill='both',expand=True)
        self.source=tk.Text(source_frame,wrap='none',undo=True,font=('Consolas',11),bg='#181b23',fg='#e6e9f0',insertbackground='white',height=10)
        self.source.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(source_frame,orient='vertical',command=self.source.yview);scroll.grid(row=0,column=1,sticky='ns');xscroll=ttk.Scrollbar(source_frame,orient='horizontal',command=self.source.xview);xscroll.grid(row=1,column=0,sticky='ew');self.source.configure(yscrollcommand=scroll.set,xscrollcommand=xscroll.set);source_frame.rowconfigure(0,weight=1);source_frame.columnconfigure(0,weight=1)
        self.source.insert('1.0',self.state['source']);self.source.edit_modified(False);self.source.bind('<<Modified>>',self.source_changed)
        footer=ttk.Frame(outer);footer.pack(side='bottom',fill='x',pady=(8,0),before=panes)
        ttk.Label(footer,text='Source and notes save with the project. Assembly previews overwrite bounded bytes in memory; Undo and separate checksum correction/export remain available.',style='Muted.TLabel',wraplength=650).pack(side='left')
        ttk.Button(footer,text='Undo',command=lambda:app.run(app.undo)).pack(side='right');ttk.Button(footer,text='Redo',command=lambda:app.run(app.redo)).pack(side='right',padx=5)
        self.unsubscribe=self.document.subscribe(self.changed)
        app.root.after_idle(lambda:app.run(self.decode) if not self.closed else None)

    def need(self):
        if self.app.doc is not self.document or self.closed:raise ValueError('The active project changed. Open its code workspace again.')
        return self.document

    def change_cpu(self):
        self.need();self.state['cpu']=self.cpu.get();self.preview_operation=None;self.decoder.cpu=self.cpu.get();self.decode(record=False)

    def source_changed(self,event=None):
        if self.closed or not self.source.edit_modified():return
        self.need();text=self.source.get('1.0','end-1c')
        if len(text)>131072:self.source.edit_undo();self.source.edit_modified(False);raise ValueError('Assembly source exceeds 128 KiB.')
        self.state['source']=text;self.preview_operation=None;self.source.edit_modified(False)

    def changed(self):
        if not self.closed and self.app.doc is self.document:self.decode(record=False)

    def decode(self,record=True):
        self.need();start=number(self.address.get());length=number(self.length.get())
        if start%2 or start<0 or start>=len(self.document.data) or not 1<=length<=8192:raise ValueError('Use an aligned BIN offset and 1..8192 decode bytes.')
        length=min(length,len(self.document.data)-start);mapping=engine.segments(self.state['segments'],len(self.document.data));origin=engine.to_cpu(mapping,start,length)
        if record and (not self.history or self.history[-1]!=start):self.history.append(start)
        selected=self.tree.selection();selected=selected[0] if selected else None;scroll=self.tree.yview()
        self.tree.delete(*self.tree.get_children());self.rows={};unknown=0
        for cpu,raw,text in self.decoder.decode_range(self.document.data[start:start+length],origin,length):
            offset=start+cpu-origin;target=engine.branch_target(bytes.fromhex(raw),text,cpu);unknown+=text.startswith('(')
            key=str(offset);self.rows[key]={'offset':offset,'cpu':cpu,'raw':raw,'text':text,'target':target}
            self.tree.insert('','end',iid=key,values=(f'{offset:06X}',f'{cpu:06X}',raw,text,f'{target:06X}' if target is not None else '',self.state['labels'].get(key,''),self.state['comments'].get(key,'')),tags=('unknown',) if text.startswith('(') else ())
        self.status.set(f'{len(self.rows)} rows · {unknown} unknown/truncated · encoded data addresses')
        if selected in self.rows:self.tree.selection_set(selected);self.tree.focus(selected)
        if scroll:self.tree.yview_moveto(scroll[0])

    def selected(self):
        self.need();choice=self.tree.selection()
        if not choice:raise ValueError('Select an instruction row first.')
        return self.rows[choice[0]]

    def back(self):
        if len(self.history)<2:return
        self.history.pop();self.address.set(hex(self.history[-1]));self.decode(record=False)

    def patch_selection(self):
        row=self.selected();self.address.set(hex(row['offset']));self.preview_operation=None

    def follow(self):
        row=self.selected()
        if row['target'] is None:raise ValueError('This row has no resolved direct branch/call. Indirect and DPP-dependent targets remain unknown.')
        self.address.set(hex(engine.to_file(self.state['segments'],row['target'])));self.decode()

    def find(self):
        query=self.query.get().casefold().strip()
        if not query:return
        keys=list(self.rows);selection=self.tree.selection();start=keys.index(selection[0])+1 if selection and selection[0] in keys else 0
        for key in keys[start:]+keys[:start]:
            if query in ' '.join(map(str,self.tree.item(key,'values'))).casefold():self.tree.selection_set(key);self.tree.focus(key);self.tree.see(key);return
        raise ValueError('No match in the decoded listing. Decode another range to search it.')

    def references(self):
        row=self.selected();matches=[r for r in self.rows.values() if r['target']==row['cpu']]
        self.show_text('Direct references in decoded range','\n'.join(f'File 0x{r["offset"]:X} / CPU 0x{r["cpu"]:X}: {r["text"]}' for r in matches) or 'No direct references in the current decoded range. This is not a whole-firmware control-flow analysis.')

    def annotate(self):
        row=self.selected();key=str(row['offset'])
        label=sd.askstring('Code label','Label at the selected file offset:',initialvalue=self.state['labels'].get(key,''),parent=self.window)
        if label is None:return
        if label and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}',label):raise ValueError('Use a simple label of at most 128 letters, digits or underscores.')
        comment=sd.askstring('Code comment','Comment:',initialvalue=self.state['comments'].get(key,''),parent=self.window)
        if comment is None:return
        self.state['labels'][key]=label;self.state['comments'][key]=comment[:4096];self.decode(record=False)

    def edit_segments(self):
        self.need();window=tk.Toplevel(self.window);window.title('File ↔ CPU memory segments');centre(window,self.window,700,430);window.transient(self.window)
        ttk.Label(window,text='Each segment defines file offset, CPU origin and length. Numbers may be decimal or strings such as "0x80000". Mappings are explicit assumptions.',wraplength=650,padding=12).pack(fill='x')
        text=tk.Text(window,font=('Consolas',11));text.pack(fill='both',expand=True,padx=12);text.insert('1.0',json.dumps(self.state['segments'],indent=2))
        def apply():
            value=json.loads(text.get('1.0','end'))
            if not isinstance(value,list):raise ValueError('Segments must be a JSON array.')
            mapping=engine.segments([{k:number(v) for k,v in item.items()} for item in value],len(self.document.data))
            self.need();self.state['segments']=mapping;self.preview_operation=None;window.destroy();self.decode(record=False)
        ttk.Button(window,text='Use mapping',command=lambda:self.app.run(apply)).pack(pady=10)

    def load_source(self):
        self.need();name=fd.askopenfilename(parent=self.window,filetypes=[('Assembly source','*.asm *.s'),('Text','*.txt')])
        if not name:return
        p=__import__('pathlib').Path(name)
        if p.stat().st_size>131072:raise ValueError('Source file exceeds 128 KiB.')
        text=p.read_text(encoding='utf-8-sig');self.source.delete('1.0','end');self.source.insert('1.0',text);self.source_changed()

    def save_source(self):
        self.need();name=fd.asksaveasfilename(parent=self.window,defaultextension='.asm',filetypes=[('Assembly source','*.asm')])
        if not name:return
        path=self.document.protect(name)
        if path.suffix.lower() not in ('.asm','.s','.txt'):raise ValueError('Save source with .asm, .s or .txt extension.')
        with path.open('x',encoding='utf-8') as stream:stream.write(self.source.get('1.0','end-1c'))

    def show_text(self,title,text):
        window=tk.Toplevel(self.window);window.title(title);centre(window,self.window,1000,540)
        box=tk.Text(window,wrap='none',font=('Consolas',10),bg='#181b23',fg='#e6e9f0');box.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(window,orient='vertical',command=box.yview);scroll.pack(side='right',fill='y');box.configure(yscrollcommand=scroll.set);box.insert('1.0',text);box.configure(state='disabled');return window

    def assemble(self):
        document=self.need();source=self.source.get('1.0','end-1c');self.state['source']=source
        offset=number(self.address.get());capacity=number(self.capacity.get())
        operation=engine.preview(document,source,offset,capacity,self.state['segments'],self.cpu.get())
        self.preview_operation=operation;raw=bytes.fromhex(operation['output_hex']);offset=number(self.address.get())
        before=bytes(document.data[offset:offset+len(raw)]).hex(' ').upper()
        listing='\n'.join(f'{ea:06X}  {encoded:8s}  {text}' for ea,encoded,text in self.decoder.decode_range(raw,operation['origin'],len(raw)))
        window=self.preview_window=self.show_text('C166 assembly · review before applying',f'{operation["name"]}\n\n{len(raw)} output bytes within capacity {self.capacity.get()}\nBefore: {before}\nAfter:  {raw.hex(" ").upper()}\n\n{listing}\n\nAssembly only verifies encoding. CPU mapping, runtime state and vehicle execution remain unverified.\nChecksum correction and BIN export are separate actions.\n')
        def apply():
            self.need()
            if number(self.address.get())!=offset or number(self.capacity.get())!=capacity:raise ValueError('Patch address or capacity changed. Assemble and review again.')
            if digest(self.source.get('1.0','end-1c').encode('utf-8'))!=operation['source_sha256'] or self.cpu.get()!=operation['cpu'] or self.state['segments']!=operation['mapping']:raise ValueError('Source, CPU or mapping changed. Assemble and review again.')
            engine.apply_preview(document,operation);window.destroy();self.app.refresh();self.decode(record=False)
        self.apply_button=ttk.Button(window,text='Apply bounded overwrite to project',state='normal' if operation['edits'] else 'disabled',command=lambda:self.app.run(apply));self.apply_button.pack(side='bottom',fill='x',pady=12,before=window.winfo_children()[0])
        return operation

    def close(self):
        if self.closed:return
        self.closed=True;self.unsubscribe();self.window.destroy()


def open_workspace(app):
    document=app.need();old=getattr(app,'code_workspace',None)
    if old and not old.closed:
        if old.document is document:old.window.lift();return old
        old.close()
    app.code_workspace=Workspace(app);return app.code_workspace
