# ChangeMesh — Türkçe Proje Özeti

> **Her kritik değişikliği önce prova et. Yalnızca kanıtlanmış ajanlara güven. Kanıtla yürüt.**

ChangeMesh; kod, veri, güvenlik, uyumluluk ve operasyon sınırlarını aşan uzun süreli kurumsal değişiklikleri otonom biçimde yürüten, fakat geri döndürülemez yetki sınırlarında yalnızca gerekli insan kararını isteyen bir ajan filosudur.

## Durum

Bu repo başlangıç aşamasındadır. Şu anda ürün anayasası, mimari sınırlar, canlı yönetişim dosyaları ve ayrıntılı geliştirme planı hazırlanmıştır. Gerçek kanıt olmadan hiçbir özellik tamamlanmış gösterilemez.

## Temel fikir

**Keşfet → Yeterliliği doğrula → Prova et → Güvenilir hafızayla temellendir → Yetkilendir → Yürüt → Kanıtla → Sertifikalandır**

## Otonomluk yaklaşımı

Sistem ağırlıklı olarak `human-on-the-loop` tasarlanır. Ajanlar analizi, planı, güvenli migration’ı, testleri, hata senaryolarını, otomatik düzeltmeyi, branch/draft PR hazırlığını ve kanıt toplamayı kendi yapar. İnsan yalnızca şirket adına yetki kullanılması gereken en küçük karar kümesinde çağrılır.

## Bağlayıcı plan

Tüm geliştirme adımları için tek resmi kaynak:

[`plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`](plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md)

Mülakat fazı kaldırılmıştır; proje mutabakatı dondurulmuştur. Ancak canlı hafıza, mimari, devir, kanıt ve bütün-repo tutarlılık kontrolleri pazarlık edilemez.
