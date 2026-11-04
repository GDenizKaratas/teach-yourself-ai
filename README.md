<p align="center"><img src="assets/logo.svg" width="72" alt=""></p>

<h1 align="center">teach</h1>

<p align="center">Claude Code içinde çalışan kişisel öğretmen.<br>Ne öğrenmek istediğini söylersin; sana özel bir yol çizer ve adım adım öğretir.</p>

<p align="center"><img src="docs/img/pano.png" alt="Pano: bütün konuların kavram ağı, ne kadarının taze kaldığı, çalışma takvimi ve son çalışmalar"></p>

## Nasıl çalışır

- **Önce hedefini sorar.** Birkaç soruyla asıl amacını bulur ve sana uygun dersi önerir.
- **Ezberletmez, anlatır.** Temelden başlar, her seferinde tek adım ilerler. Cevaplarından seni tanır.
- **Önce bütün resim, sonra parçalar.** Her konu puansız bir harita sayfasıyla açılır; seviyeni ölçtükten sonra gün ona göre şekillenir: yeni başlayana çözümlü örnek → yarım örnek → kendin yap, bilene kısa sayfa → birkaç soru → gerçek bir vaka.
- **Sayfada çalışırsın, sohbette derinleşirsin.** Ders sayfasındaki sorular, yazı kutuları ve "sormak istediğim" kutusu tek düğmeyle sohbete gelir. Claude emin olup yanlış bildiğin yerlerden başlar, yazdıklarını değerlendirir, sorularını cevaplar; cevabı sana vermez, ipuçlarıyla kendin bulursun.
- **Unutturmaz.** Doğru bildiğin de başka bir gün tekrar sorulur; konular karışık gelir, konu adı yazmaz. Kalıcı öğrenme böyle oluyor.
- **Seni tanır.** Sana nasıl sesleneceğini, kararlarını, hayatında olup biteni bilir; her oturum üç satırla başlar: neredeyiz, hangi yöne, sıradaki ne.
- **İlerlemeni gösterir.** Haritan, notların ve derslerin tek bir panoda durur; her sayfada nerede olduğunun çizimi var.

<p align="center"><img src="docs/img/harita.png" alt="Bir konunun haritası: temelden hedefe adımlar, sıradaki adım sarı, yanında notlar ve dokümanlar"></p>

## Kurulum

1. [VS Code](https://code.visualstudio.com/) ve **Claude Code** eklentisini kur. Claude Code için ücretli bir Claude planı gerekir. Windows'ta [Git](https://git-scm.com/download/win) de kur.
2. Bu repoyu indir: `git clone https://github.com/GDenizKaratas/teach-yourself-ai.git`
3. Klasörü VS Code'da aç. Claude panelinde yeni bir sohbet başlatıp **"başla"** yaz.

Python kurulumu dahil gerisini ilk sohbette birlikte yaparsınız. Adım adım kontrol listesi: [KURULUM.md](KURULUM.md).

## Bilmen gerekenler

- Verilerin yalnızca senin bilgisayarında, `learner/` ve `tracks/` klasörlerinde durur. Git'e gönderilmez.
- Panoyu açmak için: `learner/dashboard.html`. Bir kez yer imine eklersen tek tıkla açılır.
- Bırakmak için "bugünlük bu kadar" yazman yeterli. Bir sonraki sefer kaldığın yerden devam eder.

<sub>Başka bir yapay zekâ ajanıyla kullanmak için: [AGENTS.md](AGENTS.md). Sistemin nasıl kurulduğu: [docs/engine.md](docs/engine.md).</sub>

<sub>MIT lisansı: [LICENSE](LICENSE).</sub>
