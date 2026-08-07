# ChangeMesh — Türkçe Proje Özeti

> **Her kritik değişikliği önce prova et. Yalnızca kanıtlanmış ajanlara güven. Kanıtla yürüt.**

**ChangeMesh**, yüksek riskli kurumsal mimari değişikliklerini güvenle prova eden ve yürüten, kural-yönetimli (policy-governed) bir ajan filosudur. Kurumsal bir değişikliği bir sohbet oturumu olarak değil, uzun ömürlü dağıtık bir işlem (transaction) olarak ele alır. Google Agent Development Kit ve Gemini kullanarak bağımlılıkları keşfeder, gölge ortamda provalar yapar ve haftalar sürecek manuel koordinasyon sürecini tek bir kriptografik Değişim Kanıt Pasaportuna (Change Evidence Passport) dönüştürür.

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
