const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const ls = { get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { } } };
let cfg = {}, mode = "simple", queue = [], idx = -1, view = "create", cache = {};
let lang = ls.get("dhun_lang", "en");
const audio = $("#audio");

/* ---------------- translations (UI) ---------------- */
const T = {
  en: {
    nav_create: "Create", nav_library: "Library", nav_explore: "Explore", creates_left: "creates left today",
    simple: "Simple", custom: "Custom", desc: "Song description", desc_ph: "A dreamy lo-fi song about a rainy night in Mumbai, soft piano and slow beats…",
    lyrics: "Lyrics", starter: "✎ Starter lyrics", styles: "Styles", exclude: "Exclude styles (optional)", title: "Song title (optional)",
    instrumental: "Instrumental", songlang: "Song language", voice: "Voice", emotion: "Emotion", voice_note: "Voices and languages work with the AI engine.",
    length: "Song length", quality: "Quality", fast: "Fast", high: "High (slower)", share: "Share on Explore", create: "Create",
    latest: "Your latest songs", search_ph: "Search songs…", listen_now: "Listen Now", most_played: "Most played",
    menu: "Menu", yourname: "Your name", language: "Language", theme: "Theme", dark: "Dark", light: "Light",
    invite: "Invite friends", help: "Help", about: "About", feedback: "Feedback", terms: "Terms of service", privacy: "Privacy policy",
    close: "Close", send: "Send", remix: "Remix", mp3: "MP3", make_video: "Make video", video_btn: "Video", public: "Public", private: "Private",
    lyrics_btn: "Lyrics", creating: "Creating your song…", queued: "In queue…", failed: "Failed", auto: "Auto",
    empty_latest: "Your songs will appear here. Describe an idea and press Create ✦", empty_lib: "No songs yet.", empty_explore: "Nothing shared yet – be the first!",
    copied: "Link copied", remix_ok: "Style copied – edit and press Create", thanks: "Thanks for your feedback!", lyrics_added: "Starter lyrics added – edit freely",
    video_started: "Making your video… the MP4 button will appear when done", by: "by",
    engine_demo: "Demo engine: instrumental-only music (no AI vocals). Connect the AI engine for real songs with vocals.",
    engine_ace: "Engine: ACE-Step 1.5 (AI music with vocals).", fb_ph: "Tell us what to improve…"
  },
  hi: {
    nav_create: "बनाएँ", nav_library: "लाइब्रेरी", nav_explore: "एक्सप्लोर", creates_left: "आज के बचे हुए गाने",
    simple: "सरल", custom: "कस्टम", desc: "गाने का विवरण", desc_ph: "मुंबई की बारिश वाली रात पर एक धीमा लो-फ़ाई गाना, हल्का पियानो…",
    lyrics: "बोल", starter: "✎ शुरुआती बोल", styles: "स्टाइल", exclude: "ये स्टाइल न हों (वैकल्पिक)", title: "गाने का नाम (वैकल्पिक)",
    instrumental: "सिर्फ़ संगीत", songlang: "गाने की भाषा", voice: "आवाज़", emotion: "भाव (इमोशन)", voice_note: "आवाज़ और भाषा AI इंजन के साथ काम करती हैं।",
    length: "गाने की लंबाई", quality: "क्वालिटी", fast: "तेज़", high: "हाई (धीमा)", share: "एक्सप्लोर पर शेयर करें", create: "बनाएँ",
    latest: "आपके नए गाने", search_ph: "गाने खोजें…", listen_now: "अभी सुनें", most_played: "सबसे ज़्यादा सुने गए",
    menu: "मेन्यू", yourname: "आपका नाम", language: "भाषा", theme: "थीम", dark: "डार्क", light: "लाइट",
    invite: "दोस्तों को बुलाएँ", help: "मदद", about: "हमारे बारे में", feedback: "सुझाव", terms: "सेवा की शर्तें", privacy: "गोपनीयता नीति",
    close: "बंद करें", send: "भेजें", remix: "रीमिक्स", mp3: "MP3", make_video: "वीडियो बनाएँ", video_btn: "वीडियो", public: "सार्वजनिक", private: "निजी",
    lyrics_btn: "बोल", creating: "आपका गाना बन रहा है…", queued: "कतार में…", failed: "असफल", auto: "ऑटो",
    empty_latest: "आपके गाने यहाँ दिखेंगे। एक आइडिया लिखिए और बनाएँ दबाइए ✦", empty_lib: "अभी कोई गाना नहीं।", empty_explore: "अभी कुछ शेयर नहीं हुआ – पहले आप बनिए!",
    copied: "लिंक कॉपी हो गया", remix_ok: "स्टाइल कॉपी हो गया – बदलकर बनाएँ दबाइए", thanks: "सुझाव के लिए धन्यवाद!", lyrics_added: "शुरुआती बोल जुड़ गए – बदल सकते हैं",
    video_started: "वीडियो बन रहा है… तैयार होने पर MP4 बटन आ जाएगा", by: "द्वारा",
    engine_demo: "डेमो इंजन: सिर्फ़ संगीत (AI आवाज़ नहीं)। आवाज़ वाले असली गानों के लिए AI इंजन जोड़ें।",
    engine_ace: "इंजन: ACE-Step 1.5 (आवाज़ के साथ AI संगीत)।", fb_ph: "बताइए क्या बेहतर करें…"
  },
  bn: {
    nav_create: "তৈরি করুন", nav_library: "লাইব্রেরি", nav_explore: "এক্সপ্লোর", creates_left: "আজ বাকি",
    simple: "সহজ", custom: "কাস্টম", desc: "গানের বিবরণ", lyrics: "কথা", starter: "✎ শুরুর কথা", styles: "স্টাইল",
    exclude: "বাদ দেওয়ার স্টাইল (ঐচ্ছিক)", title: "গানের নাম (ঐচ্ছিক)", instrumental: "শুধু যন্ত্রসংগীত", songlang: "গানের ভাষা", voice: "কণ্ঠ",
    length: "গানের দৈর্ঘ্য", quality: "মান", fast: "দ্রুত", high: "উচ্চ (ধীর)", share: "এক্সপ্লোরে শেয়ার করুন", create: "তৈরি করুন",
    latest: "আপনার সাম্প্রতিক গান", search_ph: "গান খুঁজুন…", listen_now: "এখনই শুনুন", most_played: "সবচেয়ে বেশি শোনা",
    menu: "মেনু", yourname: "আপনার নাম", language: "ভাষা", theme: "থিম", dark: "ডার্ক", light: "লাইট",
    invite: "বন্ধুদের আমন্ত্রণ", help: "সাহায্য", about: "আমাদের সম্পর্কে", feedback: "মতামত", terms: "পরিষেবার শর্তাবলি", privacy: "গোপনীয়তা নীতি",
    close: "বন্ধ করুন", send: "পাঠান", remix: "রিমিক্স", make_video: "ভিডিও বানান", video_btn: "ভিডিও", public: "পাবলিক", private: "প্রাইভেট",
    lyrics_btn: "কথা", creating: "আপনার গান তৈরি হচ্ছে…", queued: "সারিতে…", failed: "ব্যর্থ", auto: "অটো", by: "লেখক"
  },
  pa: {
    nav_create: "ਬਣਾਓ", nav_library: "ਲਾਇਬ੍ਰੇਰੀ", nav_explore: "ਐਕਸਪਲੋਰ", creates_left: "ਅੱਜ ਬਾਕੀ",
    simple: "ਸੌਖਾ", custom: "ਕਸਟਮ", desc: "ਗਾਣੇ ਦਾ ਵੇਰਵਾ", lyrics: "ਬੋਲ", starter: "✎ ਸ਼ੁਰੂਆਤੀ ਬੋਲ", styles: "ਸਟਾਈਲ",
    exclude: "ਇਹ ਸਟਾਈਲ ਨਾ ਹੋਣ (ਚੋਣਵਾਂ)", title: "ਗਾਣੇ ਦਾ ਨਾਂ (ਚੋਣਵਾਂ)", instrumental: "ਸਿਰਫ਼ ਸੰਗੀਤ", songlang: "ਗਾਣੇ ਦੀ ਭਾਸ਼ਾ", voice: "ਆਵਾਜ਼",
    length: "ਗਾਣੇ ਦੀ ਲੰਬਾਈ", quality: "ਕੁਆਲਿਟੀ", fast: "ਤੇਜ਼", high: "ਹਾਈ (ਹੌਲੀ)", share: "ਐਕਸਪਲੋਰ 'ਤੇ ਸਾਂਝਾ ਕਰੋ", create: "ਬਣਾਓ",
    latest: "ਤੁਹਾਡੇ ਨਵੇਂ ਗਾਣੇ", search_ph: "ਗਾਣੇ ਲੱਭੋ…", listen_now: "ਹੁਣੇ ਸੁਣੋ", most_played: "ਸਭ ਤੋਂ ਵੱਧ ਸੁਣੇ ਗਏ",
    menu: "ਮੀਨੂ", yourname: "ਤੁਹਾਡਾ ਨਾਂ", language: "ਭਾਸ਼ਾ", theme: "ਥੀਮ", dark: "ਡਾਰਕ", light: "ਲਾਈਟ",
    invite: "ਦੋਸਤਾਂ ਨੂੰ ਬੁਲਾਓ", help: "ਮਦਦ", about: "ਸਾਡੇ ਬਾਰੇ", feedback: "ਸੁਝਾਅ", terms: "ਸੇਵਾ ਦੀਆਂ ਸ਼ਰਤਾਂ", privacy: "ਪਰਦੇਦਾਰੀ ਨੀਤੀ",
    close: "ਬੰਦ ਕਰੋ", send: "ਭੇਜੋ", remix: "ਰੀਮਿਕਸ", make_video: "ਵੀਡੀਓ ਬਣਾਓ", video_btn: "ਵੀਡੀਓ", public: "ਪਬਲਿਕ", private: "ਪ੍ਰਾਈਵੇਟ",
    lyrics_btn: "ਬੋਲ", creating: "ਤੁਹਾਡਾ ਗਾਣਾ ਬਣ ਰਿਹਾ ਹੈ…", queued: "ਕਤਾਰ ਵਿੱਚ…", failed: "ਅਸਫਲ", auto: "ਆਟੋ", by: "ਵੱਲੋਂ"
  },
  mr: {
    nav_create: "तयार करा", nav_library: "लायब्ररी", nav_explore: "एक्सप्लोर", creates_left: "आज शिल्लक",
    simple: "सोपे", custom: "कस्टम", desc: "गाण्याचे वर्णन", lyrics: "बोल", starter: "✎ सुरुवातीचे बोल", styles: "स्टाइल",
    exclude: "हे स्टाइल नको (ऐच्छिक)", title: "गाण्याचे नाव (ऐच्छिक)", instrumental: "फक्त संगीत", songlang: "गाण्याची भाषा", voice: "आवाज",
    length: "गाण्याची लांबी", quality: "दर्जा", fast: "जलद", high: "उच्च (हळू)", share: "एक्सप्लोरवर शेअर करा", create: "तयार करा",
    latest: "तुमची नवीन गाणी", search_ph: "गाणी शोधा…", listen_now: "आता ऐका", most_played: "सर्वाधिक ऐकलेली",
    menu: "मेनू", yourname: "तुमचे नाव", language: "भाषा", theme: "थीम", dark: "डार्क", light: "लाइट",
    invite: "मित्रांना आमंत्रित करा", help: "मदत", about: "आमच्याबद्दल", feedback: "अभिप्राय", terms: "सेवेच्या अटी", privacy: "गोपनीयता धोरण",
    close: "बंद करा", send: "पाठवा", remix: "रीमिक्स", make_video: "व्हिडिओ बनवा", video_btn: "व्हिडिओ", public: "सार्वजनिक", private: "खाजगी",
    lyrics_btn: "बोल", creating: "तुमचे गाणे तयार होत आहे…", queued: "रांगेत…", failed: "अयशस्वी", auto: "ऑटो", by: "द्वारे"
  }
};
const tr = k => (T[lang] && T[lang][k]) || T.en[k] || k;

/* page texts (English + Hindi; other languages fall back to English) */
const PAGES = {
  help: {
    en: ["1. Pick Simple or Custom.", "2. Write an idea or your lyrics. Choose style, song language, voice and length (up to 10 minutes).", "3. Press Create and wait for your song.", "4. Play it, download the MP3, or make an MP4 video.", "Note: this is free hosting, so songs can disappear when the server restarts. Download what you like."],
    hi: ["1. सरल या कस्टम चुनिए।", "2. आइडिया या अपने बोल लिखिए। स्टाइल, गाने की भाषा, आवाज़ और लंबाई (10 मिनट तक) चुनिए।", "3. बनाएँ दबाइए और गाना बनने का इंतज़ार कीजिए।", "4. गाना सुनिए, MP3 डाउनलोड कीजिए या MP4 वीडियो बनाइए।", "ध्यान दें: यह फ्री होस्टिंग है, सर्वर रीस्टार्ट होने पर गाने मिट सकते हैं। जो पसंद आए उसे डाउनलोड कर लीजिए।"]
  },
  about: {
    en: ["Dhun is a free, experimental AI music maker for songs in Hindi, English, Bangla, Punjabi and Marathi.", "Voices such as Adil, Rohan, Meera and Sana are Dhun's own style presets. They are not copies of real people or of voices from other apps."],
    hi: ["Dhun हिंदी, इंग्लिश, बांग्ला, पंजाबी और मराठी में गाने बनाने वाला एक फ्री, प्रायोगिक AI म्यूज़िक मेकर है।", "Adil, Rohan, Meera और Sana जैसी आवाज़ें Dhun के अपने स्टाइल प्रीसेट हैं। ये किसी असली इंसान या दूसरे ऐप की आवाज़ की कॉपी नहीं हैं।"]
  },
  terms: {
    en: ["Dhun is provided free and as is, without guarantees. Songs may be deleted at any time.", "You are responsible for what you create and share. Do not imitate or clone a real person's voice without their permission.", "Songs you mark Public can be heard and remixed by everyone."],
    hi: ["Dhun फ्री और जैसा है वैसा उपलब्ध है, किसी गारंटी के बिना। गाने कभी भी हट सकते हैं।", "आप जो बनाते और शेयर करते हैं उसकी ज़िम्मेदारी आपकी है। किसी असली इंसान की आवाज़ उसकी इजाज़त के बिना नक़ल या क्लोन न करें।", "जिन गानों को आप सार्वजनिक रखते हैं उन्हें सब सुन और रीमिक्स कर सकते हैं।"]
  },
  privacy: {
    en: ["We use a random ID cookie in your browser to keep your songs. We do not ask for your email or password.", "We store your songs, your optional display name and any feedback you send.", "Public songs are visible to everyone."],
    hi: ["आपके गाने सुरक्षित रखने के लिए हम ब्राउज़र में एक रैंडम ID कुकी इस्तेमाल करते हैं। हम ईमेल या पासवर्ड नहीं माँगते।", "हम आपके गाने, वैकल्पिक नाम और भेजा गया सुझाव सहेजते हैं।", "सार्वजनिक गाने सबको दिखते हैं।"]
  }
};

function applyLang() {
  document.documentElement.lang = lang;
  $$("[data-i18n]").forEach(e => { e.textContent = tr(e.dataset.i18n); });
  $$("[data-i18n-ph]").forEach(e => { e.placeholder = tr(e.dataset.i18nPh); });
  $$("#uiLangs span").forEach(s => s.classList.toggle("sel", s.dataset.lang === lang));
  $("#engineNote").textContent = (cfg.engine === "ace" || cfg.engine === "modal" || cfg.engine === "hf") ? tr("engine_ace") : tr("engine_demo");
  buildSelects(); credits(); redraw();
}

/* ---------------- helpers ---------------- */
const fmt = s => { s = Math.floor(s || 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const esc = s => (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = async (u, o = {}) => {
  const r = await fetch(u, { headers: { "Content-Type": "application/json" }, ...o });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Something went wrong");
  return j;
};
function toast(t) { const e = $("#toast"); e.textContent = t; e.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => e.hidden = true, 2600); }
const compact = n => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "K" : String(n || 0);

/* ---------------- nav ---------------- */
$$("[data-view]").forEach(a => a.onclick = () => show(a.dataset.view));
function show(v) {
  view = v;
  $$("[data-view]").forEach(a => a.classList.toggle("active", a.dataset.view === v));
  $$(".view").forEach(s => s.classList.toggle("active", s.id === "v-" + v));
  window.scrollTo(0, 0);
  refresh();
}

/* ---------------- form ---------------- */
function setMode(m) {
  mode = m;
  $$("#modeTabs button").forEach(x => x.classList.toggle("on", x.dataset.mode === m));
  $("#simpleBox").hidden = m !== "simple";
  $("#customBox").hidden = m !== "custom";
  $("#jsonBox").hidden = m !== "json";
  $$("#v-create .form > .toggle, #v-create .form > .adv, #btnCreate").forEach(e => e.style.display = m === "json" ? "none" : "");
}
$$("#modeTabs button").forEach(b => b.onclick = () => setMode(b.dataset.mode));
const STYLES = ["pop", "lo-fi", "bollywood", "indian classical", "rock", "edm", "hip hop", "acoustic", "ambient", "cinematic", "romantic", "punjabi", "ghazal", "sad", "upbeat"];
$("#styleChips").innerHTML = STYLES.map(s => `<span>${s}</span>`).join("");
$("#styleChips").onclick = e => {
  if (e.target.tagName !== "SPAN") return;
  const el = $("#styles"), cur = el.value.split(",").map(x => x.trim()).filter(Boolean);
  if (!cur.includes(e.target.textContent)) cur.push(e.target.textContent);
  el.value = cur.join(", ");
};
$("#duration").oninput = e => $("#durLbl").textContent = fmt(e.target.value);
function syncInstr() { const on = $("#instrumental").checked; $("#lyrics").disabled = on; $("#lyrics").style.opacity = on ? .4 : 1; }
$("#instrumental").onchange = syncInstr;

const NATIVE = { hi: "हिन्दी", en: "English", bn: "বাংলা", pa: "ਪੰਜਾਬੀ", mr: "मराठी" };
let voiceData = { voices: [{ id: "auto", name: "Auto", gender: "" }], emotions: [{ id: "auto", name: "Auto" }], languages: [] };
function buildSelects() {
  const sl = $("#songLang"), sv = $("#voice"), curL = sl.value, curV = sv.value;
  sl.innerHTML = `<option value="">${tr("auto")}</option>` + voiceData.languages.map(l => `<option value="${l.id}">${NATIVE[l.id] || l.name}</option>`).join("");
  sv.innerHTML = voiceData.voices.map(v => `<option value="${v.id}">${v.id === "auto" ? tr("auto") : v.name + (v.gender === "male" ? " ♂" : v.gender === "female" ? " ♀" : "")}</option>`).join("");
  sl.value = curL; if (curV) sv.value = curV;
  const se = $("#emotion"), curE = se.value;
  se.innerHTML = (voiceData.emotions || [{ id: "auto", name: "Auto" }]).map(m => `<option value="${m.id}">${m.id === "auto" ? tr("auto") : m.name}</option>`).join("");
  if (curE) se.value = curE;
}

$("#btnLyrics").onclick = () => {
  const idea = ($("#prompt").value || $("#title").value || $("#styles").value || "zindagi").trim().split(/\s+/).slice(0, 4).join(" ");
  $("#lyrics").value =
`[Verse 1]
Raat ke andhere mein, ${idea}
Dil ki dhadkan keh rahi hai, ek nayi kahani
Khamosh si hawa mein, teri yaad aati hai
Har pal bas tujhe hi, ye zindagi bulati hai

[Chorus]
Oh ${idea}, tu hi meri dhun hai
Har saans mein basa hai, tera hi toh sun hai
Chal chalein door kahin, jahan ho sirf hum tum
${idea}, ${idea}, gunj uthe ye gagan

[Verse 2]
Subah ki pehli kiran, jab chhoo le ye zameen
Lagta hai sapne mere, ho gaye hain haseen
Kadam kadam par tera, saath hai bas yahi
Mushkilein jo aayein, ab koi darr nahi

[Chorus]
Oh ${idea}, tu hi meri dhun hai
Har saans mein basa hai, tera hi toh sun hai

[Outro]
${idea}…`;
  toast(tr("lyrics_added"));
};

$("#btnCreate").onclick = async () => {
  const btn = $("#btnCreate"); $("#err").textContent = "";
  const custom = mode === "custom";
  const body = {
    prompt: $("#prompt").value,
    lyrics: custom ? $("#lyrics").value : "",
    styles: custom ? $("#styles").value : "",
    exclude: custom ? $("#exclude").value : "",
    title: custom ? $("#title").value : "",
    instrumental: $("#instrumental").checked,
    language: $("#songLang").value, voice: $("#voice").value, emotion: $("#emotion").value, creator: $("#myName").value,
    duration: +$("#duration").value, quality: $("#quality").value, public: $("#public").checked,
  };
  btn.disabled = true;
  try { const r = await api("/api/generate", { method: "POST", body: JSON.stringify(body) }); cfg.daily_left = r.daily_left; credits(); await refresh(); }
  catch (e) { $("#err").textContent = e.message; }
  btn.disabled = false;
};

function credits() {
  $(".credits").hidden = !cfg.daily_limit;
  if (!cfg.daily_limit) return;
  $("#creditsTxt").textContent = `${cfg.daily_left} / ${cfg.daily_limit}`;
  $("#creditsBar").style.width = (cfg.daily_left / cfg.daily_limit * 100) + "%";
}

/* ---------------- lists ---------------- */
function card(s) {
  const ready = s.status === "ready";
  const st = s.status === "failed" ? `<small style="color:#ff7a7a">${tr("failed")}: ${esc(s.error)}</small>`
    : !ready ? `<small><span class="spin"></span>${s.status === "running" ? tr("creating") : tr("queued")}</small>`
    : `<small>${esc(s.styles || s.prompt)}${s.mine ? "" : " · " + tr("by") + " " + esc(s.creator)}</small>`;
  let vid = "";
  if (ready && s.mine) {
    vid = s.video === "ready" ? `<button data-a="watch">▶ ${tr("video_btn")}</button><a href="/download/${s.id}.mp4">⬇ MP4</a>`
      : s.video === "pending" ? `<button disabled><span class="spin"></span>…</button>`
      : `<button data-a="video">🎬 ${tr("make_video")}</button>`;
  }
  const tags = (s.language ? `<span class="tag lang">${NATIVE[s.language] || s.language}</span>` : "") + (s.voice && s.voice !== "auto" ? `<span class="tag">${esc(s.voice.replace(/^auto:/, "").replace(":", " · "))}</span>` : "");
  return `<div class="song ${queue[idx] && queue[idx].id === s.id ? "playing" : ""}" data-id="${s.id}">
    <div class="cv" data-a="play">${ready ? `<img src="/media/${s.id}/cover.jpg" loading="lazy">` : ""}${ready ? '<div class="pl">▶</div>' : ""}</div>
    <div class="meta"><b>${esc(s.title)}${ready ? `<span class="tag">${fmt(s.duration)}</span>` : ""}${s.instrumental ? '<span class="tag">♪</span>' : ""}${tags}</b>${st}</div>
    ${ready ? `<div class="acts">
      <button data-a="like" class="${s.liked ? "liked" : ""}">${s.liked ? "♥" : "♡"} ${s.likes || ""}</button>
      <button data-a="remix">⟲ ${tr("remix")}</button>
      ${s.lyrics ? `<button data-a="lyrics">${tr("lyrics_btn")}</button>` : ""}
      <a href="/download/${s.id}.mp3">⬇ MP3</a>${vid}
      ${s.mine ? `<button data-a="vis">${s.public ? tr("public") : tr("private")}</button><button data-a="del">🗑</button>` : ""}
    </div>` : ""}
  </div>`;
}
function ccard(s) {
  return `<div class="ccard" data-id="${s.id}">
    <div class="cv2" data-a="play"><img src="/media/${s.id}/cover.jpg" loading="lazy"><div class="pl">▶</div></div>
    <b>${esc(s.title)}</b><small>${esc(s.creator)} · ${fmt(s.duration)}</small>
    <div class="stats">▶ ${compact(s.plays)} · ♥ ${compact(s.likes)}</div>
    <div class="ra"><button data-a="remix">⟲ ${tr("remix")}</button></div>
  </div>`;
}
const draw = (el, list, empty, fn = card) => { cache[el] = list; $(el).innerHTML = list.length ? list.map(fn).join("") : `<div class="empty">${empty}</div>`; };
const EMPTY = { "#latest": "empty_latest", "#library": "empty_lib", "#exLatest": "empty_explore", "#exTop": "empty_explore" };
function redraw() {
  Object.keys(cache).forEach(k => draw(k, cache[k], tr(EMPTY[k]), k.startsWith("#ex") ? ccard : card));
}

async function refresh() {
  try {
    if (view === "create") draw("#latest", (await api("/api/songs")).slice(0, 12), tr("empty_latest"));
    if (view === "library") draw("#library", await api("/api/songs?q=" + encodeURIComponent($("#search").value)), tr("empty_lib"));
    if (view === "explore") {
      draw("#exLatest", await api("/api/explore"), tr("empty_explore"), ccard);
      draw("#exTop", await api("/api/explore?sort=top"), tr("empty_explore"), ccard);
    }
  } catch (e) { }
}
setInterval(() => {
  const busy = Object.values(cache).flat().some(s => s.status === "pending" || s.status === "running" || s.video === "pending");
  if (busy) refresh();
}, 3000);
$("#search").oninput = () => refresh();

function remix(s) {
  setMode("custom");
  $("#lyrics").value = s.lyrics || ""; $("#styles").value = s.styles || s.prompt || ""; $("#title").value = "";
  $("#exclude").value = ""; $("#instrumental").checked = !!s.instrumental; syncInstr();
  $("#songLang").value = s.language || ""; { const [vv, ee] = (s.voice || "auto").split(":"); $("#voice").value = vv || "auto"; $("#emotion").value = ee || "auto"; }
  show("create"); toast(tr("remix_ok"));
}

document.addEventListener("click", async e => {
  const t = e.target.closest("[data-a]"); if (!t) return;
  const row = t.closest(".song, .ccard"); if (!row) return;
  const id = row.dataset.id, list = Object.values(cache).flat().find(s => s.id === id), a = t.dataset.a;
  if (!list) return;
  if (a === "play") { const l = cache["#" + row.parentElement.id] || [list]; play(l.filter(x => x.status === "ready"), id); }
  if (a === "remix") remix(list);
  if (a === "like") { await api(`/api/songs/${id}/like`, { method: "POST" }); refresh(); }
  if (a === "del") { if (confirm("Delete?")) { await api(`/api/songs/${id}`, { method: "DELETE" }); refresh(); } }
  if (a === "vis") { await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ public: !list.public }) }); refresh(); }
  if (a === "lyrics") { $("#lyTitle").textContent = list.title; $("#lyBody").textContent = list.lyrics; $("#lyricModal").hidden = false; }
  if (a === "video") { try { await api(`/api/songs/${id}/video`, { method: "POST" }); toast(tr("video_started")); refresh(); } catch (er) { toast(er.message); } }
  if (a === "watch") { $("#vidEl").src = `/media/${id}/video.mp4`; $("#vidModal").hidden = false; $("#vidEl").play(); audio.pause(); }
});
$("#vidClose").onclick = () => { $("#vidEl").pause(); $("#vidModal").hidden = true; };

/* ---------------- player ---------------- */
function play(list, id) { queue = list; idx = Math.max(0, list.findIndex(s => s.id === id)); load(); }
function load() {
  const s = queue[idx]; if (!s) return;
  audio.src = `/media/${s.id}/audio.mp3`; audio.play();
  api(`/api/songs/${s.id}/play`, { method: "POST" }).catch(() => { });
  $("#player").hidden = false; $("#pCover").src = `/media/${s.id}/cover.jpg`;
  $("#pTitle").textContent = s.title; $("#pStyles").textContent = s.styles || s.prompt || "";
  $$(".song").forEach(r => r.classList.toggle("playing", r.dataset.id === s.id));
}
$("#pPlay").onclick = () => audio.paused ? audio.play() : audio.pause();
$("#pNext").onclick = () => { if (queue.length) { idx = (idx + 1) % queue.length; load(); } };
$("#pPrev").onclick = () => { if (queue.length) { idx = (idx - 1 + queue.length) % queue.length; load(); } };
audio.onplay = () => $("#pPlay").textContent = "❚❚";
audio.onpause = () => $("#pPlay").textContent = "▶";
audio.onended = () => $("#pNext").click();
audio.ontimeupdate = () => { if (audio.duration) { $("#pSeek").value = audio.currentTime / audio.duration * 1000; $("#pCur").textContent = fmt(audio.currentTime); $("#pDur").textContent = fmt(audio.duration); } };
$("#pSeek").oninput = e => { if (audio.duration) audio.currentTime = e.target.value / 1000 * audio.duration; };
$("#pVol").oninput = e => audio.volume = e.target.value / 100; audio.volume = .8;

/* ---------------- menu drawer ---------------- */
const drawer = $("#drawer"), overlay = $("#overlay");
const openDrawer = o => { drawer.hidden = !o; overlay.hidden = !o; };
$("#menuBtn").onclick = () => openDrawer(true);
$("#drawerClose").onclick = overlay.onclick = () => openDrawer(false);
$("#uiLangs").innerHTML = Object.keys(NATIVE).map(k => `<span data-lang="${k}">${NATIVE[k]}</span>`).join("");
$("#uiLangs").onclick = e => { const l = e.target.dataset.lang; if (!l) return; lang = l; ls.set("dhun_lang", l); applyLang(); };
function applyTheme(t) { document.documentElement.dataset.theme = t; $$("#themes span").forEach(s => s.classList.toggle("sel", s.dataset.theme === t)); }
$("#themes").onclick = e => { const t = e.target.dataset.theme; if (!t) return; ls.set("dhun_theme", t); applyTheme(t); };
$("#myName").value = ls.get("dhun_name", "");
$("#myName").oninput = e => ls.set("dhun_name", e.target.value);

function openPage(key) {
  $("#pgTitle").textContent = tr(key);
  const body = $("#pgBody");
  if (key === "feedback") {
    body.innerHTML = `<textarea id="fbText" maxlength="1000" placeholder="${esc(tr("fb_ph"))}"></textarea><button class="primary" id="fbSend">${tr("send")}</button>`;
    $("#fbSend").onclick = async () => {
      const text = $("#fbText").value.trim(); if (!text) return;
      try { await api("/api/feedback", { method: "POST", body: JSON.stringify({ text }) }); toast(tr("thanks")); $("#pageModal").hidden = true; } catch (er) { toast(er.message); }
    };
  } else {
    const src = PAGES[key]; const lines = src[lang] || src.en;
    body.innerHTML = lines.map(l => `<p>${esc(l)}</p>`).join("");
  }
  $("#pageModal").hidden = false;
}
$(".menulist").onclick = async e => {
  const key = e.target.dataset.page; if (!key) return;
  if (key === "invite") {
    const url = location.origin;
    try { if (navigator.share) { await navigator.share({ title: "Dhun", text: "Dhun – AI music", url }); return; } } catch (er) { return; }
    try { await navigator.clipboard.writeText(url); toast(tr("copied")); } catch (er) { toast(url); }
    return;
  }
  openDrawer(false); openPage(key);
};
$("#pgClose").onclick = () => $("#pageModal").hidden = true;

/* ---------------- boot ---------------- */
(async () => {
  applyTheme(ls.get("dhun_theme", "dark"));
  try { cfg = await api("/api/config"); } catch (e) { cfg = {}; }
  try { voiceData = await api("/api/voices"); } catch (e) { }
  if (cfg.max_duration) $("#duration").max = cfg.max_duration;
  applyLang(); refresh();
})();
