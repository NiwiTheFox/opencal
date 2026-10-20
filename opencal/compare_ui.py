"""Two live comparison windows sharing the active project's edit history."""
import bisect,json,struct
import tkinter as tk
from tkinter import ttk,font as tkfont,simpledialog as sd
from pathlib import Path
from .core import digest,differences,number,map_values,axis_values
from .compare import changed_maps,reference_map,map_difference
from .codeblocks import map_name,codeblock


class MapHost:
    def __init__(self,session,editor):
        self.session=session;self.editor=editor;self.root=session.map_window;self.status=session.app.status
        self.compact=True
    @property
    def doc(self):return self.session.app.doc
    def need(self):return self.session.need()
    def run(self,fn):return self.session.app.run(fn)
    def refresh(self):self.session.app.refresh()


class Comparison:
    def __init__(self,app,reference,path):
        self.app=app;self.document=app.need();self.reference=bytes(reference);self.path=str(path);self.pending=None;self.cache=None;self.closed=False
        self.first=0;self.selected=0;self.selected_map=None;self.differences=[];self.starts=[];self.refreshing=False
        self.hex_window=tk.Toplevel(app.root);self.hex_window.title('OpenCal • Hex comparison');self.hex_window.geometry('1280x760');self.hex_window.minsize(820,500)
        self.map_window=tk.Toplevel(app.root);self.map_window.title('OpenCal • Changed maps');self.map_window.geometry('1380x880');self.map_window.minsize(1050,650)
        self.hex_window.protocol('WM_DELETE_WINDOW',lambda:self.close_window(self.hex_window));self.map_window.protocol('WM_DELETE_WINDOW',lambda:self.close_window(self.map_window))
        self.build_hex();self.build_maps();self.unsubscribe=self.document.subscribe(self.schedule)
        self.hex_window.bind('<Destroy>',self.destroyed,add='+');self.map_window.bind('<Destroy>',self.destroyed,add='+')
        self.refresh()

    def need(self):
        if self.closed or self.app.doc is not self.document:raise ValueError('This comparison belongs to a closed or replaced project.')
        return self.document

    def alive(self,window):
        try:return bool(window.winfo_exists())
        except tk.TclError:return False

    def destroyed(self,event):
        if event.widget in (self.hex_window,self.map_window) and not self.alive(self.hex_window) and not self.alive(self.map_window):self.close()

    def close_window(self,window):
        if self.alive(window):window.destroy()
        if not self.alive(self.hex_window) and not self.alive(self.map_window):self.close()

    def close(self):
        if self.closed:return
        self.closed=True
        if self.pending is not None:
            try:self.app.root.after_cancel(self.pending)
            except tk.TclError:pass
        self.pending=None;self.unsubscribe()
        for window in (self.hex_window,self.map_window):
            if self.alive(window):window.destroy()
        if self in getattr(self.app,'comparisons',[]):self.app.comparisons.remove(self)

    def schedule(self):
        if not self.closed and self.pending is None:self.pending=self.app.root.after_idle(self.flush)

    def flush(self):
        self.pending=None
        if self.app.doc is not self.document:self.close();return
        self.app.refresh()

    def refresh(self):
        if self.closed:return
        if self.app.doc is not self.document:self.close();return
        if self.pending is not None:
            self.app.root.after_cancel(self.pending);self.pending=None
        key=(digest(self.document.data),json.dumps(self.document.definitions,sort_keys=True))
        if key==self.cache:return
        self.cache=key;self.differences=list(differences(self.document.data,self.reference));self.starts=[a for a,b in self.differences]
        total=sum(b-a for a,b in self.differences)
        if self.alive(self.hex_window):
            self.hex_summary.set(f'{total:,} differing bytes · {len(self.differences):,} ranges · active {len(self.document.data):,} bytes / reference {len(self.reference):,} bytes')
            self.render_hex()
        if self.alive(self.map_window):self.render_maps()

    def build_hex(self):
        window=self.hex_window;bar=ttk.Frame(window,padding=12);bar.pack(fill='x')
        self.address=tk.StringVar(value='0x0');self.hex_summary=tk.StringVar()
        ttk.Label(bar,text='BIN offset').pack(side='left');ttk.Entry(bar,textvariable=self.address,width=13).pack(side='left',padx=7)
        for label,fn in [('Go',self.goto),('Edit active bytes…',self.edit_bytes),('Undo',self.app.undo),('Redo',self.app.redo)]:
            ttk.Button(bar,text=label,command=lambda f=fn:self.app.run(f)).pack(side='left',padx=3)
        navigation=ttk.Frame(window,padding=(12,0,12,8));navigation.pack(fill='x')
        for label,direction in [('Previous difference',-1),('Next difference',1)]:
            ttk.Button(navigation,text=label,command=lambda n=direction:self.app.run(lambda:self.jump(n))).pack(side='left',padx=(0,6))
        ttk.Label(window,textvariable=self.hex_summary,style='Muted.TLabel',padding=(12,0,12,8)).pack(fill='x')
        ttk.Label(window,text='Highlighted bytes differ between the files. Click either side to select an offset; editing always changes the active project. Reference is read-only.',style='Muted.TLabel',padding=(12,5),wraplength=1200).pack(side='bottom',fill='x')
        grid=ttk.Frame(window,padding=(10,0));grid.pack(fill='both',expand=True)
        self.hex_widgets=[]
        for column,title in enumerate(('Active project · editable','Reference · read-only · '+Path(self.path).name)):
            frame=ttk.Frame(grid);frame.grid(row=0,column=column,sticky='nsew',padx=3)
            ttk.Label(frame,text=title,style='Title.TLabel',wraplength=570).pack(anchor='w',pady=(4,10))
            text=tk.Text(frame,font=('Consolas',10),wrap='none',bg='#181b23',fg='#e6e9f0',insertbackground='white',state='disabled',highlightthickness=0,padx=8,pady=8,exportselection=False)
            text.pack(fill='both',expand=True);horizontal=ttk.Scrollbar(frame,orient='horizontal',command=text.xview);horizontal.pack(fill='x');text.configure(xscrollcommand=horizontal.set)
            text.tag_configure('difference',background='#57322a',foreground='#ffd18c');text.tag_configure('offset',foreground='#8e9cb2');text.tag_configure('selected_byte',background='#fa633b',foreground='white')
            text.bind('<MouseWheel>',lambda e:self.scroll_event(e));text.bind('<ButtonRelease-1>',lambda e,t=text:self.pick_byte(t,e.x,e.y))
            text.bind('<Configure>',lambda e:self.render_hex())
            for key,direction in (('<Next>',1),('<Prior>',-1),('<Down>',1),('<Up>',-1)):
                text.bind(key,lambda e,n=direction,k=key:(self.scroll('scroll',n,'pages' if k in ('<Next>','<Prior>') else 'units'),'break')[1])
            text.bind('<Control-Home>',lambda e:(self.scroll('moveto',0),'break')[1]);text.bind('<Control-End>',lambda e:(self.scroll('moveto',1),'break')[1])
            self.hex_widgets.append(text);grid.columnconfigure(column,weight=1,uniform='hex')
        self.scrollbar=ttk.Scrollbar(grid,orient='vertical',command=self.scroll);self.scrollbar.grid(row=0,column=2,sticky='ns');grid.rowconfigure(0,weight=1)

    def rows(self):
        return max(1,min((t.winfo_height()-16)//max(1,tkfont.Font(font=t['font']).metrics('linespace')) for t in self.hex_widgets))

    def render_hex(self):
        if not hasattr(self,'scrollbar') or self.closed or not self.alive(self.hex_window):return
        rows=self.rows();total=max(1,(max(len(self.document.data),len(self.reference))+15)//16)
        self.first=max(0,min(self.first,total-rows))
        for text,data in zip(self.hex_widgets,(self.document.data,self.reference)):
            x=text.xview()[0];text.configure(state='normal');text.delete('1.0','end')
            for row in range(min(rows,total-self.first)):
                a=(self.first+row)*16;text.insert('end',f'{a:08X}  ','offset')
                for j in range(16):
                    p=a+j;left=self.document.data[p] if p<len(self.document.data) else None;right=self.reference[p] if p<len(self.reference) else None
                    value=f'{data[p]:02X} ' if p<len(data) else '-- '
                    text.insert('end',value,'difference' if left!=right else ())
                text.insert('end','  '+''.join(chr(v) if 32<=v<127 else '.' for v in data[a:a+16]))
                if row<min(rows,total-self.first)-1:text.insert('end','\n')
            text.configure(state='disabled');text.xview_moveto(x)
            line=self.selected//16-self.first+1;j=self.selected%16
            if 1<=line<=rows:
                text.tag_add('selected_byte',f'{line}.{10+j*3}',f'{line}.{12+j*3}')
                if self.selected<len(data):text.tag_add('selected_byte',f'{line}.{60+j}',f'{line}.{61+j}')
        self.scrollbar.set(self.first/total,min(1,(self.first+rows)/total))

    def scroll_event(self,event):
        if event.delta:self.scroll('scroll',-max(1,abs(event.delta)//120)*(1 if event.delta>0 else -1)*3,'units')
        return 'break'

    def scroll(self,action,value,unit=None):
        total=(max(len(self.document.data),len(self.reference))+15)//16
        self.first=round(float(value)*total) if action=='moveto' else self.first+int(value)*(max(1,self.rows()-1) if unit=='pages' else 1)
        self.render_hex()

    def pick_byte(self,text,x,y):
        row,col=map(int,text.index(f'@{x},{y}').split('.'))
        j=(col-10)//3 if 10<=col<58 else col-60 if 60<=col<76 else None
        if j is None:return
        selected=(self.first+row-1)*16+j
        if selected>=max(len(self.document.data),len(self.reference)):return
        self.selected=selected;self.address.set(hex(selected));self.render_hex()

    def goto(self):
        address=number(self.address.get())
        if not 0<=address<max(len(self.document.data),len(self.reference)):raise ValueError('Offset is outside both files.')
        self.selected=address;self.first=address//16;self.render_hex()

    def jump(self,direction):
        if not self.starts:return
        index=bisect.bisect_right(self.starts,self.selected) if direction>0 else bisect.bisect_left(self.starts,self.selected)-1
        index=max(0,min(len(self.starts)-1,index));self.address.set(hex(self.starts[index]));self.goto()

    def edit_bytes(self,value=None):
        document=self.need();address=number(self.address.get())
        if not 0<=address<len(document.data):raise ValueError('There is no active-project byte at this offset. Files cannot be resized.')
        if value is None:value=sd.askstring('Edit active project bytes',f'Overwrite active bytes at 0x{address:06X}. Reference remains unchanged.',initialvalue=f'{document.data[address]:02X}',parent=self.hex_window)
        if value is None:return
        document.edit(address,bytes.fromhex(value),'Comparison hex edit');self.app.refresh()

    def build_maps(self):
        window=self.map_window;self.map_summary=tk.StringVar();bar=ttk.Frame(window,padding=12);bar.pack(fill='x')
        ttk.Label(bar,textvariable=self.map_summary,style='Muted.TLabel',wraplength=900).pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='Unmatched maps…',command=self.show_unmatched).pack(side='right')
        split=ttk.Panedwindow(window,orient='horizontal');split.pack(fill='both',expand=True,padx=12,pady=(0,12))
        side=ttk.Frame(split);split.add(side,weight=0);side.configure(width=300)
        self.map_tree=ttk.Treeview(side,columns=('changes',),show='tree headings',selectmode='browse');self.map_tree.heading('#0',text='Changed maps');self.map_tree.heading('changes',text='Cells / axes');self.map_tree.column('#0',width=330,stretch=False);self.map_tree.column('changes',width=100,stretch=False)
        self.map_tree.grid(row=0,column=0,sticky='nsew');vs=ttk.Scrollbar(side,orient='vertical',command=self.map_tree.yview);vs.grid(row=0,column=1,sticky='ns');hs=ttk.Scrollbar(side,orient='horizontal',command=self.map_tree.xview);hs.grid(row=1,column=0,sticky='ew');self.map_tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);side.rowconfigure(0,weight=1);side.columnconfigure(0,weight=1)
        detail=ttk.Frame(split);split.add(detail,weight=1)
        self.detail_label=tk.StringVar(value='Select a changed map. The reference file remains read-only.')
        ttk.Label(detail,textvariable=self.detail_label,style='Muted.TLabel',wraplength=1000).pack(fill='x',pady=(0,8))
        controls=ttk.Frame(detail);controls.pack(fill='x',pady=(0,8))
        for label,fn in [('Open in main editor',self.open_in_main),('Undo',self.app.undo),('Redo',self.app.redo)]:ttk.Button(controls,text=label,command=lambda f=fn:self.app.run(f)).pack(side='left',padx=(0,5))
        tabs=ttk.Notebook(detail);tabs.pack(fill='both',expand=True)
        pair=ttk.Panedwindow(tabs,orient='horizontal');tabs.add(pair,text='Side-by-side maps')
        left=ttk.Frame(pair);pair.add(left,weight=1)
        ttk.Label(left,text='ACTIVE PROJECT · EDITABLE',style='Muted.TLabel',padding=(10,10,10,0)).pack(fill='x')
        editor=ttk.Frame(left,padding=10);editor.pack(fill='both',expand=True)
        self.reference_frame=ttk.Frame(pair);pair.add(self.reference_frame,weight=1)
        positioned=[False]
        def balance(event):
            if not positioned[0] and event.width>300:pair.sashpos(0,event.width//2);positioned[0]=True
        pair.bind('<Configure>',balance)
        values=ttk.Frame(tabs);tabs.add(values,text='Reference & differences')
        self.map_host=MapHost(self,editor)
        self.value_tree=ttk.Treeview(values,columns=('position','active','reference','delta'),show='headings')
        for key,title,width in [('position','Cell / axis point',170),('active','Active',110),('reference','Reference',110),('delta','Active − reference',130)]:self.value_tree.heading(key,text=title);self.value_tree.column(key,width=width,anchor='w' if key=='position' else 'e')
        self.value_tree.grid(row=0,column=0,sticky='nsew');vs=ttk.Scrollbar(values,orient='vertical',command=self.value_tree.yview);vs.grid(row=0,column=1,sticky='ns');self.value_tree.configure(yscrollcommand=vs.set);values.rowconfigure(0,weight=1);values.columnconfigure(0,weight=1)
        self.value_tree.tag_configure('changed',foreground='#ffd18c');self.value_tree.bind('<Double-1>',lambda e:self.app.run(self.edit_value))
        self.value_tree.bind('<Return>',lambda e:self.app.run(self.edit_value))
        self.value_note=tk.StringVar(value='Physical values in storage order · yellow rows differ · double-click to edit the active project')
        ttk.Label(values,textvariable=self.value_note,style='Muted.TLabel',wraplength=850,padding=8).grid(row=1,column=0,sticky='ew')
        self.value_edit_button=ttk.Button(values,text='Edit selected active value / axis…',command=lambda:self.app.run(self.edit_value))
        self.value_edit_button.grid(row=2,column=0,sticky='w',padx=8,pady=(0,8))
        self.map_tree.bind('<<TreeviewSelect>>',lambda e:self.app.run(self.choose_map))
        split.bind('<Map>',lambda e:split.sashpos(0,310))
        self._listing=False;self.report={'changed':[],'unmatched':[],'matched':0}

    def render_maps(self):
        self.report=changed_maps(self.document.data,self.reference,self.document.definitions);report=self.report
        self.map_summary.set(f'{len(report["changed"])} changed maps · {report["matched"]} compatible maps · {len(report["unmatched"])} unmatched\nReference: {Path(self.path).name} · active project edits update every view')
        self._listing=True;view=self.map_tree.yview()
        open_state={}
        def remember(parent=''):
            for item in self.map_tree.get_children(parent):
                if item.startswith(('block:','category:')):open_state[item]=bool(self.map_tree.item(item,'open'));remember(item)
        remember();first_selection=self.selected_map is None;parents=set()
        self.map_tree.delete(*self.map_tree.get_children())
        for item in report['changed']:
            m=item['map'];block=codeblock(self.document.data,m);parent=''
            if block:
                parent=f'block:{block["base"]}'
                if parent not in parents:
                    self.map_tree.insert('','end',iid=parent,text=f'Codeblock {block["number"] if block["number"] is not None else "unknown"} · 0x{block["base"]:05X}',open=open_state.get(parent,False));parents.add(parent)
            category=f'category:{parent}:{m["category"]}'
            if category not in parents:
                self.map_tree.insert(parent,'end',iid=category,text=m['category'] or 'Other',open=open_state.get(category,True));parents.add(category)
            self.map_tree.insert(category,'end',iid=m['id'],text=map_name(self.document.data,m),values=(f'{len(item["cells"])} / {sum(map(len,item["axes"].values()))}',))
        if self.selected_map is None and report['changed']:self.selected_map=report['changed'][0]['id']
        if self.selected_map and self.map_tree.exists(self.selected_map):self.map_tree.selection_set(self.selected_map)
        if first_selection and self.selected_map:self.map_tree.see(self.selected_map)
        self.map_tree.yview_moveto(view[0] if view else 0);self._listing=False
        self.render_selected()

    def choose_map(self):
        if self._listing:return
        selected=self.map_tree.selection()
        if selected and not selected[0].startswith(('block:','category:')) and selected[0]!=self.selected_map:self.selected_map=selected[0];self.render_selected()

    def selected_definition(self):
        return next(((i,m) for i,m in enumerate(self.document.definitions['maps']) if m['id']==self.selected_map),(None,None))

    def render_selected(self):
        index,m=self.selected_definition()
        if m is None:
            self.selected_map=None
            for widget in self.map_host.editor.winfo_children():widget.destroy()
            for widget in self.reference_frame.winfo_children():widget.destroy()
            ttk.Label(self.map_host.editor,text='No changed map selected.',style='Title.TLabel').pack(anchor='w',pady=20)
            self.value_tree.delete(*self.value_tree.get_children());return
        from .map_editor import render_editor
        other,reason=reference_map(self.document.data,self.reference,m,self.document.definitions)
        self.map_host.comparison_reference=(self.reference,other) if other is not None else None
        render_editor(self.map_host,index);self.value_tree.delete(*self.value_tree.get_children())
        self.detail_label.set(map_name(self.document.data,m)+'\n'+reason+(' · map now matches reference' if not self.map_tree.exists(m['id']) and other is not None else ''))
        if other is None:
            for widget in self.reference_frame.winfo_children():widget.destroy()
            ttk.Label(self.reference_frame,text='No compatible reference map.\n'+reason,wraplength=400).pack(padx=12,pady=12);return
        from .reference_view import ReferenceView
        self.reference_view=ReferenceView(self.reference_frame,self.reference,other,self.document.data,m)
        self.reference_view.align_with(self.map_host.editor_table)
        active=map_values(self.document.data,m);reference=map_values(self.reference,other);cells,axes=map_difference(self.document.data,self.reference,m,other);cell_set=set(cells)
        self.value_note.set(('First 4,096 cells shown; counts cover the whole map. ' if len(active)>4096 else '')+'Physical values in storage order · yellow rows differ · double-click to edit active values or axes')
        # Bound the detail list; full-size comparison counts still cover all cells.
        for i,(a,b) in enumerate(zip(active[:4096],reference[:4096])):
            row,column=divmod(i,m['columns']);self.value_tree.insert('','end',iid=f'cell:{i}',values=(f'Row {row+1} · Col {column+1}',f'{a:g}',f'{b:g}',f'{a-b:g}'),tags=('changed',) if i in cell_set else ())
        for key in ('x_axis','y_axis'):
            if 'address' not in m.get(key,{}):continue
            for i,(a,b) in enumerate(zip(axis_values(self.document.data,m,key),axis_values(self.reference,other,key))):
                self.value_tree.insert('','end',iid=f'{key}:{i}',values=(f'{key[0].upper()} axis {i+1}',f'{a:g}',f'{b:g}',f'{a-b:g}'),tags=('changed',) if i in axes.get(key,[]) else ())

    def edit_value(self):
        self.need();index,m=self.selected_definition();selected=self.value_tree.selection()
        if not selected or m is None:return
        kind,position=selected[0].split(':');position=int(position)
        if kind!='cell':
            from .table_tools_ui import edit_axis
            edit_axis(self.map_host,m,kind,position);return
        value=sd.askfloat('Edit active map value',f'Physical value · {m["unit"]}',initialvalue=map_values(self.document.data,m)[position],parent=self.map_window)
        if value is not None:self.document.set_map_cell(m,position,value);self.app.refresh()

    def open_in_main(self):
        self.need();index,m=self.selected_definition()
        if m is None:raise ValueError('Select a map first.')
        self.app.search.set('');self.app.active_map=index;self.app.filter_maps();self.app.maps.selection_set(str(index));self.app.maps.see(str(index));self.app.view_map();self.app.root.lift()

    def show_unmatched(self):
        window=tk.Toplevel(self.map_window);window.title('Unmatched comparison maps');window.geometry('850x450')
        text=tk.Text(window,wrap='word',bg='#181b23',fg='#e6e9f0');text.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(window,orient='vertical',command=text.yview);scroll.pack(side='right',fill='y');text.configure(yscrollcommand=scroll.set)
        for item in self.report['unmatched']:
            m=self.document.definitions['maps'][item['index']];text.insert('end',m['name']+'\n'+item['reason']+'\n\n')
        if not self.report['unmatched']:text.insert('end','All defined maps have a compatible reference layout.')
        text.configure(state='disabled')
