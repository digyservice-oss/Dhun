/* JSON import and script -> voice-over */
const SAMPLE = { type: "voiceover", title: "Mera Ad", language: "hi", music: { style: "soft cinematic", volume: 0.25 },
  segments: [{ text: "नमस्ते, आपका स्वागत है।", pause: 0.6 }, { text: "आज ही हमसे जुड़िए।" }] };
$("#jsonIn").value = JSON.stringify(SAMPLE, null, 2);
$("#jsonFile").onchange = async e => { const f = e.target.files[0]; if (f) $("#jsonIn").value = await f.text(); };
async function submitSpec(spec) {
  $("#jsonErr").textContent = "";
  try {
    // {"type":"song", ...} or a list of items; "voiceover" goes to the voice-over maker
    for (const item of Array.isArray(spec) ? spec : [spec]) {
      const url = item.type === "voiceover" ? "/api/voiceover" : "/api/generate";
      await api(url, { method: "POST", body: JSON.stringify(item) });
    }
    await refresh();
  } catch (e) { $("#jsonErr").textContent = e.message; }
}
$("#jsonRun").onclick = () => {
  let spec;
  try { spec = JSON.parse($("#jsonIn").value); } catch (e) { $("#jsonErr").textContent = "JSON galat hai: " + e.message; return; }
  submitSpec(spec);
};
$("#voMake").onclick = () => submitSpec({ type: "voiceover", language: $("#songLang").value || "hi",
  script: $("#voScript").value, music: { style: $("#voStyle").value } });
