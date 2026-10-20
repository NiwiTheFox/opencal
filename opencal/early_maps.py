"""GPL-3.0-only. Bounded subset of ZedSuite edc15p/early.rs.
Copyright 2026 ZedPerf. OpenCal keeps file storage orientation and candidate labels.
"""
import struct
from collections import Counter


def classify(data,maps):
    axes=[]
    for m in maps.values():
        for key in ('x_axis','y_axis'):
            a=m.get(key)
            if not a:continue
            pos=a['address'];ident,n=struct.unpack_from('<HH',data,pos-4)
            values=struct.unpack_from('<'+'H'*n,data,pos)
            if n>=8 and 2500<=values[-1]<=6500 and values[0]<values[-1] and all(a<=b for a,b in zip(values,values[1:])):axes.append(ident)
    counts=Counter(axes)
    if not counts:return
    rpm_id,count=max(counts.items(),key=lambda x:(x[1],x[0]))
    if count<3:return
    duration_ids={};limiters={}
    def raw_axis(m,key):
        a=m[key]['address'];ident,n=struct.unpack_from('<HH',data,a-4)
        return ident,struct.unpack_from('<'+'H'*n,data,a)
    for m in maps.values():
        if not all(k in m for k in ('x_axis','y_axis')):continue
        fi,f=raw_axis(m,'y_axis');si,s=raw_axis(m,'x_axis');b=m['codeblock_base']
        if m['rows']*m['columns']==285 and si==rpm_id:duration_ids.setdefault(b,fi)
        if len(f)==14 and len(s)==11 and fi==rpm_id and all(2200<=v<=4300 for v in s):limiters.setdefault(b,m['address'])
    for m in maps.values():
        if not all(k in m for k in ('x_axis','y_axis')):continue
        fi,f=raw_axis(m,'y_axis');si,s=raw_axis(m,'x_axis');nf,ns=len(f),len(s);size=nf*ns*2;b=m['codeblock_base']
        raw=struct.unpack_from('<'+'H'*(nf*ns),data,m['address'])
        temp=lambda v:len(v)>=3 and all(2200<=x<=4300 for x in v)
        iq=lambda v:v[0]<=300 and 1500<=v[-1]<=6500 and v[0]<v[-1]
        pressure=lambda v:v[0]>=400 and v[-1]<=3500 and not temp(v)
        name=None;category='Fuel';factor=1;offset=0;xf=1;xo=0;yf=1;yo=0;unit='raw';kind='u16'
        if fi==rpm_id and (nf,ns)==(16,8) and s[0]<=400 and 6000<=s[-1]<=10000:
            name='Driver wish';category='Engine fuel request';factor=.01;xf=.01;unit='mg/st';kind='i16'
        elif fi==rpm_id and nf==16 and size in (384,416) and s[0]>=1500 and s[-1]>=5000:
            name='IQ by MAF limiter';category='Smoke limitation';factor=.01;xf=.1;unit='mg/st'
        elif fi==rpm_id and (nf,ns)==(16,10) and pressure(s) and s[0]>=700:
            name='IQ by MAP limiter';category='Smoke limitation';factor=.01;unit='mg/st'
        elif fi==rpm_id and (nf,ns)==(16,10) and iq(s) and sum(800<=v<=3500 for v in raw)>100:
            name='Boost target map';category='Turbo boost pressure';unit='mbar';xf=.01
        elif fi==rpm_id and (nf,ns)==(16,13) and iq(s):
            xf=.01
            after=b in limiters and limiters[b]<m['address']<limiters[b]+0x400
            if after and all(1500<=v<=3800 for v in raw):name='Start of injection (SOI)';category='Injection system';factor=-.023437;offset=78;unit='degrees BTDC'
            elif f[0]>=400:name='N75 duty cycle';category='Turbo boost pressure control';factor=-.01;offset=100;unit='%'
            elif all(v<=12000 for v in raw):name='EGR request';category='EGR';factor=.1;unit='mg/st'
        elif fi==rpm_id and (nf,ns)==(14,11) and temp(s):
            name='SOI limiter';category='Injection system';factor=-.023437;offset=78;xf=.1;xo=-273.1;unit='degrees BTDC'
        elif fi==rpm_id and nf in (8,9) and 8<=ns<=10 and temp(s):
            name='MAF correction by temperature' if (nf,ns)==(8,8) else 'Start IQ';factor=.01;xf=.1;xo=-273.1;unit='mg/st' if name=='Start IQ' else 'coefficient'
        elif size in (570,180,200) and fi==duration_ids.get(b) and si==rpm_id:
            name='Injector duration';category='Injection system';factor=.023437;yf=.01;unit='degrees crank angle'
        elif (nf,ns)==(10,10) and pressure(f) and si==rpm_id and all(800<=v<=3500 for v in raw):
            name='Boost limit map';category='Turbo boost pressure';unit='mbar'
        elif fi==rpm_id and (nf,ns)==(8,8) and iq(s) and all(2600<=v<=4200 for v in raw):
            name='Expected fuel temperature';factor=.1;offset=-273;xf=.01;unit='°C'
        elif fi==rpm_id and (nf,ns)==(9,8) and iq(s):
            name='Fuel volume correction';factor=.002441;xf=.01;unit='IQ correction per 100K';kind='i16'
        if name:
            m.update(name=f'{name} (early-layout candidate) @ {m["address"]:06X}',category=category,factor=factor,offset=offset,unit=unit,type=kind,confidence=.6,
                     evidence='ZedSuite early-generation shape/value classifier; modal RPM axis and bounded file orientation; candidate only.')
            m['x_axis'].update(factor=xf,offset=xo,values=[v*xf+xo for v in s])
            m['y_axis'].update(factor=yf,offset=yo,values=[v*yf+yo for v in f])
