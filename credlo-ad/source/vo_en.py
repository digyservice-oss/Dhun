import soundfile as sf, numpy as np
from kokoro_onnx import Kokoro
k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
segs = ["Give your business new wings!",
"Funding from fifty lakh, to two hundred crore.",
"A wide lending network, with service across India.",
"Contact us today. Credlo, your partner in business growth!"]
for v in ['hm_omega','am_onyx']:
  for i,t in enumerate(segs):
    s, sr = k.create(t, voice=v, speed=1.0, lang="en-us")
    a=np.abs(s); idx=np.where(a>0.01)[0]; s=s[max(idx[0]-200,0):idx[-1]+2000]
    sf.write(f"en_{v}_{i}.wav", s, sr); print(v,i, round(len(s)/sr,2))
for t in segs: print(k.tokenizer.phonemize(t, lang="en-us"))
