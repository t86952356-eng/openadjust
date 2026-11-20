# OpenAdjust v1.0 — Android Client Version (1.8.9)

نسخة **OpenAdjust** (استعادة مصدر Java كاملة لعميل **Adjust** على ماين كرافت
1.8.9 — 102 موديول + 29 أمر + OptiFine + قوائم وواجهات كاملة) معدّة لتعمل على
**أندرويد** عبر **Fold Craft Launcher (FCL)** بنظام **Client Version** مستقل.

- الملفات: `OpenAdjust-Android-v1.0.jar` (العميل الكامل) +
  `OpenAdjust-Android-v1.0.json` (ملف الإصدار) + `android-package-report.json`
  (تقرير التغليف).
- المصدر: https://github.com/t86952356-eng/openadjust

## لماذا هذا العميل يعمل بالكامل (عكس حالات سابقة)

| | OpenAugustus (توقف عند نواة محمية) | OpenAdjust |
|---|---|---|
| طبيعة الكود | نواة JNIC native لويندوز x64 فقط | **Java خالص 100%** — لا حماية native إطلاقاً |
| الواجهة (ClickGUI/HUD) | Java | Java فوق **NanoVG** — وFCL يدعم NanoVG في منفذه الرسمي |
| النتيجة | جدار بنيوي | **لا يوجد أي جدار** |

بنية التشغيل على الجهاز (محددة من كود FCL نفسه ومتحقق منها في CI):

- ملف JSON يعلن `org.lwjgl:lwjgl:3.3.3` → FCL يختار منفذه المدمج **LWJGL 3.3.3
  لأندرويد** (كلاسات + natives لـ arm64) والذي يشمل: **NanoVG** (واجهة العميل
  كلها مبنية عليها) + GLFW + OpenGL + OpenAL + STB.
- بدون `lwjglx`: كلاسات `org.lwjgl.*` الخاصة بالعميل (جسور Display/Keyboard/Mouse
  المستعادة من المصدر) تبقى الوحيدة على الكلاسباث — صفر تعارض.
- FCL يجهّز تلقائياً **native مكتبة JNA لأندرويد** (AAR رسمي) لأن JSON يعلن
  `jna:5.15.0`.
- CI بروب ثلاثي المراحل يثبت: سلامة بنية الجار + ارتباط كل السلاسل الحرجة
  بترتيب كلاسباث FCL حرفياً + إقلاع `net.minecraft.client.main.Main` بنجاح
  حتى نقطة تحميل native بالضبط (`Main → ClientBootstrap → GameSettings →
  OptiFine → Display → liblwjgl.so`) — وهي النقطة التي يتكفل بها FCL على
  الجهاز.

## الميزات غير المتاحة على أندرويد (1 فقط)

- **Voice Chat**: مكتبات Opus وRNNoise native غير موجودة لأندرويد. الكود الأصلي
  محروس بالكامل بـ `try/catch` — الموديول يتعطل بأمان مع رسالة في السجل بدل
  الكراش. كل الموديولات الـ 101 الأخرى والـ HUD والـ ClickGUI **بدون أي تعديل**.

## التثبيت على FCL (Fold Craft Launcher)

1. حمّل `OpenAdjust-Android-v1.0.jar` و `OpenAdjust-Android-v1.0.json`.
2. في مجلد FCL: `files/.minecraft/versions/OpenAdjust-Android-v1.0/`
   (أو مسار اللعبة الظاهر في إعدادات FCL)
   - ضع الملفين بنفس الاسم:
     - `versions/OpenAdjust-Android-v1.0/OpenAdjust-Android-v1.0.jar`
     - `versions/OpenAdjust-Android-v1.0/OpenAdjust-Android-v1.0.json`
3. شغّل FCL ← الإصدارات ← اختر **OpenAdjust-Android-v1.0**.
   - FCL سينزّل أصول Minecraft 1.8.9 الرسمية تلقائياً (assets 1.8) في أول تشغيل.
4. **Java: اختر `Auto` أو `jre21`** (العميل مبني على Java 21 — الـ JSON يطلبها).
5. العارض: **GL4ES** أو **Holy-GL4ES** أو **Krypton/NG-GL4ES** — كلها مدعومة.

### ملاحظات تشغيل

- واجهة العميل (ClickGUI، HUD، الخطوط، الرادار) تستخدم NanoVG عبر الـ runtime
  الرسمي لـ FCL — مع تدرّج تلقائي GL3→GL2 حسب قدرات الجهاز (من كود العميل
  نفسه).
- الصوت يعمل عبر OpenAL من منفذ FCL (نفس آلية ماين كرافت الحديثة).
- إن ظهرت أي مشكلة عرض جرّب تبديل العارض بين GL4ES وKrypton.

## التغليف والتقنية

- المصدر بُني كما هو (صفر تعديل على كود العميل) بـ Gradle + JDK 21 ثم دُمج في
  جار واحد مستقل مع:
  - **حذف**: كل ملفات natives ويندوز + `opus.dll` + signatures + multi-release
    (توفرها FCL لأندرويد أو لا تلزم).
  - **إبقاء**: كل كلاسات العميل وMC 1.8.9 المستعاد + المكتبات كاملة
    (fastutil, JTS, JOML, Netty, Guava, log4j, OSHI, JNA classes, lwjgl-opus
    bindings…).
- 150.3MB (غير مضغوط) → **75.7MB** مضغوط.

---

# English summary

OpenAdjust (full Java source restoration of the Adjust client for Minecraft
1.8.9 — 102 modules, 29 commands, OptiFine) packaged as a standalone **Client
Version** for **Fold Craft Launcher** on Android.

The version JSON declares `org.lwjgl:lwjgl:3.3.3`, so FCL selects its built-in
LWJGL 3.3.3 Android runtime (which includes **NanoVG** — the entire client
UI stack depends on it) and skips the `lwjglx` LWJGL2 shim: the client's own
source-restored `org.lwjgl.*` bridges stay the only ones on the classpath.
FCL also provisions the Android JNA native from the declared `jna:5.15.0`.
A three-stage CI probe verifies jar structure, class linkage with the exact
FCL classpath order, and a headless boot of `net.minecraft.client.main.Main`
all the way to the LWJGL native boundary — the point where FCL takes over on
device. Voice Chat is the only unavailable feature (no Android Opus/RNNoise
natives; the upstream code already guards it and degrades safely). Zero
client-code modifications were needed. Size: 75.7 MB.
