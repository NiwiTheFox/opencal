"""Embedded map table, curve and 3D surface rendering. Original GPL-3.0-only."""
import csv,math,struct
import tkinter as tk
from tkinter import ttk,simpledialog as sd,filedialog as fd
from .core import map_values,number,TYPES,axis_values


def render_editor(app,index):
    d=app.need(); m=d.definitions['maps'][index]
    from .codeblocks import map_name,codeblock
    previous=getattr(app,'_editor_preferences',{})
    prefs=previous.get(m['id'],{})
    for child in app.editor.winfo_children(): child.destroy()
    host=app.editor
    ttk.Label(host,text=map_name(d.data,m),style='Title.TLabel',wraplength=1000).pack(anchor='w')
    block=codeblock(d.data,m);bank=f' · Bank base 0x{block["base"]:05X}' if block else ''
    ttk.Label(host,text=f'0x{number(m["address"]):06X}  ·  {m["rows"]} × {m["columns"]}  ·  {m["unit"] or "raw units"}  ·  {m["verification"]}'+bank,style='Muted.TLabel').pack(anchor='w',pady=(5,9))
    controls=ttk.Frame(host); controls.pack(fill='x',pady=(0,9))
    mode=tk.StringVar(value=prefs.get('mode','Physical')); graph_mode=tk.StringVar(value=prefs.get('graph','3D surface' if m['rows']>1 and m['columns']>1 else '2D curve'))
    original_visible=tk.BooleanVar(value=prefs.get('original',False))
    def remember(*_):
        previous[m['id']]={'mode':mode.get(),'graph':graph_mode.get(),'original':original_visible.get()}
        app._editor_preferences=previous
    for variable in (mode,graph_mode,original_visible): variable.trace_add('write',remember)
    if m['rows']==m['columns']==1:
        graph_mode.set('Single value')
        render_scalar(app,d,m,host,controls,mode)
        return
    ttk.Label(controls,text='Values').pack(side='left',padx=(0,5))
    units=ttk.Combobox(controls,textvariable=mode,values=['Physical','Raw'],state='readonly',width=10); units.pack(side='left')
    ttk.Checkbutton(controls,text='Show original',variable=original_visible).pack(side='left',padx=12)
    plot_select=ttk.Combobox(controls,textvariable=graph_mode,values=['3D surface','2D curve'],state='readonly',width=13); plot_select.pack(side='right')
    tools=ttk.Frame(host);tools.pack(fill='x',pady=(0,10))
    split=ttk.Panedwindow(host,orient='vertical')
    table_frame=ttk.Frame(split);split.add(table_frame,weight=3)
    cols=[str(i) for i in range(m['columns'])]
    column_order=list(reversed(cols)) if m.get('x_axis',{}).get('display_backwards') else cols
    row_order=list(range(m['rows']))
    if m.get('y_axis',{}).get('display_backwards'): row_order.reverse()
    table=ttk.Treeview(table_frame,columns=cols,show='tree headings',height=min(12,m['rows']),selectmode='extended',style='Map.Treeview')
    table.configure(displaycolumns=column_order)
    y_axis=m.get('y_axis',{})
    table.heading('#0',text='Y · '+(y_axis.get('name') or y_axis.get('unit') or 'Row')); table.column('#0',width=115,stretch=False)
    for col in cols:
        vals=axis_values(d.data,m,'x_axis')
        table.heading(col,text=f'{vals[int(col)]:g}'); table.column(col,width=90,stretch=False,anchor='e')
    table.grid(row=0,column=0,sticky='nsew')
    vs=ttk.Scrollbar(table_frame,orient='vertical',command=table.yview); vs.grid(row=0,column=1,sticky='ns')
    hs=ttk.Scrollbar(table_frame,orient='horizontal',command=table.xview); hs.grid(row=1,column=0,sticky='ew')
    table.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
    table_frame.rowconfigure(0,weight=1); table_frame.columnconfigure(0,weight=1)
    table.tag_configure('changed',foreground='#ffd18c')
    table.tag_configure('alternate',background='#1d212b')
    plot_frame=ttk.Frame(split);split.add(plot_frame,weight=2)
    canvas=tk.Canvas(plot_frame,height=205,background='#101218',highlightthickness=0);canvas.pack(fill='both',expand=True)
    positioned=[False]
    def initial_split(event):
        if not positioned[0] and event.height>100:
            split.sashpos(0,int(event.height*.62));positioned[0]=True
    split.bind('<Configure>',initial_split)
    app.editor_table=table; app.editor_canvas=canvas; app.editor_map=m
    app.editor_value_mode=mode; app.editor_graph_mode=graph_mode
    selected_row=[0]
    selected_cell=[0];inline=[None]
    selection_label=tk.StringVar(value='Select a cell · Enter or double-click to edit')
    def values(data):
        if mode.get()=='Physical': return map_values(data,m)
        fmt=('<' if m['endian']=='little' else '>')+TYPES[m['type']]; width=struct.calcsize(fmt)
        return [struct.unpack_from(fmt,data,number(m['address'])+i*width)[0] for i in range(m['rows']*m['columns'])]
    def draw_graph():
        canvas.delete('all'); v=map_values(d.data,m); w=max(canvas.winfo_width(),500)
        if not all(math.isfinite(x) for x in v):
            canvas.create_text(20,20,text='Graph unavailable: nonfinite values',anchor='nw',fill='#f5b66f'); return
        lo,hi=min(v),max(v); span=max(hi-lo,1e-9)
        canvas.create_text(14,12,text=f'{graph_mode.get()}  ·  {lo:g} – {hi:g} {m["unit"]}',anchor='nw',fill='#a7b0c2',font=('Segoe UI',10))
        if graph_mode.get()=='3D surface' and m['rows']>1 and m['columns']>1:
            # Sample at most 33x33 points. Geometry is indexed storage order;
            # explicit physical-axis values remain visible in the table headers.
            rows=sorted(set(round(i*(m['rows']-1)/min(32,m['rows']-1)) for i in range(min(32,m['rows']-1)+1)))
            cols2=sorted(set(round(i*(m['columns']-1)/min(32,m['columns']-1)) for i in range(min(32,m['columns']-1)+1)))
            def point(r,c):
                x=c/max(1,m['columns']-1); y=r/max(1,m['rows']-1); z=(v[r*m['columns']+c]-lo)/span
                return (w/2+(x-y)*min(w*.32,300),80+(x+y)*55-z*90)
            for r1,r2 in reversed(list(zip(rows,rows[1:]))):
                for c1,c2 in zip(cols2,cols2[1:]):
                    z=sum(v[r*m['columns']+c] for r,c in [(r1,c1),(r1,c2),(r2,c2),(r2,c1)])/4
                    q=(z-lo)/span; color=f'#{int(45+q*190):02x}{int(130-q*55):02x}{int(160-q*105):02x}'
                    coords=[v for r,c in [(r1,c1),(r1,c2),(r2,c2),(r2,c1)] for v in point(r,c)]
                    canvas.create_polygon(*coords,fill=color,outline='#343944',width=1)
            canvas.create_text(14,184,text='Indexed row/column surface · up to 33×33 display samples',anchor='nw',fill='#788397')
        else:
            row=min(selected_row[0],m['rows']-1); points=v[row*m['columns']:(row+1)*m['columns']]
            if m['columns']==1: points=v
            coords=[]
            for i,value in enumerate(points): coords.extend((30+i*(w-60)/max(1,len(points)-1),165-(value-lo)/span*115))
            if len(coords)>2: canvas.create_line(*coords,fill='#ff986b',width=2)
            elif coords: canvas.create_oval(coords[0]-4,coords[1]-4,coords[0]+4,coords[1]+4,fill='#ff986b')
            label='Complete column curve' if m['columns']==1 else f'Row {row+1} · select a table row to compare its curve'
            canvas.create_text(14,184,text=label,anchor='nw',fill='#788397')
        canvas.scale('all',0,0,1,max(80,canvas.winfo_height())/205)
    def redraw():
        vals,orig=values(d.data),values(d.original); table.delete(*table.get_children())
        y=axis_values(d.data,m,'y_axis')
        for r in row_order:
            a=r*m['columns']; cells=[]; changed=False
            for i in range(a,a+m['columns']):
                text=f'{vals[i]:g}'; different=vals[i]!=orig[i]; changed|=different
                if original_visible.get(): text+=f' ({orig[i]:g})'
                elif different: text+=' *'
                cells.append(text)
            tags=(('alternate',) if r%2 else ())+ (('changed',) if changed else ())
            table.insert('','end',iid=str(r),text=f'{y[r]:g}',values=cells,tags=tags)
        draw_graph()
    def cancel_inline():
        if inline[0] is not None:
            inline[0].destroy();inline[0]=None
    def edit_cell(cell=None):
        cancel_inline()
        cell=selected_cell[0] if cell is None else cell
        row,col=divmod(cell,m['columns']);table.see(str(row));table.update_idletasks()
        box=table.bbox(str(row),str(col))
        if not box:raise ValueError('Scroll the selected column into view to edit it.')
        entry=ttk.Entry(table,justify='right');entry.insert(0,f'{values(d.data)[cell]:.12g}');entry.place(x=box[0],y=box[1],width=box[2],height=box[3])
        inline[0]=entry;entry.focus_set();entry.selection_range(0,'end')
        def commit(_=None):
            value=float(entry.get().strip());physical=value if mode.get()=='Physical' else value*m['factor']+m['offset']
            d.set_map_cell(m,cell,physical);cancel_inline();app.refresh()
        entry.bind('<Return>',lambda e:app.run(commit));entry.bind('<Escape>',lambda e:cancel_inline())
        entry.bind('<FocusOut>',lambda e:cancel_inline())
        app.editor_cell_entry=entry;app.editor_cell_commit=commit
    def edit(event):
        row=table.identify_row(event.y);col=table.identify_column(event.x);region=table.identify_region(event.x,event.y)
        from .table_tools_ui import edit_axis
        if region=='heading' and col!='#0':edit_axis(app,m,'x_axis',int(column_order[int(col[1:])-1]));return
        if row and col=='#0':edit_axis(app,m,'y_axis',int(row));return
        if row and col!='#0':edit_cell(int(row)*m['columns']+int(column_order[int(col[1:])-1]))
    def pick_cell(event):
        row=table.identify_row(event.y);col=table.identify_column(event.x)
        if row and col!='#0':
            selected_cell[0]=int(row)*m['columns']+int(column_order[int(col[1:])-1])
            selection_label.set(f'Row {int(row)+1} · Column {selected_cell[0]%m["columns"]+1} · Enter to edit · Ctrl/Shift selects rows')
    def select_row(_):
        selected=table.selection()
        if selected:
            row=int(table.focus() or selected[0]);selected_row[0]=row
            selected_cell[0]=row*m['columns']+selected_cell[0]%m['columns']
            draw_graph()
    table.bind('<Button-1>',pick_cell);table.bind('<Double-1>',lambda e:app.run(lambda:edit(e))); table.bind('<<TreeviewSelect>>',select_row)
    table.bind('<Return>',lambda e:app.run(edit_cell))
    from .table_tools_ui import edit_axis,batch_dialog,import_csv,copy_banks,review
    from .table_tools import operation_preview
    ttk.Button(tools,text='Edit value',command=lambda:app.run(edit_cell)).pack(side='left',padx=(0,5))
    app.editor_edit_cell=edit_cell
    app.editor_axis_buttons={}
    for key,label in [('x_axis','Edit X axis'),('y_axis','Edit Y axis')]:
        axis=m.get(key,{})
        b=ttk.Button(tools,text=label,state='normal' if 'type' in axis and 'address' in axis else 'disabled',command=lambda k=key:app.run(lambda:edit_axis(app,m,k)))
        b.pack(side='left',padx=(0,5));app.editor_axis_buttons[key]=b
    menu_button=ttk.Menubutton(tools,text='Table actions ▾');menu_button.pack(side='left')
    menu=tk.Menu(menu_button,tearoff=False,background='#20242f',foreground='#e6e9f0');menu_button.configure(menu=menu)
    menu.add_command(label='Set, add, percent, interpolate…',command=lambda:app.run(lambda:batch_dialog(app,m,[int(r) for r in table.selection()])))
    menu.add_command(label='Restore original map…',command=lambda:app.run(lambda:review(app,operation_preview(d.data,m,'Restore original',original=d.original,definitions=d.definitions))))
    menu.add_separator();menu.add_command(label='Import CSV…',command=lambda:app.run(lambda:import_csv(app,m)))
    menu.add_command(label='Copy values to matching banks…',command=lambda:app.run(lambda:copy_banks(app,m)))
    units.bind('<<ComboboxSelected>>',lambda e:redraw()); plot_select.bind('<<ComboboxSelected>>',lambda e:draw_graph())
    original_visible.trace_add('write',lambda *_:redraw()); canvas.bind('<Configure>',lambda e:draw_graph())
    bar=ttk.Frame(host); bar.pack(side='bottom',fill='x',pady=(5,0))
    ttk.Label(bar,textvariable=selection_label,style='Muted.TLabel').pack(side='left')
    def export_csv():
        p=fd.asksaveasfilename(defaultextension='.csv')
        if p:
            d.protect(p)
            with open(p,'x',newline='',encoding='utf-8') as f:
                writer=csv.writer(f); data=map_values(d.data,m)
                for r in range(m['rows']): writer.writerow(data[r*m['columns']:(r+1)*m['columns']])
    ttk.Button(bar,text='Export CSV',command=lambda:app.run(export_csv)).pack(side='right')
    ttk.Label(host,text=f'Source: {m["source"]}',style='Muted.TLabel',wraplength=900).pack(side='bottom',anchor='w',pady=(6,0))
    split.pack(fill='both',expand=True,pady=(8,0))
    redraw()


def render_scalar(app,d,m,host,controls,mode):
    """A scalar is an editable value, not a one-point curve or 3D surface."""
    import re
    token='SVRL' if re.search(r'\bSVRL\b',m['name'],re.I) else 'SVBL' if re.search(r'\bSVBL\b',m['name'],re.I) else None
    purpose={'SVRL':'Maximum engine speed','SVBL':'Single-value boost limit'}.get(token,'Single calibration value')
    ttk.Label(controls,text='Display').pack(side='left',padx=(0,8))
    units=ttk.Combobox(controls,textvariable=mode,values=['Physical','Raw'],state='readonly',width=10); units.pack(side='left')
    card=ttk.Frame(host,padding=(20,18)); card.pack(fill='x',pady=(12,0))
    ttk.Label(card,text=purpose,style='Title.TLabel').pack(anchor='w')
    shown=tk.StringVar(); original=tk.StringVar(); draft=tk.StringVar(); stored=tk.StringVar()
    app.editor_map=m; app.editor_value_mode=mode; app.editor_scalar_value=shown; app.editor_scalar_draft=draft
    app.editor_graph_mode=tk.StringVar(value='Single value'); app.editor_table=None; app.editor_canvas=None
    ttk.Label(card,textvariable=shown,style='Scalar.TLabel').pack(anchor='w',pady=(12,4))
    ttk.Label(card,textvariable=original,style='Muted.TLabel').pack(anchor='w',pady=(0,15))
    editbar=ttk.Frame(card); editbar.pack(fill='x')
    ttk.Label(editbar,text='New value').pack(side='left',padx=(0,8))
    entry=ttk.Entry(editbar,textvariable=draft,width=15); entry.pack(side='left',padx=(0,10))
    app.editor_scalar_entry=entry
    fmt=('<' if m['endian']=='little' else '>')+TYPES[m['type']]
    def value(data):
        raw=struct.unpack_from(fmt,data,number(m['address']))[0]
        return raw if mode.get()=='Raw' else raw*m['factor']+m['offset']
    def refresh_value(*_):
        current,old=value(d.data),value(d.original)
        unit='raw' if mode.get()=='Raw' else m['unit'] or 'scaled units'
        shown.set(f'{current:g} {unit}')
        original.set(f'Original: {old:g} {unit}'+('  ·  Modified' if bytes(d.data[number(m['address']):number(m['address'])+struct.calcsize(fmt)])!=d.original[number(m['address']):number(m['address'])+struct.calcsize(fmt)] else '  ·  Unchanged'))
        draft.set(f'{current:g}')
        stored.set(f'Stored value: {struct.unpack_from(fmt,d.data,number(m["address"]))[0]:g} · {m["type"]} {m["endian"]} endian · 0x{number(m["address"]):06X}')
    def apply():
        entered=float(draft.get().strip())
        physical=entered if mode.get()=='Physical' else entered*m['factor']+m['offset']
        d.set_map_cell(m,0,physical); app.refresh()
    app.editor_scalar_apply=ttk.Button(editbar,text='Apply value',style='Accent.TButton',command=lambda:app.run(apply))
    app.editor_scalar_apply.pack(side='left')
    entry.bind('<Return>',lambda _:app.run(apply))
    ttk.Label(card,textvariable=stored,style='Muted.TLabel',wraplength=700).pack(anchor='w',pady=(16,0))
    ttk.Label(card,text='Edits stay in this project. Undo restores the previous value.',style='Muted.TLabel',wraplength=700).pack(anchor='w',pady=(8,0))
    details=ttk.Frame(host,padding=(0,18)); details.pack(fill='x')
    ttk.Label(details,text='Definition source',style='Muted.TLabel').pack(anchor='w')
    ttk.Label(details,text=m['source'],style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(4,0))
    mode.trace_add('write',refresh_value)
    refresh_value()
