"""Guided source-backed solutions, with a concrete byte preview before apply."""
import json,tkinter as tk
from tkinter import ttk
from .solutions import launch_control_state,preview_launch_control,apply_preview,launch_control_maps


def build_solutions(app):
    tab=app.solutions_tab
    ttk.Label(tab,text='Solutions',style='Title.TLabel').pack(anchor='w',padx=18,pady=(18,8))
    ttk.Label(tab,text='Inspect support, review the change, then apply it to this project.\nOriginal BINs are preserved; checksum correction and export remain separate.',style='Muted.TLabel').pack(anchor='w',padx=18,pady=(0,18))
    card=ttk.Frame(tab,padding=18);card.pack(fill='x',padx=10)
    ttk.Label(card,text='Launch-control speed axis',style='Title.TLabel').pack(anchor='w')
    app.solution_status=tk.StringVar(value='Open a BIN to inspect support')
    ttk.Label(card,textvariable=app.solution_status,style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=10)
    ttk.Label(card,text='Source-backed EDC15 layout change. Vehicle execution has not been verified.\nThis exposes the existing 14 × 25 calibration table; it does not install ECU multimap switching.',style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(0,12))
    buttons=ttk.Frame(card);buttons.pack(fill='x')
    for text,restore in [('Preview enable',False),('Preview restore original',True)]:
        ttk.Button(buttons,text=text,command=lambda r=restore:app.run(lambda:show_preview(app,r))).pack(side='left',padx=(0,8))
    ttk.Label(tab,text='Other available tools',style='Title.TLabel').pack(anchor='w',padx=18,pady=(28,12))
    tools=ttk.Frame(tab,padding=18);tools.pack(fill='x')
    for label,fn in [('RPM limiter (SVRL)',lambda:app.jump_to_map('SVRL')),('Boost limiter (SVBL)',lambda:app.jump_to_map('SVBL')),('Read DTC records',app.read_dtcs),('Verify checksums',app.verify_checksums)]:
        ttk.Button(tools,text=label,command=lambda f=fn:app.run(f)).pack(side='left',padx=(0,8))


def refresh_solutions(app):
    if not app.doc: app.solution_status.set('Open a BIN to inspect support');return
    state=launch_control_state(app.doc.data,app.doc.original)
    sites=state['sites'];available=sum(s['status']=='available' for s in sites);active=sum(s['status']=='active' for s in sites);custom=sum(s['status']=='custom' for s in sites)
    app.solution_status.set(f'{state["status"].capitalize()} · {available} original axes · {active} source-pattern axes · {custom} project-customised axes' if sites else state.get('reason','No supported structure found in this BIN.'))


def show_preview(app,restore=False):
    d=app.need();preview=preview_launch_control(d.data,d.original if restore else None,reference=d.original)
    w=tk.Toplevel(app.root);w.title(preview['name']);w.geometry('800x520');w.transient(app.root)
    ttk.Label(w,text=preview['name'],style='Title.TLabel',wraplength=760).pack(anchor='w',padx=18,pady=18)
    ttk.Label(w,text=f'{len(preview["edits"])} bank change(s). Only the listed axis bytes will change.\nApply changes the project in memory; source files remain untouched.',style='Muted.TLabel').pack(anchor='w',padx=18)
    tree=ttk.Treeview(w,columns=('bank','address','before','after'),show='headings',height=8)
    for col,label,width in [('bank','Bank',70),('address','Offset',90),('before','Before (hex)',270),('after','After (hex)',270)]:
        tree.heading(col,text=label);tree.column(col,width=width)
    for e in preview['edits']:tree.insert('','end',values=(f'{e["bank"]:05X}',f'{e["address"]:06X}',e['before'],e['after']))
    tree.pack(fill='both',expand=True,padx=18,pady=18)
    ttk.Label(w,text='Source port verified at byte level; ECU behaviour requires independent validation.',style='Muted.TLabel').pack(anchor='w',padx=18)
    bar=ttk.Frame(w,padding=18);bar.pack(fill='x')
    def apply():
        apply_preview(d,preview)
        app.refresh();app.status.set('Solution applied in memory. Review the new map, then verify/correct checksums before separate export.');w.destroy()
    ttk.Button(bar,text='Apply to project',style='Accent.TButton',state='normal' if preview['edits'] else 'disabled',command=lambda:app.run(apply)).pack(side='right')
    ttk.Button(bar,text='Cancel',command=w.destroy).pack(side='right',padx=8)
    app.solution_preview=preview
