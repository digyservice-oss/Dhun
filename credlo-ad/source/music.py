import numpy as np, soundfile as sf, sys
SR=44100; D=15.0; N=int(SR*D); t=np.arange(N)/SR
L=np.zeros(N); R=np.zeros(N)
rng=np.random.default_rng(3)
def hz(m): return 440*2**((m-69)/12)
def add(sig,start,pan=0.0,g=1.0):
    i=int(start*SR); n=min(len(sig),N-i)
    if n<=0: return
    L[i:i+n]+=sig[:n]*g*(1-pan)/1.0 if pan>0 else sig[:n]*g
    R[i:i+n]+=sig[:n]*g*(1+pan)/1.0 if pan<0 else sig[:n]*g
def env(n,a,r):
    e=np.ones(n); ai=int(a*SR); ri=int(r*SR)
    if ai: e[:ai]=np.linspace(0,1,ai)
    if ri: e[-ri:]*=np.linspace(1,0,ri)
    return e
def saw(f,dur,harm=8):
    tt=np.arange(int(dur*SR))/SR; s=np.zeros_like(tt)
    for k in range(1,harm+1):
        if f*k>12000: break
        s+=np.sin(2*np.pi*f*k*tt+rng.random()*6)/k
    return s
# chords (MIDI) D A Bm G
CH={'D':[50,57,62,66,69],'A':[45,57,61,64,69],'Bm':[47,54,62,66,71],'G':[43,55,59,62,67]}
seq=['D','A','Bm','G','D','A','G','A']  # each 2s -> 16s
# pad
for i,c in enumerate(seq):
    st=i*2.0;
    if st>=13: break
    dur=2.15 if st<12 else 3.2
    for m in CH[c][1:]:
        for det in (-0.12,0.12):
            s=saw(hz(m+det),dur,6)*env(int(dur*SR),0.35,0.5)*0.035
            add(s,st,pan=det*3)
# final resolve chord D at 13s, held
for m in [38,50,57,62,66,69,74,78]:
    for det in (-0.1,0.1):
        s=saw(hz(m+det),2.0,7)*env(int(2.0*SR),0.02,1.6)*0.04
        add(s,13.0,pan=det*3)
# arp plucks 8th notes (0.25s)
pat=[0,2,1,3,2,4,3,1]
for k in range(int(13/0.25)):
    st=k*0.25; c=seq[int(st//2)]; notes=CH[c][1:]
    m=notes[pat[k%8]%len(notes)]+12
    dur=0.6; n=int(dur*SR); tt=np.arange(n)/SR
    s=(np.sin(2*np.pi*hz(m)*tt)+0.35*np.sin(2*np.pi*hz(m)*2*tt)+0.12*np.sin(2*np.pi*hz(m)*3*tt))*np.exp(-tt*7)
    g=0.05 if st<3 else 0.07
    add(s,st,pan=0.3 if k%2 else -0.3,g=g)
# kick from 3s
def kick():
    n=int(0.45*SR); tt=np.arange(n)/SR; f=45+80*np.exp(-tt*30); ph=2*np.pi*np.cumsum(f)/SR
    return np.sin(ph)*np.exp(-tt*7)*0.55
for b in np.arange(3.0,13.0,0.5): add(kick(),b)
# sub bass 8ths from 3s
for k in np.arange(3.0,13.0,0.25):
    c=seq[int(k//2)]; f=hz(CH[c][0]-12+12); n=int(0.24*SR); tt=np.arange(n)/SR
    add(np.sin(2*np.pi*f*tt)*env(n,0.005,0.08)*0.16,k)
# hats 16ths from 3s
def hp(x,a=0.85):
    y=np.zeros_like(x); 
    y[1:]=x[1:]-x[:-1]; return y
for k in np.arange(3.0,13.0,0.125):
    n=int(0.06*SR); s=hp(hp(rng.standard_normal(n)))*np.exp(-np.arange(n)/SR*60)*0.025
    add(s*(1.4 if (k*4)%2==1 else 1),k,pan=0.4)
# clap on 2 and 4 from 7s
for b in np.arange(7.5,13.0,1.0):
    n=int(0.25*SR); s=hp(rng.standard_normal(n))*np.exp(-np.arange(n)/SR*18)*0.12; add(s,b)
# impacts
def impact(g=1.0):
    n=int(2.5*SR); tt=np.arange(n)/SR
    boom=np.sin(2*np.pi*(38+40*np.exp(-tt*8))*tt)*np.exp(-tt*2.2)*0.7
    nz=rng.standard_normal(n); lp=np.convolve(nz,np.ones(40)/40,'same')*np.exp(-tt*4)*0.5
    return (boom+lp)*g
for st,g in [(0.0,0.9),(3.0,0.8),(7.0,0.8),(11.0,0.8),(12.85,1.0)]: add(impact(g),st)
# risers before cuts
def riser(dur):
    n=int(dur*SR); tt=np.arange(n)/SR; nz=rng.standard_normal(n)
    out=np.zeros(n); w=np.clip(np.linspace(60,4,n).astype(int),4,60)
    cs=np.cumsum(np.insert(nz,0,0))
    for i in range(0,n,512):
        k=w[i]; seg=slice(i,min(i+512,n)); idx=np.arange(seg.start,seg.stop)
        lo=np.clip(idx-k,0,n); out[seg]=(cs[idx+1]-cs[lo])/k
    sw=np.sin(2*np.pi*np.cumsum(np.linspace(200,1400,n))/SR)*0.15
    return (out*1.2+sw)*np.linspace(0,1,n)**2*0.35
for c in [3.0,7.0,11.0,12.85]: add(riser(0.9),c-0.9)
# shimmer bells at logo
for i,m in enumerate([86,90,93,98]):
    n=int(1.8*SR); tt=np.arange(n)/SR; s=np.sin(2*np.pi*hz(m)*tt)*np.exp(-tt*2.5)*0.05
    add(s,12.95+i*0.12,pan=(-0.5+i/3))
# simple stereo reverb via noise IR
def rev(x,seed):
    r=np.random.default_rng(seed); n=int(1.6*SR); ir=r.standard_normal(n)*np.exp(-np.arange(n)/SR*3.5); ir[0]=0
    F=1<<int(np.ceil(np.log2(len(x)+n))); y=np.fft.irfft(np.fft.rfft(x,F)*np.fft.rfft(ir,F),F)[:len(x)]
    return y/np.max(np.abs(ir).sum()**0.5*30)
L2=L+rev(L,1)*0.9; R2=R+rev(R,2)*0.9
out=np.stack([L2,R2],1)
fade=int(0.6*SR); out[-fade:]*=np.linspace(1,0,fade)[:,None]
out/=np.max(np.abs(out))*1.12
sf.write(sys.argv[1],out,SR)
print('ok')
