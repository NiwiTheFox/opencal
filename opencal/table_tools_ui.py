"""Table and ROM-axis editing with a reviewable, atomic byte preview."""
import tkinter as tk
from tkinter import ttk,filedialog as fd
from pathlib import Path
from .core import axis_values,number
from .table_tools import (axis_preview,operation_preview,interpolation_preview,
                         csv_preview,bank_copy_preview,apply_table_preview)


def centre(w,root,width,height):
    root.update_idletasks()
    x=max(0,root.winfo_rootx()+(root.winfo_width()-width)//2)
    y=max(0,root.winfo_rooty()+(root.winfo_height()-height)//2)
    w.geometry(f'{width}x{height}+{x}+{y}')


def review(app,preview):
    document=app.need()
    w=tk.Toplevel(app.root);w.title('Review changes');centre(w,app.root,900,570);w.minsize(650,420);w.transient(app.root)
    body=ttk.Frame(w,padding=18);body.pack(fill='both',expand=True)
    ttk.Label(body,text=preview['name'],style='Title.TLabel',wraplength=820).pack(anchor='w')
    count=len(preview['edits'])
    ttk.Label(body,text=f'{count} stored value(s) will change. Apply makes one undoable project edit.',style='Muted.TLabel').pack(anchor='w',pady=(8,12))
    shared=preview.get('shared_maps',[])
    if shared:
        ttk.Label(body,text='Shared storage: '+', '.join(shared[:4])+(' …' if len(shared)>4 else ''),style='Muted.TLabel',wraplength=820).pack(anchor='w',pady=(0,12))
    frame=ttk.Frame(body);frame.pack(fill='both',expand=True)
    tree=ttk.Treeview(frame,columns=('cell','address','before','after'),show='headings',height=10)
    for key,label,width in [('cell','Cell / index',110),('address','BIN offset',110),('before','Before',220),('after','Stored after',220)]:
        tree.heading(key,text=label);tree.column(key,width=width,anchor='e' if key in ('before','after') else 'w')
    tree.grid(row=0,column=0,sticky='nsew')
    scrollbar=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);scrollbar.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scrollbar.set)
    frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    cells=preview.get('cells',[])
    # Keep even large previews responsive; hashes still bind the complete edit.
    for i,e in enumerate(preview['edits'][:2000]):
        c=cells[i] if i<len(cells) else None
        values=(f'{c["row"]}, {c["column"]}' if c else '—',f'0x{e["address"]:06X}',
                f'{c["before"]:.10g}' if c else e['before'],f'{c["after"]:.10g}' if c else e['after'])
        tree.insert('','end',values=values)
    ttk.Label(body,text=('First 2,000 changes shown. ' if count>2000 else '')+'Values are rounded to the BIN storage precision. Original file stays untouched.',style='Muted.TLabel',wraplength=820).pack(anchor='w',pady=12)
    bar=ttk.Frame(body);bar.pack(fill='x')
    def apply():
        if app.doc is not document:raise ValueError('The open project changed. Review this operation again.')
        apply_table_preview(document,preview)
        w.destroy();app.refresh();app.status.set(f'Applied {count} value change(s). Undo restores the complete operation.')
    button=ttk.Button(bar,text='Apply to project',style='Accent.TButton',state='normal' if count else 'disabled',command=lambda:app.run(apply));button.pack(side='right')
    ttk.Button(bar,text='Cancel',command=w.destroy).pack(side='right',padx=8)
    app.table_preview=preview;app.table_preview_apply=button;app.table_preview_window=w
    return w


def edit_axis(app,m,key,focus_index=0):
    d=app.need();axis=m.get(key,{})
    values=axis_values(d.data,m,key,strict=True)
    if 'type' not in axis or 'address' not in axis:raise ValueError('This axis has no editable ROM storage. Reimport a supported mappack or detect maps again.')
    original=axis_values(d.original,m,key)
    w=tk.Toplevel(app.root);w.title('Edit '+key[0].upper()+' axis');centre(w,app.root,600,600);w.minsize(470,380);w.transient(app.root)
    body=ttk.Frame(w,padding=18);body.pack(fill='both',expand=True)
    ttk.Label(body,text=f'{key[0].upper()} axis · {axis.get("name") or "Calibration breakpoints"}',style='Title.TLabel',wraplength=550).pack(anchor='w')
    ttk.Label(body,text=f'Physical values · {axis.get("unit") or "scaled units"} · ROM 0x{number(axis["address"]):06X}\n{axis["type"]} {axis["endian"]} endian · {len(values)} points in storage order',style='Muted.TLabel').pack(anchor='w',pady=(8,14))
    outer=ttk.Frame(body);outer.pack(fill='both',expand=True)
    canvas=tk.Canvas(outer,background='#101218',highlightthickness=0)
    scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
    rows=ttk.Frame(canvas);item=canvas.create_window(0,0,window=rows,anchor='nw')
    rows.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    for c,title in enumerate(('Point','Original','Current','New value')):ttk.Label(rows,text=title,style='Muted.TLabel').grid(row=0,column=c,padx=8,pady=6,sticky='w')
    drafts=[];entries=[]
    for i,(old,current) in enumerate(zip(original,values)):
        draft=tk.StringVar(value=f'{current:.12g}');drafts.append(draft)
        for c,text in enumerate((str(i+1),f'{old:.10g}',f'{current:.10g}')):ttk.Label(rows,text=text).grid(row=i+1,column=c,padx=8,pady=5,sticky='w')
        entry=ttk.Entry(rows,textvariable=draft,width=14);entry.grid(row=i+1,column=3,padx=8,pady=5,sticky='ew');entries.append(entry)
    rows.columnconfigure(3,weight=1)
    ttk.Label(body,text='These bytes may be shared by other maps. Review shows affected definitions before applying.',style='Muted.TLabel',wraplength=550).pack(anchor='w',pady=12)
    bar=ttk.Frame(body);bar.pack(fill='x')
    def preview():
        if app.doc is not d:raise ValueError('The open project changed.')
        p=axis_preview(d.data,m,key,[float(v.get()) for v in drafts],d.definitions)
        w.destroy();review(app,p)
    button=ttk.Button(bar,text='Review axis changes',style='Accent.TButton',command=lambda:app.run(preview));button.pack(side='right')
    ttk.Button(bar,text='Cancel',command=w.destroy).pack(side='right',padx=8)
    def restore():
        for var,value in zip(drafts,original):var.set(f'{value:.12g}')
    ttk.Button(bar,text='Use original',command=restore).pack(side='left')
    entries[min(max(0,focus_index),len(entries)-1)].focus_set()
    app.axis_drafts=drafts;app.axis_review_button=button;app.axis_window=w
    return w


def batch_dialog(app,m,selected_rows):
    d=app.need();w=tk.Toplevel(app.root);w.title('Edit map values');centre(w,app.root,560,330);w.transient(app.root)
    body=ttk.Frame(w,padding=20);body.pack(fill='both',expand=True)
    ttk.Label(body,text='Edit map values',style='Title.TLabel').pack(anchor='w')
    ttk.Label(body,text='Use physical values. Review the stored result before applying.',style='Muted.TLabel').pack(anchor='w',pady=(6,15))
    operation=tk.StringVar(value='Add');scope=tk.StringVar(value='Selected rows' if selected_rows else 'Whole map');amount=tk.StringVar(value='0')
    grid=ttk.Frame(body);grid.pack(fill='x')
    for r,label in enumerate(('Operation','Apply to','Amount')):ttk.Label(grid,text=label).grid(row=r,column=0,sticky='w',padx=(0,14),pady=8)
    ttk.Combobox(grid,textvariable=operation,values=['Set','Add','Percent','Interpolate endpoints','Restore original'],state='readonly',width=25).grid(row=0,column=1,sticky='ew')
    ttk.Combobox(grid,textvariable=scope,values=['Whole map']+(['Selected rows'] if selected_rows else []),state='readonly',width=25).grid(row=1,column=1,sticky='ew')
    entry=ttk.Entry(grid,textvariable=amount);entry.grid(row=2,column=1,sticky='ew');grid.columnconfigure(1,weight=1)
    def changed(*_):entry.configure(state='disabled' if operation.get() in ('Restore original','Interpolate endpoints') else 'normal')
    operation.trace_add('write',changed)
    def preview():
        if app.doc is not d:raise ValueError('The open project changed.')
        rows=selected_rows if scope.get()=='Selected rows' else None
        if operation.get()=='Interpolate endpoints':p=interpolation_preview(d.data,m,rows,d.definitions)
        else:
            indexes=None if rows is None else [r*m['columns']+c for r in rows for c in range(m['columns'])]
            p=operation_preview(d.data,m,operation.get(),0 if operation.get()=='Restore original' else float(amount.get()),indexes,d.original,d.definitions)
        w.destroy();review(app,p)
    bar=ttk.Frame(body);bar.pack(fill='x',pady=(18,0))
    ttk.Button(bar,text='Review changes',style='Accent.TButton',command=lambda:app.run(preview)).pack(side='right')
    ttk.Button(bar,text='Cancel',command=w.destroy).pack(side='right',padx=8)


def import_csv(app,m):
    d=app.need();p=fd.askopenfilename(title='Import physical values in storage order',filetypes=[('CSV','*.csv')])
    if not p:return
    path=Path(p)
    if path.stat().st_size>8*1024*1024:raise ValueError('CSV exceeds 8 MiB.')
    d.protected_paths.add(str(path.resolve()))
    review(app,csv_preview(d.data,m,path.read_text(encoding='utf-8-sig'),d.definitions))


def copy_banks(app,m):
    review(app,bank_copy_preview(app.need().data,m,app.need().definitions))
