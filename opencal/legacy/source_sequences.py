"""GPL-3.0-only. Port of selected ZedSuite EDC15P source passes.

Copyright (C) 2026 ZedPerf. Modified for OpenCal 2026-10-18.
Upstream edc15p/mod.rs: find_svbl_sequence, find_map_maf_switch,
find_pid_maps, find_selector_for_injector_duration, detect_soi_maps_by_selector,
fix_injector_duration_maps (complete six-map chains), detect_vcds_diag_sequences.
Standard banks only. Diagnostic display limits are not engine torque limits.
Also adapted from edc15p/early.rs EGR hysteresis and egr_temperature.rs.
"""
import re,struct


def source_maps(data,bases):
    from .edc15 import _map,AXIS_IDS
    found={}
    def add(a,rows,cols,name,category,factor=1,unit='raw'):
        m=_map(a,rows,cols,name+' (source candidate)',category,factor,unit=unit)
        m['evidence']='Adapted from ZedSuite Rust edc15p/mod.rs sequence pass; standard bank bounds checked.'
        found[a]=m
        return m
    for base in bases:
        start,end=base-0x4000,base+0xc000
        region=data[start:end]
        curves=[]; idle_count=0
        for p in range(start,end-90,2):
            ident,n=struct.unpack_from('<HH',data,p); high=ident>>8
            if high not in AXIS_IDS or not 1<=n<=32 or p+4+n*4>end: continue
            vals=list(struct.unpack_from('<'+'H'*n,data,p+4)); a=p+4+n*2
            increasing=all(x<y for x,y in zip(vals,vals[1:]))
            next_id,next_n=struct.unpack_from('<HH',data,a)
            single=not(next_id>>8 in AXIS_IDS and 1<=next_n<=32 and a+4+next_n*2<=end)
            if n==2 and high==0xc1 and increasing and idle_count<2:
                raw=struct.unpack_from('<2H',data,a)
                if all(700<=v<=1400 for v in raw):
                    m=add(a,1,2,'Idle RPM','Idle / Governor',unit='rpm'); idle_count+=1
                    m['x_axis']={'address':p+4,'type':'u16','endian':'little','factor':.1,'offset':-273.1,'values':[v*.1-273.1 for v in vals],'name':'Coolant temperature','unit':'°C'}
            if n==2 and ident in (0xeba2,0xeba4,0xe9bc):
                raw=struct.unpack_from('<2H',data,a)
                if 50<=raw[0]<=600 and 1500<=raw[1]<=7000 and raw[0]<raw[1]:
                    m=add(a,1,2,'MAP linearisation','MAP sensor',unit='mbar')
                    m['x_axis']={'address':p+4,'values':vals,'name':'Sensor axis','unit':'raw'}
            if n==16 and high==0xec and increasing and single:
                m=add(a,1,16,'Boost actuator upper limit curve (N75)','Turbo boost pressure control',.01,'%')
                m['x_axis']={'address':p+4,'values':vals,'name':'Engine speed','unit':'rpm'}
            if n in (19,20) and high in (0xea,0xec) and increasing and vals[0]<=100 and 2500<=vals[-1]<=6500:
                raw=struct.unpack_from('<'+'h'*n,data,a)
                if all(-100<=v<=12000 for v in raw): curves.append((a,n,vals))
            if n==5 and high in (0xec,0xea,0xda,0xc0) and increasing and vals[0]<=1500 and vals[-1]<=6500 and data[p+15:p+18]==b'\xc1\x06\0':
                temps=struct.unpack_from('<6H',data,p+18)
                if all(x<y for x,y in zip(temps,temps[1:])) and 1500<=temps[0] and temps[-1]<=5000 and temps[-1]-temps[0]>=100:
                    m=add(p+30,5,6,'EGR temperature map','EGR')
                    m['x_axis']={'address':p+18,'type':'u16','endian':'little','factor':.1,'offset':-273,'values':[v*.1-273 for v in temps],'name':'Temperature','unit':'°C'}
                    m['y_axis']={'address':p+4,'values':vals,'name':'Engine speed','unit':'rpm','display_backwards':True}
        for (a,n,vals),(b,nb,vals_b) in zip(curves,curves[1:]):
            if n!=nb or not 4+4*n<=b-a<=8+4*n: continue
            for index,(addr,values) in enumerate([(a,vals),(b,vals_b)],1):
                m=add(addr,1,n,f'EGR hysteresis {index}','EGR',.01,'mg/st'); m['type']='i16'
                m['x_axis']={'address':addr-n*2,'values':values,'name':'Engine speed','unit':'rpm'}
            break
        for match in re.finditer(re.escape(bytes.fromhex('0A 00 4D 09 E3 09 47 0A')),region):
            p=start+match.start()
            if p+74>end: continue
            m=add(p+22,1,10,'BIP temperature correction','Injection system',.023437,'degrees crank angle')
            m['x_axis']={'address':p+2,'type':'u16','endian':'little','factor':.1,'offset':-273.1,'values':[v*.1-273.1 for v in struct.unpack_from('<10H',data,p+2)],'name':'Temperature','unit':'°C'}
            if data[p+43:p+46]==b'\xc5\x07\0':
                m=add(p+60,1,7,'BIP SOI correction','Injection system',.023437,'degrees crank angle'); m['type']='i16'
                m['x_axis']={'address':p+46,'type':'i16','endian':'little','factor':.023437,'offset':0,'values':[v*.023437 for v in struct.unpack_from('<7h',data,p+46)],'name':'SOI delta','unit':'degrees'}
            if p>=start+206:
                for q in range(max(start,p-606),p-206-43,2):
                    if data[q+1:q+4]!=b'\xc5\x0a\0': continue
                    axis=struct.unpack_from('<10H',data,q+4); raw=struct.unpack_from('<10H',data,q+24)
                    if all(x<y for x,y in zip(axis,axis[1:])) and 100<=axis[0] and axis[-1]<=1023 and all(x>y for x,y in zip(raw,raw[1:])) and raw[-1]>=300 and raw[0]<=3000:
                        m=add(q+24,1,10,'BIP basic characteristic','Injection system')
                        m['x_axis']={'address':q+4,'values':list(axis),'name':'Voltage','unit':'raw'}; break
        match=re.search(re.escape(bytes.fromhex('27 00 00 64 00')),region)
        if match and start+match.start()+7<=end: add(start+match.start()+5,1,1,'Left foot brake switch','Switches')
        candidates=[]
        for match in re.finditer(re.escape(bytes.fromhex('DF 7A 28 00')),region):
            p=start+match.start(); a=p-(4 if data[p-2:p]==b'\0\xc3' else 2)
            if a>=start: candidates.append(a)
        header=bytes.fromhex('D2 00 FC 03 00 00 00 00 04 00')
        for match in re.finditer(re.escape(header),region):
            p=start+match.start()
            if p+20<=end and data[p+13:p+16]==b'\xc3\0\0' and data[p+18:p+20]==b'\0\xc3': candidates.append(p+16)
        for a in candidates:
            value=int.from_bytes(data[a:a+2],'little')
            if value==0 or 1000<=value<=7000: add(a,1,1,'SVBL','Turbo boost pressure',unit='mbar')
        for match in re.finditer(rb'\x00\x01\x01[\s\S]\x01[\x41\x01]\x02[\s\S]{2}\x00\x01',region):
            add(start+match.start()+7,1,1,'MAP/MAF switch','Smoke limitation'); break
        axes=[]; selectors=[]
        for p in range(start,end-68):
            if data[p+1:p+4]==b'\xc0\x10\0':
                axis=struct.unpack_from('<16H',data,p+4)
                if all(a<=b for a,b in zip(axis,axis[1:])) and axis[0]<axis[-1]<5000: axes.append(p+4)
        if len(axes)==4 and axes[3]-axes[0]<=0x400:
            for axis,name in zip(axes,['I amplification','D amplification','DT1 memory factor','P amplification']):
                m=add(axis+32,1,16,'PID map - '+name,'Turbo boost pressure control',0.0001)
                m['type']='i16'; m['x_axis']={'address':axis,'values':list(struct.unpack_from('<16H',data,axis)),'name':'Boost deviation','unit':'mbar'}
        for a in range(start+16,end-12,2):
            if data[a+2:a+12]!=struct.pack('<5H',256,512,768,1024,1280) or int.from_bytes(data[a:a+2],'little')>512: continue
            axis_id,n=struct.unpack_from('<HH',data,a-16)
            vals=struct.unpack_from('<6H',data,a-12)
            if axis_id>>8 in AXIS_IDS and n==6 and all(1500<=v<=4500 for v in vals): selectors.append(a)
        if selectors:
            a=min(selectors,key=lambda a:abs(a-start-0x945c))
            m=add(a,6,1,'Selector for injector duration','Injection system',0.003906)
            m['y_axis']={'address':a-12,'type':'u16','endian':'little','factor':-.023437,'offset':78,'values':[78-v*0.023437 for v in struct.unpack_from('<6H',data,a-12)],'name':'SOI','unit':'degrees BTDC','display_backwards':True}
        # Temperature-selected SOI family. Require both shared axes rather than
        # emitting editable maps with unknown axes when the source search fails.
        for t in range(start+4480,end-24,2):
            if data[t+1:t+4]!=b'\xc5\x0a\0': continue
            temps=[round(v/10-273.15) for v in struct.unpack_from('<10H',data,t+4)]
            if any(not -40<=v<=110 for v in temps) or temps[0]>10 or temps[-1]<85 or any(b<a-5 for a,b in zip(temps,temps[1:])): continue
            first=t-4480; shared={}
            for p in range(max(start,first-3000),first-3,2):
                ident,n=struct.unpack_from('<HH',data,p)
                if (ident>>8,n) not in ((0xf9,16),(0xeb,14)) or p+4+2*n>first: continue
                vals=list(struct.unpack_from('<'+'H'*n,data,p+4))
                asc=all(a<b for a,b in zip(vals,vals[1:])); desc=all(a>b for a,b in zip(vals,vals[1:]))
                if n==16 and ((100<=vals[0]<=1000 and 3000<=vals[-1]<=6000) or ((asc or desc) and min(vals)<=1500 and 2500<=max(vals)<=7000)):
                    shared.setdefault('y',{'address':p+4,'values':vals,'name':'Engine speed','unit':'rpm'})
                if n==14 and (vals[0]==0 or (asc and vals[0]<=1500 and vals[-1]<=9000)):
                    shared.setdefault('x',{'address':p+4,'type':'u16','endian':'little','factor':.01,'offset':0,'values':[v*.01 for v in vals],'name':'IQ','unit':'mg/st'})
            if len(shared)!=2: continue
            selector=add(t+4,1,10,'SOI selector','Injection system',.1,'°C'); selector['offset']=-273.1
            for slot,temp in enumerate(temps):
                m=add(first+slot*448,16,14,f'Start of injection (SOI) {temp}°C','Injection system',-.023437,'degrees BTDC')
                m.update(offset=78,x_axis=shared['x'],y_axis=shared['y'],selector_address=t,selector_slot=slot)
        # Duration chain, retaining raw storage rows/columns. Do not swap axis
        # factors without transposing the actual data grid.
        chains={}; p=start
        while p+8<end:
            ident,n=struct.unpack_from('<HH',data,p)
            if ident>>8 not in (0xc4,0xc5) or not 6<=n<=20 or p+8+n*2>end: p+=2; continue
            iq=list(struct.unpack_from('<'+'H'*n,data,p+4)); r=p+4+n*2
            rid,nr=struct.unpack_from('<HH',data,r)
            if rid>>8 not in (0xea,0xec) or not 8<=nr<=20 or r+4+nr*2>end: p+=2; continue
            rpm=list(struct.unpack_from('<'+'H'*nr,data,r+4)); a=r+4+nr*2; size=n*nr*2
            if not(all(x<y for x,y in zip(iq,iq[1:])) and iq[0]<=2000 and 1500<=iq[-1]<=10000 and all(x<y for x,y in zip(rpm,rpm[1:])) and 2000<=rpm[-1]<=6000 and 100<=size<=700 and a+size<=end): p+=2; continue
            chains.setdefault(ident,[]).append((a,n,nr,p+4,r+4,iq,rpm)); p=a+size
        if chains:
            chain=max(chains.values(),key=len)
            if len(chain)==6:
                for slot,(a,n,nr,ia,ra,iq,rpm) in enumerate(chain):
                    m=add(a,n,nr,f'Injector duration {slot:02}','Injection system',.023437,'degrees crank angle')
                    m['type']='u16' if slot==0 else 'i16'
                    m['x_axis']={'address':ra,'values':rpm,'name':'Engine speed','unit':'rpm'}
                    m['y_axis']={'address':ia,'type':'u16','endian':'little','factor':.01,'offset':0,'values':[v*.01 for v in iq],'name':'IQ','unit':'mg/st'}
        for match in re.finditer(re.escape(bytes.fromhex('01 69 10 0F 05 09')),region):
            p=start+match.start()
            if p+226>end: continue
            entries=[(off,f'VCDS Diagnostic IQ Limit {i+1}',.00390625,-.15234375,'mg/st',True) for i,off in enumerate([8,52,60,104,116,120,140,192,216,224])]
            entries += [(off,f'VCDS Diagnostic MAP Limit {i+1}',.1,0,'mbar',False) for i,off in enumerate([24,28,68])]
            entries.append((184,'VCDS Diagnostic Torque Limit',.00390625,-.203125,'display units',True))
            for off,name,factor,offset,unit,signed in entries:
                m=add(p+off,1,1,name,'VCDS diagnostic',factor,unit)
                m['offset']=offset; m['type']='i16' if signed else 'u16'
                m['description']='Diagnostic display ceiling; this does not establish the ECU engine-control limit.'
        for match in re.finditer(re.escape(bytes.fromhex('D4 FE 91 00 B6 FE 8C 05 B6 FE')),region):
            p=start+match.start()
            if p+144>end: continue
            word=lambda off:struct.unpack_from('<H',data,p+off)[0]
            iq=126 if word(134)==word(138)==word(142) else 138
            for off,name,mult,unit in [(42,'Torque',1000,'Nm'),(66,'MAP',10000,'mbar'),(iq,'IQ',100,'mg/st')]:
                m=add(p+off,1,1,f'VCDS Diagnostic {name} Display scaling','VCDS diagnostic')
                m['type']='i16'; m['description']=f'Diagnostic display scaling only. Maximum displayed = 255 / raw value × {mult} {unit}; zero has no defined conversion.'
    # The remaining axes above use literal unsigned 16-bit engine/sensor values.
    for m in found.values():
        for key in ('x_axis','y_axis'):
            axis=m.get(key,{})
            if axis and 'type' not in axis:
                axis.update(type='u16',endian='little',factor=1,offset=0)
    return found
