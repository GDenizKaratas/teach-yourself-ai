/* Ortak ders bileşenleri (assets/components.js). Her ders ve referans sayfası bunu yükler.
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
 *    data-card'sız kart (eski dersler 0001–0002): eski davranış — şıkka tıklamak hemen cevaplar.
 *
 *    Puan hiçbir yerde gösterilmez. Sayfada <div class="score"></div> varsa, bütün sorular cevaplanınca
 *    data-card'lı sorular için kopyalanabilir SONUÇ SATIRI çıkar (Kopyala düğmesiyle):
 *
 *      ders sonucu 0003: gt-012=B/3 "çünkü ikisi de sapmak ister"; gt-013=?/1; gt-014=A/2
 *
 *    Öğe = KART=SEÇİM/EMİNLİK [boşluk "neden"], öğeler "; " ile ayrılır. SEÇİM: A, B, C, … ya da
 *    ? (Bilmiyorum). EMİNLİK: 1–3. Neden metni çift tırnak içinde, tek satır; içindeki " → ' olur.
 *    ESKİ BİÇİM (0001–0002 dönemi, hâlâ okunur): "ders sonucu 0002: pts-010=B pts-015=C" —
 *    boşlukla ayrılmış KART=HARF, eminlik ve neden yok. teachLesson.parseResult ikisini de okur.
 *    Öğretmen her öğeyi `tools/learn record --source lesson` ile kaydeder (lesson SKILL.md).
 *
 * 2) Ödeme matrisi — <div class="payoff-game" data-game='{...}'></div>
 *    {
 *      "rows": {"player": "Britanya", "s": ["Sınırla", "İnşa et"]},
 *      "cols": {"player": "Almanya",  "s": ["Sınırla", "İnşa et"]},
 *      "pay":  [[[3,3],[1,4]], [[4,1],[2,2]]],   // pay[satır][sütun] = [satır oyuncusu, sütun oyuncusu]
 *      "mode": "static" | "nash",                  // nash: kullanıcı dengeleri işaretler ve kontrol eder
 *      "caption": "..."
 *    }
 *
 * 3) Doğruluk tablosu — <div class="truth-table" data-tt='{...}'></div>
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
 * 4) Diyagram — elle yazılmış <svg class="diagram"> (biçim style.css'te "Diyagram" başlığında).
 *    Bu dosya ok başlarını (#dg-arrow, #dg-arrow-dim) sayfaya bir kez ekler.
 *
 * 5) Matematik (isteğe bağlı) — ders <head>'inde assets/vendor/katex dosyaları yüklüyse \( … \),
 *    \[ … \] ve $$ … $$ işlenir (geri bildirim metinleri dahil). Yüklü değilse metin olduğu gibi kalır.
 *
 * 6) Ders modu (tools/lesson-template.html'deki iskelet; hepsi isteğe bağlı, yoksa sessizce atlanır):
 *    - Tema: ?theme=light|dark ya da localStorage "teach-theme" (panoyla aynı anahtar) <html data-theme>'i
 *      sayfa çizilmeden ayarlar; .theme-btn tıklanınca açık/koyu değişir (window.teachToggleTheme).
 *    - Adımlar: <section class="step" [data-title="Kısa ad"]><h2>…</h2> … </section>. JS her h2'nin üstüne
 *      "ADIM i" yazar, .lesson-bar .lb-step çipini "ADIM 3 · Başlık" olarak kaydırdıkça günceller
 *      (IntersectionObserver), .lb-progress i çizgisini kaydırma oranına göre doldurur ve [data-step-count]
 *      / [data-check-count] öğelerine sayıları yazar; hedef kartında bu sayılar gizlenir (çip tekrarı).
 *    - Harita yuvası: <div class="lmap-slot" data-track data-nodes="a,b" data-current="a"> içine
 *      `tools/learn lesson-map` çıktısı (<svg class="lmap">) yapıştırılır. SVG yoksa JS düğümleri sade
 *      çiplerle gösterir. SVG'yi `tools/learn refresh` doldurur (sarı yalnızca konunun sıradaki düğümü).
 *    - Sonuç çubuğu: data-card'lı ilk soru cevaplanınca alttan yapışkan .result-bar çıkar:
 *      "3 sorudan 2'si cevaplandı · kopyala, sohbete yapıştır" + sonuç satırı + Kopyala. Bütün
 *      data-card'lı sorular bitince aynı satır sayfa sonundaki .score içinde de görünür.
 *
 * 7) Panoya gömülü: pano dersi iframe'de "?embed=1&theme=…" ile açar. Ders bunu (ya da iframe içinde olduğunu)
 *    görünce <html class="embed"> olur: üst çubukta yalnız adım çipi ve ilerleme çizgisi kalır; tema panoyu
 *    izler; başka derse / referansa giden bağlantıları pano kendi sekmesinde / yan panelinde açar.
 *    Tek başına açılan ders eskisi gibi çalışır. Derslerde ayrıca bir şey yapmak gerekmez.
 *
 * Dikkat: data-* JSON'ları tek tırnakla yazılır; metindeki kesme işaretini &#39; olarak yaz ("Britanya&#39;nın").
 */
(function () {
  "use strict";
  var LETTERS = "ABCDEFGH";
  var CONF = [null, "Tahmin", "Emin değilim", "Eminim"]; // 1 / 2 / 3 → tools/learn --confidence

  // ---------- Sonuç satırı (saf işlevler; node ile test edilebilir) ----------
  function cleanWhy(t) {
    return String(t || "").replace(/\s+/g, " ").replace(/"/g, "'").trim().slice(0, 240);
  }
  // items: [{card: "gt-012", choice: "B" | "?", confidence: 1-3, why: "…"}]
  function formatResult(lesson, items) {
    return "ders sonucu " + lesson + ": " + items.map(function (it) {
      var s = it.card + "=" + it.choice + "/" + it.confidence, w = cleanWhy(it.why);
      return w ? s + ' "' + w + '"' : s;
    }).join("; ");
  }
  // Yeni ve eski biçimi okur → {lesson, format: "new"|"old", items: [{card, choice, confidence|null, why|null}]}
  function parseResult(line) {
    var m = /^\s*ders sonucu\s+([^\s:]+)\s*:\s*(.*)$/.exec(String(line));
    if (!m) return null;
    var re = /([^\s=;"]+)=([A-Za-z?])(?:\/([1-3]))?(?:\s+"([^"]*)")?/g, items = [], x, isNew = false;
    while ((x = re.exec(m[2]))) {
      if (x[3]) isNew = true;
      items.push({ card: x[1], choice: x[2].toUpperCase(), confidence: x[3] ? +x[3] : null, why: x[4] || null });
    }
    return { lesson: m[1], format: isNew ? "new" : "old", items: items };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { formatResult: formatResult, parseResult: parseResult, cleanWhy: cleanWhy };
  }
  if (typeof document === "undefined") return;
  window.teachLesson = { formatResult: formatResult, parseResult: parseResult };

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

  function lessonId() {
    var m = document.querySelector("main[data-lesson]");
    if (m) return m.dataset.lesson;
    var f = (location.pathname.split("/").pop() || "").replace(/\.html?$/, "");
    return f || "ders";
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

  // text: dize ya da o anki dizeyi döndüren işlev
  function copyButton(text) {
    var b = el("button", "btn", "Kopyala");
    b.type = "button";
    b.addEventListener("click", function () {
      markDirty(false);
      var t = typeof text === "function" ? text() : text;
      var done = function () { b.textContent = "Kopyalandı"; setTimeout(function () { b.textContent = "Kopyala"; }, 1500); };
      var select = function () { var r = document.createRange(); r.selectNodeContents(b.previousSibling); getSelection().removeAllRanges(); getSelection().addRange(r); done(); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(done, select);
      else select();
    });
    return b;
  }

  // ---------- Quiz ----------
  function initQuizzes() {
    var quizzes = Array.prototype.slice.call(document.querySelectorAll(".quiz"));
    var scoreEl = document.querySelector(".score");
    var answered = 0, correct = 0, results = {};
    var bound = quizzes.filter(function (q) { return !!q.dataset.card; });
    var bar = null;

    function boundItems() {
      var items = [];
      bound.forEach(function (quiz) { var r = results[quiz.dataset.card]; if (r) items.push(r); });
      return items;
    }

    // Yapışkan sonuç çubuğu: ilk data-card'lı cevaptan sonra görünür, her cevapta güncellenir.
    function renderBar() {
      var items = boundItems();
      if (!items.length) return;
      var line = formatResult(lessonId(), items);
      if (!bar) {
        bar = el("div", "result-bar");
        bar.setAttribute("role", "region");
        bar.setAttribute("aria-label", "Ders sonucu");
        var inner = el("div", "rb-inner");
        inner.appendChild(el("span", "rb-count"));
        inner.appendChild(el("code"));
        inner.appendChild(copyButton(function () { return bar.dataset.line; }));
        bar.appendChild(inner);
        document.body.appendChild(bar);
        document.body.classList.add("has-result-bar");
        requestAnimationFrame(function () { requestAnimationFrame(function () { bar.classList.add("show"); }); });
      }
      bar.dataset.line = line;
      var cnt = bar.querySelector(".rb-count");
      cnt.textContent = "";
      cnt.appendChild(el("b", null, bound.length + " sorudan " + trPoss(items.length) + " cevaplandı"));
      cnt.appendChild(document.createTextNode(" · kopyala, sohbete yapıştır"));
      var code = bar.querySelector("code");
      code.textContent = line; code.title = line;
    }

    function renderScore() {
      renderBar();
      if (!scoreEl) return;
      scoreEl.textContent = ""; // puan gösterilmez; yalnızca sohbete taşınacak sonuç satırı
      var items = boundItems();
      if (!items.length || items.length < bound.length) return;
      var line = formatResult(lessonId(), items);
      var wrap = el("div", "result-line");
      wrap.appendChild(el("code", null, line));
      wrap.appendChild(copyButton(line));
      wrap.appendChild(el("span", "hint", "Sohbete yapıştır."));
      scoreEl.appendChild(wrap);
    }

    quizzes.forEach(function (quiz, qi) {
      var cardMode = !!quiz.dataset.card;
      var q = quiz.querySelector(".q");
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
        if (quiz.dataset.card) markDirty(true); // only recorded questions have a result line to carry over
        var all = quiz.querySelectorAll(".opt");
        Array.prototype.forEach.call(all, function (o) { o.disabled = true; });
        var ok = i === answer;
        if (i >= 0) opts[i].classList.add("selected", ok ? "correct" : "incorrect");
        if (opts[answer]) opts[answer].classList.add("correct");
        answered++; if (ok) correct++;
        if (fb) {
          fb.className = "feedback show " + (ok ? "ok" : "no");
          var rightWhy = opts[answer] ? opts[answer].dataset.why || "" : "";
          fb.textContent = i < 0
            ? "Bilmiyorum demek dürüst bir cevap. Doğru şık işaretlendi" + (rightWhy ? ": " + rightWhy : ".")
            : (ok ? "Doğru. " : "Değil. ") + (opts[i].dataset.why || "") + (!ok && rightWhy ? " — Doğru cevap: " + rightWhy : "");
          typeset(fb);
        }
        if (extra) extra(ok);
        renderScore();
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
      var confBox = el("div", "conf-opts");
      confBox.setAttribute("role", "radiogroup");
      var confBtns = [1, 2, 3].map(function (n) {
        var b = el("button", null, CONF[n]);
        b.type = "button"; b.setAttribute("role", "radio"); b.setAttribute("aria-checked", "false");
        b.addEventListener("click", function () { conf = n; update(); });
        confBox.appendChild(b);
        return b;
      });
      confRow.appendChild(confBox);
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
        confBtns.forEach(function (b, k) {
          b.disabled = isDk;
          b.setAttribute("aria-checked", !isDk && conf === k + 1 ? "true" : "false");
        });
        go.disabled = !ready();
        hint.textContent = sel === null ? "Önce bir şık, sonra eminlik seç." : (ready() ? "Hazırsan cevapla." : "Ne kadar emin olduğunu seç.");
      }
      function submit() {
        if (!ready()) return;
        var c = sel === -1 ? 1 : conf, w = cleanWhy(why.value);
        results[quiz.dataset.card] = { card: quiz.dataset.card, choice: sel === -1 ? "?" : LETTERS[sel], confidence: c, why: w };
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
    renderScore();
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
    var checks = document.querySelectorAll(".quiz[data-card]").length;
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
    initMatrices();
    initTruthTables();
    initDiagrams();
    initLessonMap();
    initSteps();
    initEmbed();
    typeset(document.querySelector("main") || document.body);
  });
})();
