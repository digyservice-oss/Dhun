import soundfile as sf, numpy as np
from kokoro_onnx import Kokoro
k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
segs = ["बिज़नेस को दें नई उड़ान!",
"पचास लाख से दो सौ करोड़ तक की फंडिंग,",
"वाइड लेंडिंग नेटवर्क, और पूरे भारत में सर्विस।",
"आज ही संपर्क करें — क्रेडलो, आपके ग्रोथ का साथी!"]
for v in ['hm_omega','hm_psi']:
  for i,t in enumerate(segs):
    s, sr = k.create(t, voice=v, speed=1.0, lang="hi")
    # trim silence
    a=np.abs(s); idx=np.where(a>0.01)[0]; s=s[max(idx[0]-200,0):idx[-1]+2000]
    sf.write(f"seg_{v}_{i}.wav", s, sr); print(v,i, round(len(s)/sr,2))
print(k.tokenizer.phonemize(segs[3], lang="hi") if hasattr(k,'tokenizer') else '')
