"""Read-only map table and graph; intentionally has no edit commands."""
import math,struct
import tkinter as tk
from tkinter import ttk
from .core import TYPES,map_values,axis_values,number
from .codeblocks import map_name

BACKGROUND='#2a2e37'


class ReferenceView:
    def __init__(self,parent,data,m,active,active_m):
        for widget in parent.winfo_children():widget.destroy()
        style=ttk.Style(parent)
        style.configure('Reference.Treeview',background=BACKGROUND,fieldbackground=BACKGROUND,foreground='#e6e9f0',font=('Consolas',10),rowheight=30)
        style.configure('Reference.Treeview.Heading',background='#343946',foreground='#e6e9f0',padding=8)
        style.configure('Reference.TCombobox',fieldbackground='#343946',background=BACKGROUND,foreground='#e6e9f0')
        style.map('Reference.TCombobox',fieldbackground=[('readonly','#343946')],foreground=[('readonly','#e6e9f0')])
        body=tk.Frame(parent,bg=BACKGROUND,padx=10,pady=10);body.pack(fill='both',expand=True)
        self.body=body;self.data=bytes(data);self.definition=m
        def label(text,size=10):
            widget=tk.Label(body,text=text,bg=BACKGROUND,fg='#e6e9f0',anchor='w',justify='left',font=('Segoe UI Semibold' if size>10 else 'Segoe UI',size),wraplength=460);widget.pack(fill='x',pady=(0,7));return widget
        label('REFERENCE · READ-ONLY',11)
        label(map_name(data,m),13)
        label(f'0x{number(m["address"]):06X} · {m["rows"]} × {m["columns"]} · {m["unit"] or "raw units"}')
        self.mode=tk.StringVar(value='Physical');self.graph=tk.StringVar(value='3D surface' if m['rows']>1 and m['columns']>1 else '2D curve')
        controls=tk.Frame(body,bg=BACKGROUND);controls.pack(fill='x',pady=(0,10))
        mode=ttk.Combobox(controls,textvariable=self.mode,values=('Physical','Raw'),state='readonly',width=10,style='Reference.TCombobox');mode.pack(side='left')
        graph=ttk.Combobox(controls,textvariable=self.graph,values=('3D surface','2D curve'),state='readonly',width=12,style='Reference.TCombobox');graph.pack(side='right')
        self.row=0
        if m['rows']==m['columns']==1:
            graph.destroy()
            self.scalar=label('',27);self.table=None;self.canvas=None
            def redraw(*_):
                values=self.values();self.scalar.configure(text=f'{values[0]:g} '+('raw' if self.mode.get()=='Raw' else m['unit']))
            label('Reference value cannot be edited.');mode.bind('<<ComboboxSelected>>',redraw);redraw();return
        # Reserve the editable side's toolbar space so corresponding rows align.
        # Measure actual widget geometry rather than assume a font/DPI height.
        self.alignment_spacer=tk.Frame(body,bg=BACKGROUND,height=1)
        self.alignment_spacer.pack(fill='x')
        self._align_target=None;self._align_pending=None
        def cancel_alignment(event):
            if event.widget is body and self._align_pending is not None:
                body.after_cancel(self._align_pending);self._align_pending=None
        body.bind('<Destroy>',cancel_alignment,add='+')
        footer=label('Amber values differ from the active map.\nReference values and axes cannot be edited.')
        footer.pack_forget();footer.pack(side='bottom',fill='x',pady=(8,0))
        split=ttk.Panedwindow(body,orient='vertical');split.pack(fill='both',expand=True)
        frame=tk.Frame(split,bg=BACKGROUND);split.add(frame,weight=3)
        columns=[str(i) for i in range(m['columns'])]
        order=list(reversed(columns)) if m.get('x_axis',{}).get('display_backwards') else columns
        self.table=ttk.Treeview(frame,columns=columns,displaycolumns=order,show='tree headings',height=min(12,m['rows']),style='Reference.Treeview',selectmode='browse')
        self.table.heading('#0',text='Y · '+(m.get('y_axis',{}).get('name') or 'Row'));self.table.column('#0',width=110,stretch=False)
        for i,value in enumerate(axis_values(data,m,'x_axis')):
            self.table.heading(str(i),text=f'{value:g}');self.table.column(str(i),width=90,stretch=False,anchor='e')
        self.table.grid(row=0,column=0,sticky='nsew');vs=ttk.Scrollbar(frame,orient='vertical',command=self.table.yview);vs.grid(row=0,column=1,sticky='ns');hs=ttk.Scrollbar(frame,orient='horizontal',command=self.table.xview);hs.grid(row=1,column=0,sticky='ew');self.table.configure(yscrollcommand=vs.set,xscrollcommand=hs.set);frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        self.table.tag_configure('different',foreground='#ffd18c')
        self.canvas=tk.Canvas(split,bg=BACKGROUND,highlightthickness=0,height=210);split.add(self.canvas,weight=2)
        self.active=active;self.active_map=active_m
        mode.bind('<<ComboboxSelected>>',lambda e:self.render());graph.bind('<<ComboboxSelected>>',lambda e:self.plot())
        self.canvas.bind('<Configure>',lambda e:self.plot());self.table.bind('<<TreeviewSelect>>',self.select_row)
        self.render()

    def align_with(self,table):
        if self.table is None or table is None:return
        self._align_target=table
        self.table.bind('<Map>',lambda e:self.queue_alignment(),add='+')
        self.table.bind('<Configure>',lambda e:self.queue_alignment(),add='+')
        table.bind('<Configure>',lambda e:self.queue_alignment(),add='+')
        self.queue_alignment()

    def queue_alignment(self):
        if self._align_pending is None:self._align_pending=self.body.after_idle(self.align_headers)

    def align_headers(self):
        self._align_pending=None;table=self._align_target
        if table is None or not table.winfo_exists() or not self.table.winfo_exists():return
        if not table.winfo_ismapped() or not self.table.winfo_ismapped():return
        delta=table.winfo_rooty()-self.table.winfo_rooty()
        if abs(delta)>1:
            self.alignment_spacer.configure(height=max(0,self.alignment_spacer.winfo_height()+delta))

    def values(self,data=None,m=None):
        data=self.data if data is None else data;m=self.definition if m is None else m
        if self.mode.get()=='Physical':return map_values(data,m)
        fmt=('<' if m['endian']=='little' else '>')+TYPES[m['type']];width=struct.calcsize(fmt)
        return [struct.unpack_from(fmt,data,number(m['address'])+i*width)[0] for i in range(m['rows']*m['columns'])]

    def render(self):
        m=self.definition;values=self.values();other=self.values(self.active,self.active_map)
        self.table.delete(*self.table.get_children());axis=axis_values(self.data,m,'y_axis')
        rows=range(m['rows']-1,-1,-1) if m.get('y_axis',{}).get('display_backwards') else range(m['rows'])
        for row in rows:
            start=row*m['columns'];items=[];changed=False
            for i in range(start,start+m['columns']):
                different=values[i]!=other[i];changed|=different;items.append(f'{values[i]:g}'+(' *' if different else ''))
            self.table.insert('','end',iid=str(row),text=f'{axis[row]:g}',values=items,tags=('different',) if changed else ())
        self.plot()

    def select_row(self,_):
        selected=self.table.selection()
        if selected:self.row=int(selected[0]);self.plot()

    def plot(self):
        if self.canvas is None:return
        canvas=self.canvas;canvas.delete('all');m=self.definition;v=self.values();width=max(200,canvas.winfo_width());height=max(100,canvas.winfo_height())
        if not all(math.isfinite(x) for x in v):return
        low,high=min(v),max(v);span=max(high-low,1e-9)
        canvas.create_text(12,12,text=f'Reference · {low:g} – {high:g} '+('raw' if self.mode.get()=='Raw' else m['unit']),fill='#e6e9f0',anchor='nw')
        if self.graph.get()=='3D surface' and m['rows']>1 and m['columns']>1:
            rows=sorted({round(i*(m['rows']-1)/min(32,m['rows']-1)) for i in range(min(32,m['rows']-1)+1)})
            columns=sorted({round(i*(m['columns']-1)/min(32,m['columns']-1)) for i in range(min(32,m['columns']-1)+1)})
            def point(r,c):
                x=c/(m['columns']-1);y=r/(m['rows']-1);z=(v[r*m['columns']+c]-low)/span
                return width/2+(x-y)*width*.38,height*.55+(x+y)*height*.16-z*height*.40
            for r1,r2 in reversed(list(zip(rows,rows[1:]))):
                for c1,c2 in zip(columns,columns[1:]):
                    points=((r1,c1),(r1,c2),(r2,c2),(r2,c1));q=sum((v[r*m['columns']+c]-low)/span for r,c in points)/4
                    colour=f'#{int(45+190*q):02x}{int(130-55*q):02x}{int(160-105*q):02x}'
                    canvas.create_polygon(*[value for r,c in points for value in point(r,c)],fill=colour,outline='#454b57')
        else:
            points=v if m['columns']==1 else v[self.row*m['columns']:(self.row+1)*m['columns']];coords=[]
            for i,value in enumerate(points):coords.extend((20+i*(width-40)/max(1,len(points)-1),height*.85-(value-low)/span*height*.6))
            if len(coords)>2:canvas.create_line(*coords,fill='#ffb38f',width=2)
