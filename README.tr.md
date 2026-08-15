# ChangeMesh — Türkçe Proje Özeti

> **Her kritik değişikliği önce prova et. Yalnızca kanıtlanmış ajanlara güven. Kanıtla yürüt.**

ChangeMesh; kod, veri, güvenlik, uyumluluk ve operasyon sınırlarını aşan uzun süreli kurumsal değişiklikleri otonom biçimde yürüten, fakat geri döndürülemez yetki sınırlarında yalnızca gerekli insan kararını isteyen bir ajan filosudur.

## Durum

Bu repo geliştirme aşamasında bir yarışma projesidir:

- **Mimari temeli (P-04):** `IMPLEMENTED` (`DONE`)
- **Domain kontratları ve makine kuralları (P-05.01–P-05.06):** `IMPLEMENTED` (`DONE`)
- **Çalışma zamanı sürümü ve repo yapısı (P-06.01):** `IMPLEMENTED` (`DONE` — Python `3.13.5` `.python-version` ile sabitlendi, Node `NOT_REQUIRED`)
- **Tekrarlanabilir bağımlılık bildirimleri ve kilit dosyaları (P-06.02):** `IMPLEMENTED` (`DONE` — PEP 621 / PEP 735 `pyproject.toml`, `[tool.uv]` sürüm zorunluluğu, `uv.lock`, çalışma zamanı `requirements.txt`, geliştirme/test `requirements-dev.txt`)
- **Güvenli yerel yapılandırma şablonu ve sır yönetimi (P-06.03):** `IMPLEMENTED` (`DONE` — varsayılan sır içermeyen `.env.example` şablonu, ADC öncelikli kimlik doğrulama, kapsamlı `.gitignore` koruması, 14 yapılandırma güvenlik testi)
- **Kanonik komut arayüzü (P-06.04):** `IMPLEMENTED` (`DONE` — `scripts/cmd.py`, format, lint, type-check, unit, integration, e2e, demo, deploy, teardown komutları sıkı güvenlik sınırları ile tanımlandı)
- **P-06 Yerel Geliştirme Ortamı ve Bağımlılık Dondurma Fazı:** `IMPLEMENTED` (`DONE` — P-06.01–P-06.05 tamamlandı; ayrı dizinden temiz klon doğrulaması [`docs/P-06.05_CLEAN_CHECKOUT_LOG.md`](docs/P-06.05_CLEAN_CHECKOUT_LOG.md) ile kanıtlandı)
- **P-07 Google ADK Ajan İskeleti ve Filosu Fazı:** `IN_PROGRESS` (P-07.01 Değişiklik Orkestratörü ADK iskeleti, P-07.02 altı uzmanlaşmış ADK ajan tanımı ile sınırlandırılmış araç/talimat kontratları, P-07.03 deterministik yerel yönlendirme/delege etme ve P-07.04 çoklu ajan koordinasyonu/ardışık yedek `IMPLEMENTED`; P-07.05 `PENDING`)
- **Çalışma zamanı ürün ve ajan filosu geliştirmesi:** P-07 aşamasında devam etmektedir (`IN_PROGRESS`). Değişiklik Orkestratörü iskeleti (P-07.01), uzmanlaşmış ajan filosu tanımları (P-07.02), deterministik yerel yönlendirme/delege etme (P-07.03) ve çoklu ajan koordinasyonu/ardışık yedek (P-07.04) `IMPLEMENTED`; ajan revizyon üstverisi (P-07.05) ve Gemini yapılandırılmış akıl yürütme (P-08) `PENDING` durumundadır. Bulut dağıtımı, kalıcılık ve P-12 Ajan Kayıt Defteri / Yetenek Pasaportu çalışma zamanı henüz uygulanmamıştır / `PLANNED` durumundadır.

Gerçek kanıt olmadan hiçbir özellik tamamlanmış gösterilemez (`PLANNED`, `IN_PROGRESS`, `PASS`, `FAIL`, `NOT_RUN`, `SIMULATED`, `BLOCKED`, `QUARANTINED`).

## Kurulum ve Temiz Klon Doğrulaması

Kanonik çalışma kopyası dışındaki ayrı bir dizinden temiz klon ile yeniden üretilebilirlik P-06.05 kapsamında tam sadakatle doğrulanmıştır ([`docs/P-06.05_CLEAN_CHECKOUT_LOG.md`](docs/P-06.05_CLEAN_CHECKOUT_LOG.md)).

### Önkoşullar

- **Python:** `3.13.5` (`uv` veya sistem CPython 3.13.5 ile yönetilir, `.python-version` içinde sabitlenmiştir)
- **uv:** `0.11.28` (`pyproject.toml` `[tool.uv] required-version` içinde sabitlenmiştir)
- **Git**

> **Test Edilen Ortam:** Windows 11 x86_64, PowerShell 7, CPython 3.13.5, uv 0.11.28, Git 2.52.0.

### Hızlı Başlangıç (Geliştirme / Test Ortamı)

1. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/zyganali-glitch/ChangeMesh.git
   cd ChangeMesh
   ```

2. **Bağımlılıkları senkronize edin (deterministik dondurulmuş kurulum):**
   ```bash
   uv sync --frozen
   ```

3. **Bağımlılık uyumluluğunu doğrulayın:**
   ```bash
   uv pip check
   ```

4. **Birim testleri çalıştırın:**
   ```bash
   uv run python scripts/cmd.py unit
   ```
   *(P-05 domain kontratları, P-06.03 yapılandırma güvenliği, P-06.04 komut kontratları, P-07.01 Değişiklik Orkestratörü ADK iskeleti, P-07.02 uzmanlaşmış ajan tanımları, P-07.03 deterministik yönlendirme ve P-07.04 çoklu ajan koordinasyonunu kapsayan 788 testin tamamını 0 çıkış koduyla çalıştırır).*

### Yapılandırma ve Kimlik Doğrulama Sınırı

- **`.env` gereksizdir:** Yerel birim testleri, şema doğrulamaları ve komut denetimleri `.env` veya bulut sırrı gerektirmez.
- **Güvenli şablon:** `.env.example`, sıfır varsayılan sır içeren kanonik ortam değişkeni yapısını sunar.
- **Google Cloud Kimlik Doğrulaması:** Application Default Credentials (`gcloud auth application-default login`), yalnızca ilerleyen fazlarda açıkça yetkilendirilmiş canlı Google Cloud işlemleri çalıştırılırken gereklidir.
- **Servis Hesabı Anahtarları:** Servis hesabı JSON anahtar dosyaları yasaktır ve `.gitignore` tarafından yok sayılır.

### Kanonik Komutlar ve Temel Hat Durum Tablosu

| Komut | Eylem | Denetim Semantiği | Temel Hat Sonucu |
|---|---|---|---|
| `uv run python scripts/cmd.py unit` | Birim testleri çalıştır | Yerel deterministik test çalıştırma | `PASS` (788 geçti) |
| `uv run python scripts/cmd.py format` | Format denetimi | Değişiklik yapmayan (`ruff format --check .`) | `FAIL` (tarihsel format borcu) |
| `uv run python scripts/cmd.py lint` | Lint denetimi | Değişiklik yapmayan (`ruff check .`, sıfır `--fix`) | `FAIL` (tarihsel lint borcu) |
| `uv run python scripts/cmd.py type-check` | Tip denetimi | Değişiklik yapmayan (`mypy domain tests`) | `FAIL` (`test_gcp_access.py` tarihsel tip borcu) |
| `uv run python scripts/cmd.py integration` | Entegrasyon testleri | Varsayılan olarak kapalı başarısız; sıfır bulut çağrısı | `FAIL_CLOSED` (`--live-write-danger` gerektirir) |
| `uv run python scripts/cmd.py e2e\|demo\|deploy\|teardown` | Ertelenmiş eylemler | Kapalı başarısız; `NOT_RUN` basar | `NOT_RUN` (sahip fazlar bekleniyor) |

## Temel fikir

**Keşfet → Yeterliliği doğrula → Prova et → Güvenilir hafızayla temellendir → Yetkilendir → Yürüt → Kanıtla → Sertifikalandır**

## Otonomluk yaklaşımı

Sistem ağırlıklı olarak `human-on-the-loop` tasarlanır. Ajanlar analizi, planı, güvenli migration’ı, testleri, hata senaryolarını, otomatik düzeltmeyi, branch/draft PR hazırlığını ve kanıt toplamayı kendi yapar. İnsan yalnızca şirket adına yetki kullanılması gereken en küçük karar kümesinde çağrılır.

## Bağlayıcı plan

Tüm geliştirme adımları için tek resmi kaynak:

[`plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`](plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md)

Mülakat fazı kaldırılmıştır; proje mutabakatı dondurulmuştur. Ancak canlı hafıza, mimari, devir, kanıt ve bütün-repo tutarlılık kontrolleri pazarlık edilemez.
