"""A bounded, virtual hex viewport with file-wide scrolling."""
import tkinter as tk
from tkinter import ttk,font as tkfont
from .core import number


def build(app):
    tab=app.hex_tab;bar=ttk.Frame(tab,padding=(8,10));bar.pack(fill='x')
    app.address=tk.StringVar(value='0x0')
    ttk.Label(bar,text='Byte address').pack(side='left')
    ttk.Entry(bar,textvariable=app.address,width=13).pack(side='left',padx=8)
    for label,fn in [('Go',app.goto),('Edit bytes…',app.edit_hex),('Find hex…',app.find)]:
        ttk.Button(bar,text=label,command=lambda f=fn:app.run(f)).pack(side='left',padx=3)
    app.hex_range=tk.StringVar(value='Open a BIN to inspect bytes')
    ttk.Label(tab,textvariable=app.hex_range,style='Muted.TLabel',padding=(12,4)).pack(fill='x')
    ttk.Label(tab,text='Scroll through the entire BIN · click a byte to select its address · yellow = modified',style='Muted.TLabel',padding=(12,8)).pack(side='bottom',fill='x')
    frame=ttk.Frame(tab);frame.pack(fill='both',expand=True)
    app.hex=tk.Text(frame,font=('Consolas',11),wrap='none',state='disabled',background='#181b23',foreground='#e6e9f0',padx=12,pady=10,borderwidth=0,highlightthickness=0)
    app.hex.grid(row=0,column=0,sticky='nsew')
    app.hex_scroll=ttk.Scrollbar(frame,orient='vertical',command=lambda *args:scroll(app,*args));app.hex_scroll.grid(row=0,column=1,sticky='ns')
    horizontal=ttk.Scrollbar(frame,orient='horizontal',command=app.hex.xview);horizontal.grid(row=1,column=0,sticky='ew');app.hex.configure(xscrollcommand=horizontal.set)
    frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    app.hex.tag_configure('changed',foreground='#ffcf69',background='#493d28')
    app.hex.tag_configure('address',foreground='#8896ab');app.hex.tag_configure('selected_byte',background='#fa633b',foreground='white')
    def wheel(event):
        if app.doc and event.delta:scroll(app,'scroll',-max(1,abs(event.delta)//120)*(1 if event.delta>0 else -1)*3,'units')
        return 'break'
    app.hex.bind('<MouseWheel>',wheel)
    for key,direction in [('<Next>',1),('<Prior>',-1),('<Down>',1),('<Up>',-1)]:
        app.hex.bind(key,lambda e,n=direction,k=key:(scroll(app,'scroll',n,'pages' if k in ('<Next>','<Prior>') else 'units'),'break')[1])
    app.hex.bind('<Control-Home>',lambda e:(scroll(app,'moveto',0),'break')[1])
    app.hex.bind('<Control-End>',lambda e:(scroll(app,'moveto',1),'break')[1])
    app.hex.bind('<ButtonRelease-1>',lambda e:select_byte(app,e.x,e.y))
    app.hex.bind('<Configure>',lambda e:render(app) if app.doc else None)


def visible_rows(app):
    font=tkfont.Font(font=app.hex['font'])
    return max(1,(app.hex.winfo_height()-20)//max(1,font.metrics('linespace')))


def render(app):
    if not app.doc:return
    data=app.doc.data;rows=visible_rows(app);total=(len(data)+15)//16
    first=max(0,min(app.page//16,max(0,total-rows)));app.page=first*16
    x=app.hex.xview()[0]
    app.hex.configure(state='normal');app.hex.delete('1.0','end')
    for row,a in enumerate(range(app.page,min(app.page+rows*16,len(data)),16),1):
        app.hex.insert('end',f'{a:08X}  ','address')
        for j in range(16):
            i=a+j
            if i<len(data):app.hex.insert('end',f'{data[i]:02X} ','changed' if data[i]!=app.doc.original[i] else ())
            else:app.hex.insert('end','   ')
        app.hex.insert('end','  '+''.join(chr(v) if 32<=v<127 else '.' for v in data[a:a+16])+('\n' if row<min(rows,total-first) else ''))
    app.hex.configure(state='disabled');app.hex.xview_moveto(x)
    app.hex_scroll.set(first/total,min(1,(first+rows)/total))
    app.hex_range.set(f'0x{app.page:08X}–0x{min(len(data),app.page+rows*16)-1:08X} · {len(data):,} bytes · offsets from the start of the BIN')
    highlight(app)


def scroll(app,action,value,unit=None):
    if not app.doc:return
    total=(len(app.doc.data)+15)//16;rows=visible_rows(app)
    if action=='moveto':first=round(float(value)*total)
    else:first=app.page//16+int(value)*(max(1,rows-1) if unit=='pages' else 1)
    first=max(0,min(first,max(0,total-rows)))
    app.page=first*16;app.address.set(hex(app.page));render(app)


def highlight(app):
    app.hex.tag_remove('selected_byte','1.0','end')
    try:a=number(app.address.get())
    except ValueError:return
    row=(a-app.page)//16+1;j=a%16
    if app.doc and app.page<=a<min(app.page+visible_rows(app)*16,len(app.doc.data)):
        app.hex.tag_add('selected_byte',f'{row}.{10+3*j}',f'{row}.{12+3*j}')
        app.hex.tag_add('selected_byte',f'{row}.{60+j}',f'{row}.{61+j}')


def select_byte(app,x,y):
    if not app.doc:return
    row,col=map(int,app.hex.index(f'@{x},{y}').split('.'))
    if 10<=col<58:j=(col-10)//3
    elif 60<=col<76:j=col-60
    else:return
    a=app.page+(row-1)*16+j
    if a<len(app.doc.data):app.address.set(hex(a));highlight(app)
