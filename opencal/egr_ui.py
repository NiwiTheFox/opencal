"""Review EGR map and diagnostic changes as one reversible project edit."""
import tkinter as tk
from tkinter import ttk
from .egr import inspect,preview
from .solutions import apply_preview
from .table_tools_ui import centre


def build(app,parent):
    card=ttk.Frame(parent,padding=18);card.pack(fill='x',padx=10,pady=(12,0))
    ttk.Label(card,text='Disable EGR',style='Title.TLabel').pack(anchor='w')
    app.egr_status=tk.StringVar(value='Open a BIN to inspect support')
    ttk.Label(card,textvariable=app.egr_status,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=10)
    ttk.Label(card,text='Checked FJ / SG 1376 layout: set the EGR fresh-air request to 850 mg/st and disable its four related diagnostic codes in every matching bank.\nThis source-backed strategy has not been validated on a vehicle.',style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,12))
    buttons=ttk.Frame(card);buttons.pack(fill='x')
    ttk.Button(buttons,text='Preview disable EGR…',command=lambda:app.run(lambda:show_preview(app))).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Preview restore loaded original…',command=lambda:app.run(lambda:show_preview(app,True))).pack(side='left')


def refresh(app):
    if not app.doc:app.egr_status.set('Open a BIN to inspect support');return
    state=inspect(app.doc.data)
    if state['status']=='unsupported':app.egr_status.set(state['reason']);return
    app.egr_status.set(f'{state["maps_at_target"]}/{len(state["maps"])} request maps already at the 850 mg/st target · {state["enabled_records"]}/{len(state["records"])} EGR diagnostic records enabled.\n'+('All patch targets are present. This does not establish physical EGR operation.' if state['status']=='target present' else 'Review the exact map and diagnostic changes before applying.'))


def show_preview(app,restore=False):
    document=app.need();operation=preview(document,restore)
    window=tk.Toplevel(app.root);window.title('EGR solution · review');centre(window,app.root,980,650);window.minsize(750,500);window.transient(app.root)
    body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True)
    ttk.Label(body,text=operation['name'],style='Title.TLabel',wraplength=900).pack(anchor='w')
    count=len(operation['edits']);dtcs=sum(e['kind']=='dtc' for e in operation['edits'])
    ttk.Label(body,text=f'{operation["map_cells_changed"]} map cell(s) and {dtcs} diagnostic record(s) will change. Apply is one undo operation.\nSource BINs remain untouched; checksum correction and export are separate.',style='Muted.TLabel',wraplength=900).pack(anchor='w',pady=(10,14))
    frame=ttk.Frame(body);frame.pack(fill='both',expand=True)
    tree=ttk.Treeview(frame,columns=('bank','item','offset','change'),show='headings')
    for key,title,width in [('bank','Codeblock / bank',150),('item','Map / diagnostic',290),('offset','BIN offset',100),('change','Planned setting',290)]:
        tree.heading(key,text=title);tree.column(key,width=width,stretch=key in ('item','change'))
    tree.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);scroll.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scroll.set);frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    for m in operation['maps']:
        tree.insert('','end',values=(f'{m["codeblock"]} / {m["bank"]:05X}',m['name'],f'0x{m["address"]:06X}','Exact loaded-original map' if restore else f'{m["minimum"]:g}–{m["maximum"]:g} → 850 mg/st'+(' · already at target' if m['at_target'] else '')))
    from .codeblocks import metadata_id
    for r in operation['records']:
        tree.insert('','end',values=(f'{metadata_id(document.data,r["codeblock_base"])} / {r["codeblock_base"]:05X}',r['code']+' · '+r['description'],f'0x{r["address"]:06X}','Exact loaded-original monitoring bytes' if restore else 'Disable monitoring'+(' · already disabled' if not r['enabled'] else '')))
    ttk.Label(body,text='Restore loaded original returns to the input file, which may already contain EGR modifications.\nNo physical EGR or vehicle-execution validation is implied.',style='Muted.TLabel',wraplength=900).pack(anchor='w',pady=(12,8))
    controls=ttk.Frame(body);controls.pack(fill='x')
    def bytes_view():
        w=tk.Toplevel(window);w.title('EGR · exact byte changes');centre(w,window,1000,480)
        text=tk.Text(w,wrap='word',bg='#181b23',fg='#e6e9f0');text.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(w,orient='vertical',command=text.yview);bar.pack(side='right',fill='y');text.configure(yscrollcommand=bar.set)
        for edit in operation['edits']:text.insert('end',f'0x{edit["address"]:06X} · {edit["name"]}\nBefore: {edit["before"]}\nAfter:  {edit["after"]}\n\n')
        if not operation['edits']:text.insert('end','No byte changes are required.')
        text.configure(state='disabled')
    ttk.Button(controls,text='View exact byte changes…',command=bytes_view).pack(side='left')
    def apply():
        if app.doc is not document:raise ValueError('The active project changed. Review this EGR operation again.')
        apply_preview(document,operation);window.destroy();app.refresh();app.status.set('EGR request/diagnostic edits applied in memory. Undo restores the complete operation. Verify checksums before separate export.')
    button=ttk.Button(controls,text='Apply to project',style='Accent.TButton',state='normal' if count else 'disabled',command=lambda:app.run(apply));button.pack(side='right')
    ttk.Button(controls,text='Cancel',command=window.destroy).pack(side='right',padx=8)
    app.egr_preview=operation;app.egr_preview_window=window;app.egr_apply_button=button
