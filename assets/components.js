/* Ortak ders bileşenleri (assets/components.js). Her ders, tekrar ve referans sayfası bunu yükler.
 *
 * 1) Quiz kartı — çoktan seçmeli soru (LH soru kartı görünümü):
 *    <div class="quiz" data-card="pts-010" data-answer="1" [data-label="Tahmin"]>
 *      <p class="q">Soru?</p>
 *      <div class="opts">
 *        <button class="opt" data-why="Neden yanlış/doğru">Seçenek</button> ...
 *      </div>
 *      <div class="feedback"></div>
 *    </div>
 *    data-card: cards.jsonl kimliği; data-answer: doğru şıkkın 0'dan başlayan sırası;
 *    data-label: kartın üstündeki mono etiket (varsayılan "Soru"; ör. "Tahmin"). Şık sırası
 *    cards.jsonl'daki (script'in karıştırdığı) sıradır; elle sıralama yapma.
 *
 *    data-card'lı kart (yeni dersler): JS her kartın altına kesikli "Bilmiyorum" satırı, 3 düzeyli
 *    eminlik seçici (Tahmin=1, Emin değilim=2, Eminim=3), isteğe bağlı tek satırlık "Neden?" alanı
 *    ve "Cevapla" düğmesi ekler. Şık seçmek cevaplamak değildir; "Cevapla" (ya da Neden? alanında
 *    Enter) kilitler ve doğru/yanlış geri bildirimini gösterir. Bilmiyorum seçilince eminlik 1 olur.
 *    data-card'sız kart (eski dersler 0001–0002): eski davranış — şıkka tıklamak hemen cevaplar;
 *    sonuç bloğuna girmez.
 *
 * 2) Açık cevap kutusu — <div class="write" data-card="gt-020" [data-label="Yaz"]><p class="q">Soru</p></div>
 *    Açık uçlu (recall/explain) kartlar için; `tools/learn cards --html` ve `due --html` bunu üretir. JS
 *    büyüyen bir textarea ("Kendi cümlelerinle… (bakmadan)"), quiz'le aynı eminlik seçiciyi ve "Kaydet"
 *    düğmesini ekler. Kaydet kutuyu kilitler ("Düzenle" bağlantısı geri açar). Model cevap sayfada DURMAZ;
 *    öğretmen sohbette puanlar (motor yaz: satırını inbox'a yazar). Taslak ve eminlik localStorage'da
 *    kalır: anahtar `teach-write:<sayfa kimliği>:<kart>` (sayfa kimliği = main[data-lesson] ya da
 *    main[data-review] değeri). Kaydedilen kutu sonuç çubuğunda bir "öğe" sayılır.
 *
 * 3) Soru kutusu — <div class="ask-box"></div> (sayfada en fazla bir tane; isteğe bağlı <p class="q">)
 *    "Anlamadığım / sormak istediğim" textarea'sı. localStorage `teach-ask:<dosya adı>` (ör. 0002-goz-goze,
 *    review-2026-11-05). Boş olmayan her satır blokta bir `soru:` satırı olur. Puanlanmaz, öğe sayılmaz;
 *    yalnız soru yazılmış bir sayfada da sonuç çubuğu (Kopyala) çıkar.
 *
 * 4) Süre — <div class="timer" data-card="gt-030" data-seconds="60"></div> (mülakat tipi sorular; isteğe bağlı)
 *    Başlat/Durdur düğmesi ve geri sayım. Durdurulunca ya da süre bitince geçen saniye o kart için
 *    kaydedilir (`süre:` satırı; localStorage `teach-timer:<sayfa kimliği>:<kart>`). "Yeniden" üstüne yazar.
 *
 * 5) SONUÇ BLOĞU (v3) — docs/plan-yontem-guncelleme.md "Veri biçimleri" §1 ile birebir. İlk data-card'lı
 *    cevaptan (quiz ya da kaydedilmiş yazı) sonra alttan yapışkan .result-bar çıkar: "4 öğeden 2'si
 *    cevaplandı · kopyala, sohbete yapıştır" + tek Kopyala düğmesi (o anki bloğu kopyalar). Bütün öğeler
 *    bitince aynı blok sayfadaki <div class="score"></div> içinde <pre> olarak da görünür. Puan hiçbir
 *    yerde gösterilmez. Blok:
 *
 *      ders sonucu 0003 v3                       ← main[data-lesson]; tekrar sayfasında "tekrar sonucu 2026-11-05 v3"
 *      mcq: gt-012=B/3 "çünkü ikisi de sapmak ister"; gt-013=?/1; gt-014=A/2
 *      yaz: gt-020/2 | Nash dengesi, kimsenin tek başına sapmak istemediği durum ⏎ ikinci satır
 *      soru: Peki iki denge varsa hangisi seçilir?
 *      süre: gt-030=58s
 *
 *    mcq: öğeler "; " ile; KART=SEÇİM/EMİNLİK ["neden"]; SEÇİM A–H ya da ? (Bilmiyorum); neden tek satır,
 *    içindeki " → '. yaz: kaydedilmiş her kutu için bir satır: KART/EMİNLİK | metin; satır sonu " ⏎ ",
 *    metindeki | → /. Boş kutu satır üretmez. soru: .ask-box'ın her dolu satırı. süre: KART=saniye s, "; " ile.
 *    Olmayan satır yazılmaz; sıra sabit değil. window.teachLesson.buildResult() o anki bloğu döndürür;
 *    teachLesson.parseResult(metin) v3 bloğu VE eski biçimleri okur:
 *      ESKİ (tek satır, 0003 dönemi):  ders sonucu 0003: gt-012=B/3 "neden"; gt-013=?/1   (format: "new")
 *      EN ESKİ (0001–0002 dönemi):     ders sonucu 0002: pts-010=B pts-015=C             (format: "old")
 *    Öğretmen bloğu `tools/learn record-lesson` ile tek seferde kaydeder (lesson SKILL.md).
 *
 * 6) Tekrar sayfası — `tools/learn due --html` → learner/reviews/review-YYYY-MM-DD.html,
 *    <main data-review="YYYY-MM-DD">, assets ../../assets/. Üst çubuk (.lesson-bar) yoktur; burada hiçbir
 *    şey ../../../ varsaymaz (ikon ve logo <script src>'den türetilir). Blok başlığı "tekrar sonucu … v3".
 *
 * 7) Ödeme matrisi — <div class="payoff-game" data-game='{...}'></div>
 *    {
 *      "rows": {"player": "Britanya", "s": ["Sınırla", "İnşa et"]},
 *      "cols": {"player": "Almanya",  "s": ["Sınırla", "İnşa et"]},
 *      "pay":  [[[3,3],[1,4]], [[4,1],[2,2]]],   // pay[satır][sütun] = [satır oyuncusu, sütun oyuncusu]
 *      "mode": "static" | "nash",                  // nash: kullanıcı dengeleri işaretler ve kontrol eder
 *      "caption": "..."
 *    }
 *
 * 8) Doğruluk tablosu — <div class="truth-table" data-tt='{...}'></div>
 *    {
 *      "vars": ["P", "Q"],                         // satırlar: bütün kombinasyonlar, önce D
 *      "given": ["P ⇒ Q"],                         // hazır gösterilen sütunlar (isteğe bağlı)
 *      "cols": ["¬Q", "¬P", "¬Q ⇒ ¬P"],            // öğrencinin dolduracağı sütunlar
 *      "labels": ["D", "Y"],                       // doğru/yanlış etiketleri (varsayılan D/Y)
 *      "caption": "..."
 *    }
 *    İfadeler: değişkenler büyük harf; ¬ (ya da !, ~), ∧ (&, and), ∨ (|, or), ⇒ (->), ⇔ (<->), parantez.
 *    Öncelik: ¬ > ∧ > ∨ > ⇒ > ⇔; ⇒ sağdan bağlar. Hücreye tıkla: boş → D → Y → boş.
 *
 * 9) Diyagram — elle yazılmış <svg class="diagram"> (biçim style.css'te "Diyagram" başlığında).
 *    Bu dosya ok başlarını (#dg-arrow, #dg-arrow-dim) sayfaya bir kez ekler.
 *
 * 9b) Konum görseli — "neredeyiz / hangi yöne" küçük SVG; ders ve Harita sayfalarında, hedef kartının altında:
 *    <div class="position-slot" data-style="path|pyramid|ring" data-pos='{"track":"t","done":6,"total":15,
 *      "learning":2,"current":"negation","path":["negation","direct-proof","…"],"labels":{"negation":"Olumsuzlama"}}'></div>
 *    data-pos'u `tools/learn refresh` export.json'dan doldurur (lmap SVG'si gibi); boşsa hiçbir şey çizilmez.
 *    path (varsayılan): yatay adımlayıcı — path id'leri soldan sağa kutular ve oklar, şimdiki kalın çerçeveli, hedef
 *    en sağda; altında ince çizgi "6 / 15 düğüm". pyramid: katlar alttan yukarı (temel altta, hedef tepede): biten
 *    gri dolu, şimdiki çerçeveli, gelecek soluk. ring: biten/toplam halkası, ortada şimdiki etiket, altında "→ sonraki".
 *    Diyagramın node/edge sınıflarını (visited/current/dim) ve tokenları kullanır; yüzde ya da başka sayı yok.
 *    data-style ders ders değiştirilebilir.
 *
 * 10) Matematik (isteğe bağlı) — ders <head>'inde assets/vendor/katex dosyaları yüklüyse \( … \),
 *    \[ … \] ve $$ … $$ işlenir (geri bildirim metinleri dahil). Yüklü değilse metin olduğu gibi kalır.
 *
 * 11) Ders modu (tools/lesson-template.html'deki iskelet; hepsi isteğe bağlı, yoksa sessizce atlanır):
 *    - Tema: ?theme=light|dark ya da localStorage "teach-theme" (panoyla aynı anahtar) <html data-theme>'i
 *      sayfa çizilmeden ayarlar; .theme-btn tıklanınca açık/koyu değişir (window.teachToggleTheme).
 *    - Adımlar: <section class="step" [data-title="Kısa ad"]><h2>…</h2> … </section>. JS her h2'nin üstüne
 *      "ADIM i" yazar, .lesson-bar .lb-step çipini "ADIM 3 · Başlık" olarak kaydırdıkça günceller
 *      (IntersectionObserver), .lb-progress i çizgisini kaydırma oranına göre doldurur ve [data-step-count]
 *      / [data-check-count] öğelerine sayıları yazar (kontrol = data-card'lı quiz + write); hedef kartında
 *      bu sayılar gizlenir (çip tekrarı). Çubuk yoksa (tekrar sayfası) hepsi sessizce atlanır.
 *    - Harita yuvası: <div class="lmap-slot" data-track data-nodes="a,b" data-current="a"> içine
 *      `tools/learn lesson-map` çıktısı (<svg class="lmap">) yapıştırılır. SVG yoksa JS düğümleri sade
 *      çiplerle gösterir. SVG'yi `tools/learn refresh` doldurur (sarı yalnızca konunun sıradaki düğümü).
 *    - Sonuç çubuğu: bkz. 5.
 *
 * 12) Panoya gömülü: pano dersi iframe'de "?embed=1&theme=…" ile açar. Ders bunu (ya da iframe içinde olduğunu)
 *    görünce <html class="embed"> olur: üst çubukta yalnız adım çipi ve ilerleme çizgisi kalır; tema panoyu
 *    izler; başka derse / referansa giden bağlantıları pano kendi sekmesinde / yan panelinde açar.
 *    Tek başına açılan ders eskisi gibi çalışır. Derslerde ayrıca bir şey yapmak gerekmez.
 *
 * Dikkat: data-* JSON'ları tek tırnakla yazılır; metindeki kesme işaretini &#39; olarak yaz ("Britanya&#39;nın").
 * localStorage'a her erişim try/catch içindedir (gizli pencere, file:// kısıtı): depo yoksa sayfa yine çalışır.
 */
(function () {
  "use strict";
  var LETTERS = "ABCDEFGH";
  var CONF = [null, "Tahmin", "Emin değilim", "Eminim"]; // 1 / 2 / 3 → tools/learn --confidence

  // ---------- Sonuç bloğu (saf işlevler; node ile test edilebilir) ----------
  function cleanWhy(t) {
    return String(t || "").replace(/\s+/g, " ").replace(/"/g, "'").trim().slice(0, 240);
  }
  // yaz:/soru: metni tek satıra: satır sonu " ⏎ ", | → /, boş satırlar atılır.
  function cleanText(t) {
    return String(t || "").replace(/\r\n?/g, "\n").split("\n")
      .map(function (l) { return l.replace(/[ \t]+/g, " ").trim(); }).filter(Boolean)
      .join(" ⏎ ").replace(/\|/g, "/").slice(0, 4000);
  }
  function mcqItem(it) {
    var s = it.card + "=" + it.choice + "/" + it.confidence, w = cleanWhy(it.why);
    return w ? s + ' "' + w + '"' : s;
  }
  // ESKİ tek satır (hâlâ üretilebilir; sayfa artık formatBlock kullanır).
  // items: [{card: "gt-012", choice: "B" | "?", confidence: 1-3, why: "…"}]
  function formatResult(lesson, items) {
    return "ders sonucu " + lesson + ": " + items.map(mcqItem).join("; ");
  }
  // v3 blok. r = {kind: "ders"|"tekrar", id, mcq: [mcq öğeleri], writes: [{card, confidence, text}],
  //              questions: ["…"], seconds: [{card, seconds}]}
  function formatBlock(r) {
    var lines = [(r.kind || "ders") + " sonucu " + r.id + " v3"];
    if (r.mcq && r.mcq.length) lines.push("mcq: " + r.mcq.map(mcqItem).join("; "));
    (r.writes || []).forEach(function (w) {
      var t = cleanText(w.text);
      if (t) lines.push("yaz: " + w.card + "/" + w.confidence + " | " + t);
    });
    (r.questions || []).forEach(function (q) {
      var t = cleanText(q);
      if (t) lines.push("soru: " + t);
    });
    if (r.seconds && r.seconds.length) {
      lines.push("süre: " + r.seconds.map(function (s) { return s.card + "=" + s.seconds + "s"; }).join("; "));
    }
    return lines.join("\n");
  }
  function parseMcq(s, into) {
    var re = /([^\s=;"]+)=([A-Za-z?])(?:\/([1-3]))?(?:\s+"([^"]*)")?/g, x, isNew = false;
    while ((x = re.exec(s))) {
      if (x[3]) isNew = true;
      into.push({ card: x[1], choice: x[2].toUpperCase(), confidence: x[3] ? +x[3] : null, why: x[4] || null });
    }
    return isNew;
  }
  // v3 bloğu ve eski biçimleri okur →
  // {kind: "ders"|"tekrar", lesson, format: "v3"|"new"|"old", items: [mcq], writes: [{card, confidence, text}],
  //  questions: [..], seconds: [{card, seconds}]}; eski biçimlerde writes/questions/seconds boş.
  function parseResult(text) {
    var lines = String(text == null ? "" : text).replace(/\r\n?/g, "\n").split("\n");
    while (lines.length && !lines[0].trim()) lines.shift();
    var m = /^\s*(ders|tekrar)\s+sonucu\s+([^\s:]+)\s*(v3)?\s*:?\s*(.*)$/.exec(lines.shift() || "");
    if (!m) return null;
    var res = { kind: m[1], lesson: m[2], format: "v3", items: [], writes: [], questions: [], seconds: [] };
    if (!m[3]) {
      res.format = parseMcq(m[4], res.items) ? "new" : "old";
      return res;
    }
    lines.forEach(function (line) {
      var k = /^\s*(mcq|yaz|soru|süre|sure)\s*:\s?(.*)$/.exec(line);
      if (!k) return;
      var body = k[2];
      if (k[1] === "mcq") parseMcq(body, res.items);
      else if (k[1] === "yaz") {
        var y = /^\s*([^\s\/|]+)\/([1-3])\s*\|\s?([\s\S]*)$/.exec(body);
        if (y) res.writes.push({ card: y[1], confidence: +y[2], text: y[3].split(/\s*⏎\s*/).join("\n").trim() });
      } else if (k[1] === "soru") {
        var q = body.split(/\s*⏎\s*/).join("\n").trim();
        if (q) res.questions.push(q);
      } else {
        var re = /([^\s=;]+)=(\d+)\s*s/g, x;
        while ((x = re.exec(body))) res.seconds.push({ card: x[1], seconds: +x[2] });
      }
    });
    return res;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { formatResult: formatResult, formatBlock: formatBlock, parseResult: parseResult, cleanWhy: cleanWhy, cleanText: cleanText };
  }
  if (typeof document === "undefined") return;
  window.teachLesson = { formatResult: formatResult, formatBlock: formatBlock, parseResult: parseResult, buildResult: buildResult };

  // ---------- Tema (panoyla aynı: ?theme= > localStorage "teach-theme" > sistem) ----------
  (function () {
    var r = document.documentElement, k = "teach-theme", t = null;
    try { var q = new URLSearchParams(location.search).get("theme"); if (q === "light" || q === "dark") t = q; } catch (e) {}
    if (!t) { try { t = localStorage.getItem(k); } catch (e) {} }
    if (t === "light" || t === "dark") r.setAttribute("data-theme", t);
    if (!window.teachToggleTheme) window.teachToggleTheme = function () {
      var c = r.getAttribute("data-theme");
      if (!c) { try { c = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; } catch (e) { c = "light"; } }
      var n = c === "dark" ? "light" : "dark";
      r.setAttribute("data-theme", n);
      try { localStorage.setItem(k, n); } catch (e) {}
    };
  })();

  // ---------- Panoya gömülü ders (pano iframe'i ya da ?embed=1) ----------
  // html.embed: kendi üst çubuğundaki ← Pano / başlık / ◐ Tema gizlenir (style.css); adım çipi ve sonuç çubuğu
  // çalışmaya devam eder. Tema panodan gelir: ?theme= ve postMessage {teach:"theme", theme}. Sayfa yüklenince
  // panoya {teach:"ready"} gider. ?embed=1 ile açıldıysa göreli bağlantılar (başka ders, referans) panoya
  // {teach:"nav", href} olarak gider; pano o sekmeyi / dökümanı açar. Dış bağlantılar yeni sekmede açılır.
  var EMBED_Q = false, EMBED = false;
  try { EMBED_Q = new URLSearchParams(location.search).get("embed") === "1"; } catch (e) {}
  try { EMBED = EMBED_Q || window.top !== window.self; } catch (e) { EMBED = true; }
  if (EMBED) {
    document.documentElement.classList.add("embed");
    window.addEventListener("message", function (e) {
      var m = e.data;
      if (e.source !== window.parent || !m || m.teach !== "theme") return;
      if (m.theme === "light" || m.theme === "dark") document.documentElement.setAttribute("data-theme", m.theme);
    });
  }
  // Panoya: cevaplanmış ama sonuç satırı kopyalanmamış soru var mı? Varken pano kendini yenilemez.
  function markDirty(on) {
    if (!EMBED) return;
    try { window.parent.postMessage({ type: "teach-dirty", dirty: !!on }, "*"); } catch (e) {}
  }
  function initEmbed() {
    if (!EMBED) return;
    try { window.parent.postMessage({ teach: "ready" }, "*"); } catch (e) {}
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a || e.defaultPrevented) return;
      var h = a.getAttribute("href");
      if (!h || h.charAt(0) === "#") return;
      if (/^https?:/i.test(a.href)) { a.target = "_blank"; a.rel = "noopener"; return; }
      if (!EMBED_Q) return;
      e.preventDefault();
      try { window.parent.postMessage({ teach: "nav", href: a.href }, "*"); } catch (x) {}
    });
  }

  // "15 sorudan 3'ü": sayıya iyelik eki (son okunan sözcüğe göre). tools/learn.py tr_poss ile aynı kural.
  function trPoss(n) {
    var U = { 1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si", 8: "i", 9: "u" };
    var T = { 1: "u", 2: "si", 3: "u", 4: "ı", 5: "si", 6: "ı", 7: "i", 8: "i", 9: "ı" };
    var s = n % 10 ? U[n % 10] : n % 100 ? T[Math.floor(n % 100 / 10)] : n % 1000 ? "ü" : n % 1e6 ? "i" : n % 1e9 ? "u" : "ı";
    return n + "'" + s;
  }


  // Sayfa kimliği: ders (main[data-lesson]) ya da tekrar (main[data-review]); yoksa dosya adı.
  function pageInfo() {
    var m = document.querySelector("main[data-review]");
    if (m && m.dataset.review) return { kind: "tekrar", id: m.dataset.review };
    m = document.querySelector("main[data-lesson]");
    if (m && m.dataset.lesson) return { kind: "ders", id: m.dataset.lesson };
    return { kind: "ders", id: pageSlug() || "ders" };
  }
  function pageSlug() {
    var f = "";
    try { f = decodeURIComponent(location.pathname.split("/").pop() || "").replace(/\.html?$/, ""); } catch (e) {}
    return f;
  }

  // localStorage: her erişim try/catch (gizli pencere, kısıtlı file://). Yoksa sayfa depolamadan çalışır.
  function loadJSON(key) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : null; } catch (e) { return null; }
  }
  function saveJSON(key, val) {
    try { if (val == null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function typeset(node) {
    if (!node || typeof window.renderMathInElement !== "function") return;
    try {
      window.renderMathInElement(node, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false }
        ],
        throwOnError: false
      });
    } catch (err) { console.error("KaTeX:", err); }
  }

  // Panoya kopyala: navigator.clipboard, olmazsa geçici textarea + execCommand.
  function copyText(t, done) {
    var fallback = function () {
      var ok = false, ta = document.createElement("textarea");
      ta.value = t; ta.setAttribute("readonly", ""); ta.setAttribute("aria-hidden", "true");
      ta.style.position = "fixed"; ta.style.top = "0"; ta.style.left = "0"; ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      done(ok);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(function () { done(true); }, fallback);
    } else fallback();
  }
  // text: dize ya da o anki dizeyi döndüren işlev
  function copyButton(text) {
    var b = el("button", "btn", "Kopyala");
    b.type = "button";
    b.addEventListener("click", function () {
      var t = typeof text === "function" ? text() : text;
      copyText(t, function (ok) {
        if (ok) markDirty(false);
        b.textContent = ok ? "Kopyalandı" : "Kopyalanamadı";
        setTimeout(function () { b.textContent = "Kopyala"; }, 1500);
      });
    });
    return b;
  }

  // Eminlik seçici (quiz ve write aynı): [Tahmin | Emin değilim | Eminim]
  function confButtons(onPick) {
    var box = el("div", "conf-opts");
    box.setAttribute("role", "radiogroup");
    var btns = [1, 2, 3].map(function (n) {
      var b = el("button", null, CONF[n]);
      b.type = "button"; b.setAttribute("role", "radio"); b.setAttribute("aria-checked", "false");
      b.addEventListener("click", function () { onPick(n); });
      box.appendChild(b);
      return b;
    });
    return { box: box, btns: btns, set: function (conf, disabled) {
      btns.forEach(function (b, k) {
        b.disabled = !!disabled;
        b.setAttribute("aria-checked", !disabled && conf === k + 1 ? "true" : "false");
      });
    } };
  }
  function autoGrow(ta) {
    ta.style.height = "auto";
    ta.style.height = (ta.scrollHeight + 2) + "px";
  }

  // ---------- Sayfa sonucu: mcq + yaz + soru + süre tek yerde (v3 blok) ----------
  var R = {
    mcqOrder: [], mcq: {},          // data-card'lı quiz'ler, sayfa sırası → cevap
    writeOrder: [], writes: {},     // .write[data-card] → kaydedilmiş {card, confidence, text}
    asks: [],                       // .ask-box okuyucuları → [satır]
    timerOrder: [], timers: {},     // .timer[data-card] → saniye
    bar: null, ready: false
  };
  function resultState() {
    var p = pageInfo();
    return {
      kind: p.kind, id: p.id,
      mcq: R.mcqOrder.map(function (c) { return R.mcq[c]; }).filter(Boolean),
      writes: R.writeOrder.map(function (c) { return R.writes[c]; }).filter(Boolean),
      questions: R.asks.reduce(function (acc, f) { return acc.concat(f()); }, []),
      seconds: R.timerOrder.filter(function (c) { return R.timers[c] != null; }).map(function (c) { return { card: c, seconds: R.timers[c] }; })
    };
  }
  function buildResult() { return formatBlock(resultState()); }
  function counts() {
    var st = resultState();
    return { total: R.mcqOrder.length + R.writeOrder.length, done: st.mcq.length + st.writes.length, questions: st.questions.length };
  }

  // Yapışkan sonuç çubuğu: ilk cevaptan (ya da ilk sorudan) sonra görünür, her değişiklikte güncellenir.
  function renderBar(c) {
    if (!R.bar) {
      R.bar = el("div", "result-bar");
      R.bar.setAttribute("role", "region");
      R.bar.setAttribute("aria-label", "Sayfa sonucu");
      var inner = el("div", "rb-inner");
      inner.appendChild(el("span", "rb-count"));
      inner.appendChild(copyButton(buildResult));
      R.bar.appendChild(inner);
      document.body.appendChild(R.bar);
      document.body.classList.add("has-result-bar");
      requestAnimationFrame(function () { requestAnimationFrame(function () { R.bar.classList.add("show"); }); });
    }
    var cnt = R.bar.querySelector(".rb-count");
    cnt.textContent = "";
    var noun = R.writeOrder.length ? " öğeden " : " sorudan ";
    cnt.appendChild(el("b", null, c.total ? c.total + noun + trPoss(c.done) + " cevaplandı" : "Sorun hazır"));
    cnt.appendChild(document.createTextNode(" · kopyala, sohbete yapıştır"));
  }
  function renderScore(c) {
    var scoreEl = document.querySelector(".score");
    if (!scoreEl) return;
    scoreEl.textContent = ""; // puan gösterilmez; yalnızca sohbete taşınacak blok
    if (!c.total || c.done < c.total) return;
    var block = buildResult();
    var wrap = el("div", "result-block");
    wrap.appendChild(el("pre", null, block));
    wrap.appendChild(copyButton(buildResult));
    wrap.appendChild(el("span", "hint", "Sohbete yapıştır."));
    scoreEl.appendChild(wrap);
  }
  function renderResult() {
    if (!R.ready) return;
    var c = counts();
    if (!c.done && !c.questions && !R.bar) return;
    renderBar(c);
    renderScore(c);
  }

  // ---------- Quiz ----------
  function initQuizzes() {
    var quizzes = Array.prototype.slice.call(document.querySelectorAll(".quiz"));
    quizzes.forEach(function (quiz, qi) {
      var cardMode = !!quiz.dataset.card;
      if (cardMode) R.mcqOrder.push(quiz.dataset.card);
      if (!quiz.querySelector(".quiz-label")) {
        quiz.insertBefore(el("div", "quiz-label", (quiz.dataset.label || "Soru") + " " + (qi + 1)), quiz.firstChild);
      }
      var answer = parseInt(quiz.dataset.answer, 10);
      var box = quiz.querySelector(".opts") || quiz;
      var opts = Array.prototype.slice.call(quiz.querySelectorAll(".opt"));
      var fb = quiz.querySelector(".feedback");
      opts.forEach(function (o) {
        if (!o.querySelector(".radio")) o.insertBefore(el("span", "radio"), o.firstChild);
        o.type = "button";
      });

      // i: seçilen şık sırası, -1 = Bilmiyorum
      function reveal(i, extra) {
        if (cardMode) markDirty(true); // only recorded questions have a result block to carry over
        var all = quiz.querySelectorAll(".opt");
        Array.prototype.forEach.call(all, function (o) { o.disabled = true; });
        var ok = i === answer;
        if (i >= 0) opts[i].classList.add("selected", ok ? "correct" : "incorrect");
        if (opts[answer]) opts[answer].classList.add("correct");
        if (fb) {
          fb.className = "feedback show " + (ok ? "ok" : "no");
          var rightWhy = opts[answer] ? opts[answer].dataset.why || "" : "";
          fb.textContent = i < 0
            ? "Bilmiyorum demek dürüst bir cevap. Doğru şık işaretlendi" + (rightWhy ? ": " + rightWhy : ".")
            : (ok ? "Doğru. " : "Değil. ") + (opts[i].dataset.why || "") + (!ok && rightWhy ? " — Doğru cevap: " + rightWhy : "");
          typeset(fb);
        }
        if (extra) extra(ok);
        renderResult();
      }

      if (!cardMode) {
        opts.forEach(function (opt, i) { opt.addEventListener("click", function () { reveal(i); }); });
        return;
      }

      // --- LH soru kartı: seç → eminlik → (neden) → Cevapla ---
      box.setAttribute("role", "radiogroup");
      var dk = el("button", "opt dk");
      dk.type = "button";
      dk.appendChild(el("span", "radio"));
      dk.appendChild(el("span", null, "Bilmiyorum"));
      box.appendChild(dk);

      var sel = null, conf = null;
      var controls = el("div", "quiz-controls");
      var confRow = el("div", "quiz-row");
      confRow.appendChild(el("span", "ui-label", "Ne kadar eminsin?"));
      var cb = confButtons(function (n) { conf = n; update(); });
      confRow.appendChild(cb.box);
      var whyRow = el("label", "quiz-row");
      whyRow.appendChild(el("span", "ui-label", "Neden?"));
      var why = el("input", "why-input");
      why.type = "text"; why.maxLength = 240;
      why.placeholder = "İsteğe bağlı: tek cümle, aklına geleni yaz.";
      whyRow.appendChild(why);
      var actions = el("div", "quiz-actions");
      var hint = el("span", "hint", "Önce bir şık, sonra eminlik seç.");
      var go = el("button", "btn primary", "Cevapla");
      go.type = "button";
      actions.appendChild(hint); actions.appendChild(go);
      controls.appendChild(confRow); controls.appendChild(whyRow); controls.appendChild(actions);
      if (fb) quiz.insertBefore(controls, fb); else quiz.appendChild(controls);

      var rows = opts.concat([dk]);
      rows.forEach(function (o, i) {
        o.setAttribute("role", "radio");
        o.addEventListener("click", function () { sel = o === dk ? -1 : i; update(); });
      });

      function ready() { return sel !== null && (sel === -1 || conf !== null); }
      function update() {
        rows.forEach(function (o, i) {
          var on = (o === dk ? -1 : i) === sel;
          o.classList.toggle("selected", on);
          o.setAttribute("aria-checked", on ? "true" : "false");
        });
        var isDk = sel === -1;
        confRow.classList.toggle("dim", isDk);
        cb.set(conf, isDk);
        go.disabled = !ready();
        hint.textContent = sel === null ? "Önce bir şık, sonra eminlik seç." : (ready() ? "Hazırsan cevapla." : "Ne kadar emin olduğunu seç.");
      }
      function submit() {
        if (!ready()) return;
        var c = sel === -1 ? 1 : conf, w = cleanWhy(why.value);
        R.mcq[quiz.dataset.card] = { card: quiz.dataset.card, choice: sel === -1 ? "?" : LETTERS[sel], confidence: c, why: w };
        reveal(sel, function () {
          if (sel === -1) dk.classList.add("selected");
          var rec = el("div", "quiz-record");
          rec.appendChild(document.createTextNode("EMİNLİK "));
          rec.appendChild(el("b", null, sel === -1 ? "Bilmiyorum" : CONF[c]));
          if (w) { rec.appendChild(document.createTextNode(" · NEDEN ")); rec.appendChild(el("b", null, w)); }
          controls.parentNode.replaceChild(rec, controls);
        });
      }
      go.addEventListener("click", submit);
      why.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); submit(); } });
      update();
    });
  }

  // ---------- Açık cevap kutusu: .write[data-card] ----------
  function initWrites() {
    var page = pageInfo();
    Array.prototype.slice.call(document.querySelectorAll(".write[data-card]")).forEach(function (box, i) {
      var card = box.dataset.card, key = "teach-write:" + page.id + ":" + card;
      R.writeOrder.push(card);
      if (!box.querySelector(".quiz-label")) {
        box.insertBefore(el("div", "quiz-label", (box.dataset.label || "Yaz") + " " + (i + 1)), box.firstChild);
      }
      var ta = el("textarea", "write-input");
      ta.rows = 3;
      ta.placeholder = "Kendi cümlelerinle… (bakmadan)";
      ta.setAttribute("aria-label", "Cevabın");
      box.appendChild(ta);

      var conf = null, saved = false;
      var controls = el("div", "quiz-controls");
      var confRow = el("div", "quiz-row");
      confRow.appendChild(el("span", "ui-label", "Ne kadar eminsin?"));
      var cb = confButtons(function (n) { conf = n; update(); persist(); });
      confRow.appendChild(cb.box);
      var actions = el("div", "quiz-actions");
      var hint = el("span", "hint", "");
      var go = el("button", "btn primary", "Kaydet");
      go.type = "button";
      actions.appendChild(hint); actions.appendChild(go);
      controls.appendChild(confRow); controls.appendChild(actions);
      box.appendChild(controls);

      var rec = el("div", "quiz-record");
      rec.hidden = true;
      box.appendChild(rec);

      function ready() { return !!ta.value.trim() && conf !== null; }
      function update() {
        cb.set(conf, false);
        go.disabled = !ready();
        hint.textContent = !ta.value.trim() ? "Önce yaz, sonra eminlik seç." : (ready() ? "Hazırsan kaydet." : "Ne kadar emin olduğunu seç.");
      }
      function persist() { saveJSON(key, { text: ta.value, conf: conf, saved: saved }); }
      function lock() {
        saved = true;
        ta.readOnly = true;
        box.classList.add("saved");
        controls.hidden = true;
        rec.textContent = "";
        rec.appendChild(document.createTextNode("EMİNLİK "));
        rec.appendChild(el("b", null, CONF[conf]));
        rec.appendChild(document.createTextNode(" · "));
        var edit = el("a", "edit", "Düzenle");
        edit.href = "#";
        edit.addEventListener("click", function (e) { e.preventDefault(); unlock(); persist(); renderResult(); ta.focus(); });
        rec.appendChild(edit);
        rec.hidden = false;
        R.writes[card] = { card: card, confidence: conf, text: ta.value };
      }
      function unlock() {
        saved = false;
        ta.readOnly = false;
        box.classList.remove("saved");
        controls.hidden = false;
        rec.hidden = true;
        delete R.writes[card];
        update();
      }
      ta.addEventListener("input", function () { autoGrow(ta); update(); persist(); });
      go.addEventListener("click", function () {
        if (!ready()) return;
        lock(); persist(); markDirty(true); renderResult();
      });

      var s = loadJSON(key);
      if (s && typeof s === "object") {
        if (typeof s.text === "string") ta.value = s.text;
        if (s.conf === 1 || s.conf === 2 || s.conf === 3) conf = s.conf;
        if (s.saved && ready()) lock();
      }
      update();
      autoGrow(ta);
    });
  }

  // ---------- Soru kutusu: .ask-box ----------
  function initAskBoxes() {
    var key = "teach-ask:" + (pageSlug() || pageInfo().id);
    Array.prototype.slice.call(document.querySelectorAll(".ask-box")).forEach(function (box, i) {
      var k = i ? key + ":" + (i + 1) : key;
      if (!box.querySelector(".ui-label, .q")) box.appendChild(el("div", "ui-label", "Anlamadığım / sormak istediğim"));
      var ta = el("textarea", "ask-input");
      ta.rows = 2;
      ta.placeholder = "Her satır bir soru. Kopyala'yla sohbete gider.";
      ta.setAttribute("aria-label", "Sorun");
      box.appendChild(ta);
      var s = loadJSON(k);
      if (s && typeof s.text === "string") ta.value = s.text;
      R.asks.push(function () {
        return ta.value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
      });
      ta.addEventListener("input", function () { autoGrow(ta); saveJSON(k, { text: ta.value }); renderResult(); });
      autoGrow(ta);
    });
  }

  // ---------- Süre: .timer[data-card][data-seconds] ----------
  function initTimers() {
    var page = pageInfo();
    Array.prototype.slice.call(document.querySelectorAll(".timer[data-card]")).forEach(function (host) {
      var card = host.dataset.card, limit = parseInt(host.dataset.seconds, 10) || 60;
      var key = "teach-timer:" + page.id + ":" + card;
      R.timerOrder.push(card);
      var btn = el("button", "btn", "Başlat"), clock = el("span", "t-clock"), note = el("span", "hint", "");
      btn.type = "button";
      host.appendChild(el("span", "ui-label", "Süre"));
      host.appendChild(clock); host.appendChild(btn); host.appendChild(note);
      var t0 = null, iv = null;
      function fmt(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
      function finish(elapsed) {
        if (iv) clearInterval(iv);
        iv = null; t0 = null;
        elapsed = Math.min(limit, Math.max(1, Math.round(elapsed)));
        R.timers[card] = elapsed;
        saveJSON(key, { seconds: elapsed });
        host.classList.remove("running"); host.classList.add("done");
        clock.textContent = fmt(elapsed);
        btn.textContent = "Yeniden";
        note.textContent = elapsed + " sn kaydedildi";
        renderResult();
      }
      function tick() {
        var e = (Date.now() - t0) / 1000;
        if (e >= limit) { finish(limit); return; }
        clock.textContent = fmt(Math.ceil(limit - e));
      }
      btn.addEventListener("click", function () {
        if (t0 !== null) { finish((Date.now() - t0) / 1000); return; }
        t0 = Date.now();
        host.classList.add("running"); host.classList.remove("done");
        btn.textContent = "Durdur"; note.textContent = "";
        clock.textContent = fmt(limit);
        iv = setInterval(tick, 250);
      });
      var s = loadJSON(key);
      if (s && s.seconds > 0) {
        R.timers[card] = Math.min(limit, Math.round(s.seconds));
        host.classList.add("done");
        clock.textContent = fmt(R.timers[card]);
        btn.textContent = "Yeniden";
        note.textContent = R.timers[card] + " sn kaydedildi";
      } else clock.textContent = fmt(limit);
    });
  }

  // ---------- Ders modu: adımlar, üst çubuk çipi, ilerleme çizgisi ----------
  function initSteps() {
    var steps = Array.prototype.slice.call(document.querySelectorAll("section.step"));
    var n = steps.length;
    document.querySelectorAll("[data-step-count]").forEach(function (e) { e.textContent = n; });
    // Hedef kartında adım / kontrol sayısı tekrar olur (çip ve ilerleme çizgisi var): gizle. Panoda Başvuru
    // bağlantıları da sağdaki notlar sütununda zaten var.
    // Süre etiket satırına taşınır: "BU DERSİN SONUNDA · ~15 DK".
    document.querySelectorAll(".goal").forEach(function (goal) {
      var label = goal.querySelector(".ui-label"), meta = goal.querySelector(".goal-meta");
      if (!meta) return;
      var shown = 0;
      Array.prototype.forEach.call(meta.children, function (sp) {
        var link = sp.querySelector("a"), counts = sp.querySelector("[data-step-count], [data-check-count]");
        if (counts || (EMBED && link)) { sp.style.display = "none"; return; }
        if (!link && label && /\d/.test(sp.textContent)) {
          label.textContent += " · " + sp.textContent.replace(/\s+/g, " ").replace(/(\d)([^\d\s])/, "$1 $2").trim();
          sp.style.display = "none"; return;
        }
        shown++;
      });
      if (!shown) meta.style.display = "none";
    });
    var checks = document.querySelectorAll(".quiz[data-card], .write[data-card]").length;
    document.querySelectorAll("[data-check-count]").forEach(function (e) { e.textContent = checks; });
    document.querySelectorAll(".theme-btn").forEach(function (b) {
      if (!b.hasAttribute("onclick")) b.addEventListener("click", function () { window.teachToggleTheme(); });
    });
    var chip = document.querySelector(".lesson-bar .lb-step");
    var line = document.querySelector(".lesson-bar .lb-progress i");
    var titles = steps.map(function (s, i) {
      var h = s.querySelector("h2");
      var t = s.dataset.title || (h ? h.textContent.trim() : "");
      if (h && !s.querySelector(".step-kicker")) {
        var k = el("div", "ui-label step-kicker");
        k.appendChild(el("b", null, "Adım " + (i + 1)));
        s.insertBefore(k, h);
      }
      return t;
    });
    var cur = -1;
    function update() {
      var y = window.innerHeight * 0.35, idx = 0;
      steps.forEach(function (s, i) { if (s.getBoundingClientRect().top <= y) idx = i; });
      if (chip && n && idx !== cur) {
        cur = idx;
        chip.textContent = "Adım " + (idx + 1) + " · " + titles[idx];
        chip.title = chip.textContent;
      }
      if (line) {
        var d = document.documentElement, max = d.scrollHeight - window.innerHeight;
        line.style.width = (max > 0 ? Math.min(100, Math.max(0, 100 * window.scrollY / max)) : 0) + "%";
      }
    }
    if (n && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(update, { rootMargin: "0px 0px -60% 0px", threshold: [0, 1] });
      steps.forEach(function (s) { io.observe(s); });
    }
    var ticking = false;
    window.addEventListener("scroll", function () {
      if (ticking) return; ticking = true;
      requestAnimationFrame(function () { ticking = false; update(); });
    }, { passive: true });
    window.addEventListener("resize", update);
    update();
  }

  // ---------- Harita yuvası: SVG yapıştırılmamışsa sade çipler ----------
  function initLessonMap() {
    document.querySelectorAll(".lmap-slot").forEach(function (slot) {
      var svg = slot.querySelector("svg");
      if ((svg && svg.childElementCount) || slot.querySelector(".lmap-fallback")) return;
      var nodes = (slot.dataset.nodes || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
      if (!nodes.length) return;
      var row = el("div", "lmap-fallback");
      nodes.forEach(function (id, i) {
        if (i) row.appendChild(el("span", "lmap-arrow", "→"));
        row.appendChild(el("span", "lmap-node" + (id === slot.dataset.current ? " current" : ""), id));
      });
      slot.appendChild(row);
    });
  }

  // ---------- Konum görseli: .position-slot[data-style][data-pos] (path | pyramid | ring) ----------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function initPositions() {
    document.querySelectorAll(".position-slot").forEach(function (slot) {
      var raw = slot.dataset.pos;
      if (!raw || !raw.trim()) return; // refresh doldurana kadar boş kalır (CSS gizler)
      var p; try { p = JSON.parse(raw); } catch (e) { console.error("position JSON hatası:", e, slot); return; }
      var path = Array.isArray(p.path) ? p.path : [], labels = p.labels || {}, idx = path.indexOf(p.current);
      var done = Math.max(0, +p.done || 0), total = Math.max(done, +p.total || 0);
      var lab = function (id) { var t = labels[id] || id || ""; return t.length > 18 ? t.slice(0, 17) + "…" : t; };
      var st = function (i) { return idx < 0 ? "dim" : i < idx ? "visited" : i === idx ? "current" : "dim"; };
      var style = slot.dataset.style === "pyramid" || slot.dataset.style === "ring" ? slot.dataset.style : "path";
      var draw = { path: posPath, pyramid: posPyramid, ring: posRing }[style];
      slot.innerHTML = draw(path, lab, st, done, total, idx);
      slot.querySelector("svg").classList.add("diagram", "position", style);
    });
  }
  function posBar(x, y, w, done, total) {
    return '<rect class="pbar-track" x="' + x + '" y="' + y + '" width="' + w + '" height="3" rx="1.5"/>' +
      (total ? '<rect class="pbar-fill" x="' + x + '" y="' + y + '" width="' + (w * done / total).toFixed(1) + '" height="3" rx="1.5"/>' : "") +
      '<text class="meta" x="' + (x + w) + '" y="' + (y + 16) + '" text-anchor="end">' + done + " / " + total + " düğüm</text>";
  }
  // Yatay adımlayıcı: kutular soldan sağa, oklu; altında ince ilerleme çizgisi.
  function posPath(path, lab, st, done, total) {
    var gap = 26, h = 30, x = 0, parts = [], boxes = [];
    path.forEach(function (id, i) {
      var w = Math.max(60, lab(id).length * 6.6 + 18);
      boxes.push({ x: x, w: w, id: id, i: i }); x += w + gap;
    });
    var W = Math.round(Math.max(120, x - gap));
    boxes.forEach(function (b, k) {
      if (k) parts.push('<path class="edge' + (st(b.i) === "dim" ? " dim" : "") + '" d="M' + (b.x - gap + 1) + "," + (h / 2) + " L" + (b.x - 1) + "," + (h / 2) + '"/>');
      parts.push('<g class="node ' + st(b.i) + '"><rect x="' + b.x.toFixed(1) + '" y="0" width="' + b.w.toFixed(1) + '" height="' + h + '" rx="3"/>' +
        '<text x="' + (b.x + b.w / 2).toFixed(1) + '" y="' + (h / 2) + '">' + esc(lab(b.id)) + "</text></g>");
    });
    parts.push(posBar(0, h + 14, W, done, total));
    return '<svg viewBox="-1 -1 ' + (W + 2) + " " + (h + 36) + '" role="img" aria-label="Konum: ' + done + " / " + total + ' düğüm">' + parts.join("") + "</svg>";
  }
  // Piramit: temel altta (path[0]), hedef tepede; biten katlar gri dolu, şimdiki çerçeveli, gelecek soluk.
  function posPyramid(path, lab, st, done, total) {
    var n = path.length || 1, W = 320, h = 26, gap = 4, parts = [];
    path.forEach(function (id, i) {
      var w = W - (W * 0.72) * i / Math.max(1, n - 1), x = (W - w) / 2, y = (n - 1 - i) * (h + gap);
      parts.push('<g class="node ' + st(i) + '"><rect x="' + x.toFixed(1) + '" y="' + y + '" width="' + w.toFixed(1) + '" height="' + h + '" rx="3"/>' +
        '<text x="' + (W / 2) + '" y="' + (y + h / 2) + '">' + esc(lab(id)) + "</text></g>");
    });
    var H = n * (h + gap) - gap;
    parts.push(posBar(0, H + 12, W, done, total));
    return '<svg viewBox="-1 -1 ' + (W + 2) + " " + (H + 34) + '" role="img" aria-label="Konum: ' + done + " / " + total + ' düğüm">' + parts.join("") + "</svg>";
  }
  // Halka: biten/toplam yayı; ortada şimdiki düğüm, altında "→ sonraki".
  function posRing(path, lab, st, done, total, idx) {
    var r = 44, c = 2 * Math.PI * r, f = total ? c * done / total : 0, cur = idx >= 0 ? path[idx] : "", next = idx >= 0 ? path[idx + 1] : path[0];
    return '<svg viewBox="0 0 140 150" role="img" aria-label="Konum: ' + done + " / " + total + ' düğüm">' +
      '<circle class="ring-track" cx="70" cy="60" r="' + r + '"/>' +
      '<circle class="ring-fill" cx="70" cy="60" r="' + r + '" transform="rotate(-90 70 60)" stroke-dasharray="' + f.toFixed(1) + " " + c.toFixed(1) + '"/>' +
      '<g class="node current"><text x="70" y="55">' + esc(lab(cur)) + '</text></g>' +
      '<text class="meta" x="70" y="74" text-anchor="middle">' + done + " / " + total + "</text>" +
      (next ? '<text class="label" x="70" y="130" text-anchor="middle">→ ' + esc(lab(next)) + "</text>" : "") + "</svg>";
  }

  // ---------- Diyagram: ok başları (bir kez) ----------
  function initDiagrams() {
    if (!document.querySelector("svg.diagram") || document.getElementById("dg-arrow")) return;
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", "0"); svg.setAttribute("height", "0"); svg.setAttribute("aria-hidden", "true");
    svg.style.position = "absolute";
    svg.innerHTML = "<defs>" + ["", "-dim"].map(function (s) {
      return '<marker id="dg-arrow' + s + '" viewBox="0 0 8 8" refX="7.5" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
        '<path class="dg-arrowhead' + (s ? " dim" : "") + '" d="M0,0.5 L8,4 L0,7.5 z"/></marker>';
    }).join("") + "</defs>";
    document.body.insertBefore(svg, document.body.firstChild);
  }

  // ---------- Ödeme matrisi ----------
  function nashCells(g) {
    var out = [];
    for (var i = 0; i < g.pay.length; i++) {
      for (var j = 0; j < g.pay[i].length; j++) {
        if (deviation(g, i, j) === null) out.push(i + "," + j);
      }
    }
    return out;
  }

  // Tek taraflı kârlı sapma varsa açıklamasını döndürür, yoksa null.
  function deviation(g, i, j) {
    var cur = g.pay[i][j];
    for (var k = 0; k < g.pay.length; k++) {
      if (g.pay[k][j][0] > cur[0]) {
        return g.rows.player + " “" + g.rows.s[i] + "” yerine “" + g.rows.s[k] + "” oynarsa " + cur[0] + " → " + g.pay[k][j][0] + " kazanır.";
      }
    }
    for (var m = 0; m < g.pay[i].length; m++) {
      if (g.pay[i][m][1] > cur[1]) {
        return g.cols.player + " “" + g.cols.s[j] + "” yerine “" + g.cols.s[m] + "” oynarsa " + cur[1] + " → " + g.pay[i][m][1] + " kazanır.";
      }
    }
    return null;
  }

  function isBestResponse(g, i, j, who) {
    if (who === 0) return g.pay.every(function (row) { return row[j][0] <= g.pay[i][j][0]; });
    return g.pay[i].every(function (c) { return c[1] <= g.pay[i][j][1]; });
  }

  function cellLabel(g, key) {
    var p = key.split(",");
    return "(" + g.rows.s[+p[0]] + ", " + g.cols.s[+p[1]] + ")";
  }

  function parseConfig(host, attr, what) {
    try { return JSON.parse(host.dataset[attr]); } catch (err) {
      host.innerHTML = '<div class="feedback show no">' + what + ' verisi okunamadı (data-* içinde kaçışsız tek tırnak olabilir — &amp;#39; kullan).</div>';
      console.error(what + " JSON hatası:", err, host);
      return null;
    }
  }

  function initMatrices() {
    document.querySelectorAll(".payoff-game").forEach(function (host) {
      var g = parseConfig(host, "game", "Matris");
      if (!g) return;
      var mode = g.mode || "static";
      var nCols = g.cols.s.length;
      var html = '<div class="payoff-wrap"><table class="payoff"><tr><th></th><th></th><th class="player" colspan="' + nCols + '">' + g.cols.player + "</th></tr>";
      html += "<tr><th></th><th></th>" + g.cols.s.map(function (s) { return "<th>" + s + "</th>"; }).join("") + "</tr>";
      g.rows.s.forEach(function (rs, i) {
        html += "<tr>" + (i === 0 ? '<th class="player p1" rowspan="' + g.rows.s.length + '">' + g.rows.player + "</th>" : "") + '<th class="p1">' + rs + "</th>";
        g.pay[i].forEach(function (c, j) {
          html += '<td class="cell' + (mode === "nash" ? " clickable" : "") + '" data-k="' + i + "," + j + '"><span class="a" data-who="0">' + c[0] + '</span>, <span class="b" data-who="1">' + c[1] + "</span></td>";
        });
        html += "</tr>";
      });
      html += "</table>";
      if (g.caption) html += '<div class="payoff-caption">' + g.caption + "</div>";
      html += '<div class="controls"><button class="btn" data-act="br">Best response’ları göster</button>';
      if (mode === "nash") html += '<button class="btn primary" data-act="check">Seçtiğim equilibrium’ları kontrol et</button><button class="btn" data-act="reset">Sıfırla</button>';
      html += '</div><div class="feedback"></div></div>';
      host.innerHTML = html;

      var picked = {};
      var fb = host.querySelector(".feedback");
      var cells = host.querySelectorAll("td.cell");

      if (mode === "nash") {
        cells.forEach(function (td) {
          td.addEventListener("click", function () {
            var k = td.dataset.k;
            picked[k] = !picked[k];
            td.classList.toggle("picked", picked[k]);
            td.classList.remove("is-ne", "wrong");
            fb.className = "feedback";
          });
        });
      }

      host.querySelector('[data-act="br"]').addEventListener("click", function (e) {
        var on = !host.classList.contains("show-br");
        host.classList.toggle("show-br", on);
        e.target.textContent = on ? "Best response’ları gizle" : "Best response’ları göster";
        cells.forEach(function (td) {
          var p = td.dataset.k.split(",");
          td.querySelectorAll("span[data-who]").forEach(function (sp) {
            sp.classList.toggle("br", on && isBestResponse(g, +p[0], +p[1], +sp.dataset.who));
          });
        });
      });

      var check = host.querySelector('[data-act="check"]');
      if (check) check.addEventListener("click", function () {
        var truth = nashCells(g);
        var chosenCells = Object.keys(picked).filter(function (k) { return picked[k]; });
        var msgs = [];
        cells.forEach(function (td) {
          var k = td.dataset.k;
          td.classList.remove("is-ne", "wrong");
          if (picked[k] && truth.indexOf(k) >= 0) td.classList.add("is-ne");
          if (picked[k] && truth.indexOf(k) < 0) {
            td.classList.add("wrong");
            var p = k.split(",");
            msgs.push(cellLabel(g, k) + " bir Nash equilibrium değil: " + deviation(g, +p[0], +p[1]));
          }
        });
        var missed = truth.filter(function (k) { return !picked[k]; });
        if (missed.length) msgs.push(missed.length + " equilibrium daha kaçırdın. İpucu: her hücrede iki oyuncuya da “tek başına sapınca kazanır mısın?” diye sor.");
        if (!chosenCells.length) msgs = ["Önce Nash equilibrium olduğunu düşündüğün hücre(ler)e tıkla."];
        var ok = msgs.length === 0;
        fb.className = "feedback show " + (ok ? "ok" : "no");
        fb.textContent = ok
          ? "Doğru! Nash equilibrium: " + truth.map(function (k) { return cellLabel(g, k); }).join(" ve ") + ". Burada hiçbir oyuncu tek başına sapmakla kazanamaz."
          : msgs.join(" ");
      });

      var reset = host.querySelector('[data-act="reset"]');
      if (reset) reset.addEventListener("click", function () {
        picked = {};
        cells.forEach(function (td) { td.classList.remove("picked", "is-ne", "wrong"); });
        fb.className = "feedback";
      });
    });
  }

  // ---------- Doğruluk tablosu: küçük önerme-mantığı ayrıştırıcısı ----------
  function normalize(s) {
    return s.replace(/<->|<=>|↔/g, "⇔").replace(/->|=>|→/g, "⇒")
      .replace(/&&|&|\band\b/gi, "∧").replace(/\|\||\||\bor\b/gi, "∨").replace(/!|~|\bnot\b/gi, "¬");
  }
  function tokenize(s) {
    var toks = [], i = 0; s = normalize(s);
    while (i < s.length) {
      var ch = s[i];
      if (/\s/.test(ch)) { i++; continue; }
      if (/[A-Za-z]/.test(ch)) { toks.push({ t: "var", v: ch.toUpperCase() }); i++; continue; }
      if ("¬∧∨⇒⇔()".indexOf(ch) >= 0) { toks.push({ t: ch }); i++; continue; }
      throw new Error("Tanınmayan simge: " + ch);
    }
    return toks;
  }
  function parse(expr) {
    var toks = tokenize(expr), pos = 0;
    function peek() { return toks[pos] && toks[pos].t; }
    function eat(t) { if (peek() !== t) throw new Error("Beklenen " + t); pos++; }
    function atom() {
      var tk = toks[pos];
      if (!tk) throw new Error("İfade eksik");
      if (tk.t === "var") { pos++; return function (env) { if (!(tk.v in env)) throw new Error("Bilinmeyen değişken " + tk.v); return env[tk.v]; }; }
      if (tk.t === "(") { pos++; var e = iff(); eat(")"); return e; }
      throw new Error("Beklenmeyen " + tk.t);
    }
    function not() { if (peek() === "¬") { pos++; var e = not(); return function (env) { return !e(env); }; } return atom(); }
    function and() { var l = not(); while (peek() === "∧") { pos++; var r = not(); l = (function (a, b) { return function (env) { return a(env) && b(env); }; })(l, r); } return l; }
    function or() { var l = and(); while (peek() === "∨") { pos++; var r = and(); l = (function (a, b) { return function (env) { return a(env) || b(env); }; })(l, r); } return l; }
    function imp() { var l = or(); if (peek() === "⇒") { pos++; var r = imp(); return function (env) { return !l(env) || r(env); }; } return l; }
    function iff() { var l = imp(); while (peek() === "⇔") { pos++; var r = imp(); l = (function (a, b) { return function (env) { return a(env) === b(env); }; })(l, r); } return l; }
    var f = iff();
    if (pos < toks.length) throw new Error("Fazla simge: " + toks[pos].t);
    return f;
  }
  function rowsFor(vars) {
    var n = vars.length, rows = [];
    for (var k = 0; k < (1 << n); k++) {
      var env = {};
      vars.forEach(function (v, i) { env[v] = !((k >> (n - 1 - i)) & 1); }); // önce hepsi D
      rows.push(env);
    }
    return rows;
  }

  function initTruthTables() {
    document.querySelectorAll(".truth-table").forEach(function (host) {
      var cfg = parseConfig(host, "tt", "Doğruluk tablosu");
      if (!cfg) return;
      var L = cfg.labels || ["D", "Y"];
      var vars = cfg.vars, given = cfg.given || [], cols = cfg.cols || [];
      var fns = {};
      try { given.concat(cols).forEach(function (e) { fns[e] = parse(e); }); }
      catch (err) { host.innerHTML = '<div class="feedback show no">İfade hatası: ' + err.message + "</div>"; return; }
      var rows = rowsFor(vars);
      var lab = function (b) { return b ? L[0] : L[1]; };
      var html = '<div class="payoff-wrap"><table class="payoff tt"><tr>';
      html += vars.map(function (v) { return '<th class="var">' + v + "</th>"; }).join("");
      html += given.map(function (e) { return '<th class="given">' + e + "</th>"; }).join("");
      html += cols.map(function (e) { return "<th>" + e + "</th>"; }).join("") + "</tr>";
      rows.forEach(function (env, ri) {
        html += "<tr>" + vars.map(function (v) { return '<td class="var">' + lab(env[v]) + "</td>"; }).join("");
        html += given.map(function (e) { return '<td class="given">' + lab(fns[e](env)) + "</td>"; }).join("");
        html += cols.map(function (e, ci) { return '<td class="cell clickable fill" data-r="' + ri + '" data-c="' + ci + '"></td>'; }).join("") + "</tr>";
      });
      html += "</table>";
      if (cfg.caption) html += '<div class="payoff-caption">' + cfg.caption + "</div>";
      html += '<div class="controls"><button class="btn primary" data-act="check">Kontrol et</button><button class="btn" data-act="reveal">Çözümü göster</button><button class="btn" data-act="reset">Sıfırla</button></div><div class="feedback"></div></div>';
      host.innerHTML = html;

      var fb = host.querySelector(".feedback");
      var cells = host.querySelectorAll("td.fill");
      var state = {}; // "r,c" -> true/false/undefined
      cells.forEach(function (td) {
        td.addEventListener("click", function () {
          var k = td.dataset.r + "," + td.dataset.c, cur = state[k];
          var next = cur === undefined ? true : (cur === true ? false : undefined);
          state[k] = next;
          td.textContent = next === undefined ? "" : lab(next);
          td.classList.remove("ok", "wrong");
          fb.className = "feedback";
        });
      });
      host.querySelector('[data-act="check"]').addEventListener("click", function () {
        var wrong = 0, empty = 0;
        cells.forEach(function (td) {
          var r = +td.dataset.r, c = +td.dataset.c, k = r + "," + c;
          var truth = fns[cols[c]](rows[r]);
          td.classList.remove("ok", "wrong");
          if (state[k] === undefined) { empty++; return; }
          if (state[k] === truth) td.classList.add("ok"); else { td.classList.add("wrong"); wrong++; }
        });
        var ok = !wrong && !empty;
        fb.className = "feedback show " + (ok ? "ok" : "no");
        fb.textContent = ok ? "Tablo doğru. Şimdi sütunları karşılaştır: hangileri her satırda aynı?"
          : (wrong ? wrong + " hücre yanlış (kırmızı). " : "") + (empty ? empty + " hücre boş. " : "") +
            "Her hücreyi o satırın değerlerinden hesapla; ¬ önce, sonra ∧, ∨, en son ⇒.";
      });
      host.querySelector('[data-act="reveal"]').addEventListener("click", function () {
        cells.forEach(function (td) {
          var r = +td.dataset.r, c = +td.dataset.c, truth = fns[cols[c]](rows[r]);
          state[r + "," + c] = truth; td.textContent = lab(truth); td.classList.remove("wrong"); td.classList.add("ok");
        });
        fb.className = "feedback show no";
        fb.textContent = "Çözüm gösterildi. Bu, kendin doldurmuş sayılmaz: sıfırlayıp bakmadan bir kez daha dene.";
      });
      host.querySelector('[data-act="reset"]').addEventListener("click", function () {
        state = {};
        cells.forEach(function (td) { td.textContent = ""; td.classList.remove("ok", "wrong"); });
        fb.className = "feedback";
      });
    });
  }

  // Δ mark: the app's logo before the lesson bar title, and the tab icon (assets/logo.svg next to this file)
  function initBrand() {
    var me = document.querySelector('script[src$="components.js"]');
    var base = me ? me.getAttribute("src").replace(/components\.js$/, "") : "";
    if (!document.querySelector('link[rel="icon"]')) {
      var l = document.createElement("link");
      l.rel = "icon"; l.href = base + "logo.svg";
      document.head.appendChild(l);
    }
    var t = document.querySelector(".lesson-bar .lb-title");
    if (t && !t.querySelector(".logo")) {
      t.insertAdjacentHTML("afterbegin", '<svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 6 L18.4 17.6 H5.6 Z" ' +
        'fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>' +
        '<circle cx="12" cy="6" r="2" fill="currentColor"/><circle cx="5.6" cy="17.6" r="2" fill="currentColor"/>' +
        '<circle cx="18.4" cy="17.6" r="2" fill="currentColor"/></svg>');
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initBrand();
    initQuizzes();
    initWrites();
    initAskBoxes();
    initTimers();
    initPositions();
    initMatrices();
    initTruthTables();
    initDiagrams();
    initLessonMap();
    initSteps();
    initEmbed();
    R.ready = true;
    renderResult(); // depodan geri gelen kayıtlı yazılar / sorular varsa çubuk hemen çıkar
    typeset(document.querySelector("main") || document.body);
  });
})();
