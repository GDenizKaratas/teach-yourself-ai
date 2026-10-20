# Buradan başla 👋

Bu klasör senin kişisel öğretmenin. Öğretmen, VS Code'un içindeki Claude. Hiçbir şey bilmeden başlayabilirsin.

## Her gün yapacağın tek şey

1. Bu klasörü VS Code'da aç.
2. Claude panelini aç: sağ üstteki Claude simgesine tıkla.
3. **Yeni bir sohbet başlat** (panelin üstündeki yeni sohbet / New Chat düğmesi) ve yaz: **"Merhaba, devam edelim"**

Claude nerede kaldığını kendisi hatırlar ve kısa bir tekrarla başlar. Her gün yeni sohbet aç. Dünkü sohbete devam edersen Claude bugünün tekrar sorularını göremez.

**Vaktin az mı?** 5 dakikalık bir gün de sayılır: "bugün 5 dakikam var" yaz, Claude sadece 2–3 tekrar sorusu sorar. Kısa ama düzenli, uzun ama ara sıradan iyidir.

**Claude izin isterse** (bir komut çalıştırmak ya da bir dosyayı değiştirmek için): bu klasördeki işler için **izin ver** (Allow / Yes). Emin değilsen önce "bu ne işe yarıyor?" diye sor.

## Ders sırasında

- **Sorular açılır pencerede gelir.** Bir şıkka tıkla. Bilmiyorsan **"Bilmiyorum"** şıkkını seç. Bu da işe yarayan bir cevap; tahmin etmekten iyidir. Bazen Claude "Neden?" diye sorar: tek satır yazman yeter.
- **Yanlış cevap sorun değil.** Hangi şıkkı seçtiğin, Claude'a tam olarak neyi anlatması gerektiğini gösterir.
- **Kodu sen yazarsın.** Claude ipucu verir, kodu senin yerine yazmaz. Kalıcı öğrenme böyle oluyor.
- Bir şey anlamadıysan: **"anlamadım"** yaz. Claude bir adım geri gider.
- Bir şey yapamadıysan: **"ipucu"** yaz.

## İşine yarayacak cümleler

| Ne istiyorsun | Ne yaz |
|---|---|
| Kaldığın yerden devam etmek | devam edelim |
| Tekrar soruları | tekrar yapalım |
| Pratik yapmak | bana bir görev ver |
| Kodunu kontrol ettirmek | kontrol et |
| Takıldığında | ipucu |
| Özet / kopya kağıdı | cheatsheet çıkaralım |
| İlerlemeni tek sayfada görmek | pano |
| Bitirmek | bugünlük bu kadar |

## Pano

**"pano"** yaz: Claude ilerlemeni gösteren sayfayı açar (haritan, sıradaki konu, derslerin, notların). Açılmazsa `learner/dashboard.html` dosyasını tarayıcıda aç. Sayfa sadece gösterir; dersler yine burada, sohbette.

## Ders sayfaları

Bazı konular için Claude sana okunacak kısa bir **ders sayfası** hazırlar: `tracks/<konu>/lessons/` içinde `.html` dosyaları. Claude sayfayı tarayıcıda **kendisi açar**. Açılmazsa Claude'un verdiği bağlantıya tıkla, ya da dosyaya sağ tıkla → "Reveal in Finder" (Mac) / "Reveal in File Explorer" (Windows), sonra çift tıklayıp tarayıcıda aç. Sayfanın sonunda kısa sorular var; hepsini cevaplayınca çıkan **"ders sonucu …" satırını kopyalayıp sohbete yapıştır**. Böylece Claude neyi bildiğini, neyi karıştırdığını görür. Kaynaklar ve "birincil kaynak" bağlantıları, istersen daha derine inmen için.

## Dosyalar nerede?

- `tracks/`: öğrendiğin konular. Her konunun haritası (`map.md`), özeti (`cheatsheet.md`), sözlüğü (`glossary.md`), görevleri (`tasks/`), ders sayfaları (`lessons/`) ve başvuru sayfaları (`reference/`) burada.
- `workspace/`: senin deneme alanın. İstediğini yaz, istediğini boz.
- Bir `.md` dosyasını güzel görmek için dosyayı aç ve şu tuşlara bas: Mac'te `Cmd+Shift+V`, Windows'ta `Ctrl+Shift+V`.

## Yazmak yerine konuşmak (isteğe bağlı)

Yazmak yorarsa bilgisayarının dikte özelliğiyle konuşarak yazabilirsin: Mac'te **Dikte** (Sistem Ayarları → Klavye → Dikte; açınca kısayola bas), Windows'ta **Win+H**. Gönder'e basmadan önce yazılanı bir göz at.

## Kısayollar

| Ne | Mac | Windows |
|---|---|---|
| `.md` dosyasını güzel görüntüle | `Cmd+Shift+V` | `Ctrl+Shift+V` |
| Dosyayı kaydet | `Cmd+S` | `Ctrl+S` |
| Terminali aç / kapat | ``Ctrl+` `` | ``Ctrl+` `` |
| Komut paleti (her şeyi aratır) | `Cmd+Shift+P` | `Ctrl+Shift+P` |
| Dosya ara ve aç | `Cmd+P` | `Ctrl+P` |
| Geri al | `Cmd+Z` | `Ctrl+Z` |
