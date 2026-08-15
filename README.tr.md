# ChangeMesh — Türkçe Proje Özeti

> **Her kritik değişikliği önce prova et. Yalnızca kanıtlanmış ajanlara güven. Kanıtla yürüt.**

ChangeMesh; kod, veri, güvenlik, uyumluluk ve operasyon sınırlarını aşan uzun süreli kurumsal değişiklikleri otonom biçimde yürüten, fakat geri döndürülemez yetki sınırlarında yalnızca gerekli insan kararını isteyen bir ajan filosudur.

## Durum

Bu repo uygulama öncesi / yarışma inşa aşamasındadır:

- **Mimari temeli (P-04):** `IMPLEMENTED` (`DONE`)
- **Domain kontratları ve makine kuralları (P-05.01–P-05.06):** `IMPLEMENTED` (`DONE`)
- **Çalışma zamanı sürümü ve repo yapısı (P-06.01):** `IMPLEMENTED` (`DONE` — Python `3.13.5` `.python-version` ile sabitlendi, Node `NOT_REQUIRED`)
- **Tekrarlanabilir bağımlılık bildirimleri ve kilit dosyaları (P-06.02):** `IMPLEMENTED` (`DONE` — PEP 621 / PEP 735 `pyproject.toml`, `[tool.uv]` sürüm zorunluluğu, `uv.lock`, çalışma zamanı `requirements.txt`, geliştirme/test `requirements-dev.txt`)
- **P-06 Yerel Geliştirme Ortamı ve Bağımlılık Dondurma Fazı:** `IN_PROGRESS` (P-06.03 yapılandırma şablonları, P-06.04 standart komutlar ve P-06.05 temiz klon doğrulaması `PENDING` durumundadır)
- **Çalışma zamanı ürün ve ajan geliştirmesi:** P-07+ aşamasında başlayacaktır (`PLANNED`).

Gerçek kanıt olmadan hiçbir özellik tamamlanmış gösterilemez (`PLANNED`, `IN_PROGRESS`, `PASS`, `FAIL`, `NOT_RUN`, `SIMULATED`, `BLOCKED`, `QUARANTINED`).

## Kurulum ve Yeniden Üretilebilirlik

P-06.02 kapsamında hem çalışma zamanı hem de geliştirme/test bağımlılık kurulumu, kanonik çalışma kopyasında taze ve izole Python 3.13.5 sanal ortamlarında başarıyla doğrulanmıştır (`VERIFIED`).

Ayrı bir dizinden temiz klon ile yeniden üretilebilirlik henüz çalıştırılmamıştır (`NOT_RUN`). İlk temiz klon kurulumunun yapılması ve kanıtlanması münhasıran P-06.05 (`PENDING`) görevine aittir.

Standart geliştirici komut akışı ve eksiksiz kurulum dokümantasyonu P-06.04 ile P-06.05 fazlarına aittir ve temiz klon doğrulaması tamamlandıktan sonra yayımlanacaktır.

## Temel fikir

**Keşfet → Yeterliliği doğrula → Prova et → Güvenilir hafızayla temellendir → Yetkilendir → Yürüt → Kanıtla → Sertifikalandır**

## Otonomluk yaklaşımı

Sistem ağırlıklı olarak `human-on-the-loop` tasarlanır. Ajanlar analizi, planı, güvenli migration’ı, testleri, hata senaryolarını, otomatik düzeltmeyi, branch/draft PR hazırlığını ve kanıt toplamayı kendi yapar. İnsan yalnızca şirket adına yetki kullanılması gereken en küçük karar kümesinde çağrılır.

## Bağlayıcı plan

Tüm geliştirme adımları için tek resmi kaynak:

[`plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`](plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md)

Mülakat fazı kaldırılmıştır; proje mutabakatı dondurulmuştur. Ancak canlı hafıza, mimari, devir, kanıt ve bütün-repo tutarlılık kontrolleri pazarlık edilemez.
