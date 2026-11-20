import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * CI smoke test for the OpenAdjust Android build.
 *
 * Stage 1 - structural: the fat jar must be self-contained but must NOT
 * bundle the LWJGL 3 core modules (FCL replaces them with its own Android
 * runtime at launch, which also carries the nanovg/stb/openal natives the
 * client UI depends on), must contain no desktop native binaries, and must
 * carry the client's own source-restored LWJGL2-style bridges.
 *
 * Stage 2 - linkage battery: loads a representative set of classes with the
 * REAL LWJGL 3.3.3 jars first on the classpath and the fat jar last - the
 * exact classpath order FCL uses - proving the whole chain links against
 * the launcher-provided LWJGL.
 *
 * Stage 3 - boot to the native boundary: launches net.minecraft.client.main.Main
 * headlessly (same args FCL passes). Without any natives on the CI classpath
 * the boot must fail EXACTLY at the LWJGL native-library boundary
 * (UnsatisfiedLinkError family). Any ClassNotFoundException /
 * NoClassDefFoundError / NoSuchMethodError / VerifyError means the packaging
 * broke something and fails the probe.
 *
 * Exit 0 + "PROBE-PASSED" = the Android jar is sound up to the GL boundary.
 */
public final class ProbeAdjust {

    private static int failures = 0;

    private static void check(boolean ok, String label) {
        System.out.println((ok ? "  [ok]   " : "  [FAIL] ") + label);
        if (!ok) failures++;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: ProbeAdjust <android-fat-jar> [boot classpath...]");
            System.exit(2);
        }
        File fat = new File(args[0]);
        List<String> bootCp = new ArrayList<>();
        for (int i = 1; i < args.length; i++) bootCp.add(args[i]);

        System.out.println("== ProbeAdjust: OpenAdjust Android jar smoke test ==");

        // ---------------- Stage 1: structure ----------------
        Set<String> names = new HashSet<>();
        String mainClass = null;
        boolean services = false;
        List<String> natives = new ArrayList<>();
        List<String> lwjglCore = new ArrayList<>();
        try (ZipFile zf = new ZipFile(fat)) {
            java.util.Enumeration<? extends ZipEntry> en = zf.entries();
            while (en.hasMoreElements()) {
                ZipEntry e = en.nextElement();
                String n = e.getName();
                if (e.isDirectory()) continue;
                names.add(n);
                String lower = n.toLowerCase(Locale.ROOT);
                if (lower.endsWith(".dll") || lower.endsWith(".so") || lower.endsWith(".jnilib")
                        || lower.endsWith(".dylib") || lower.endsWith(".a")) {
                    natives.add(n);
                }
                if (n.equals("META-INF/MANIFEST.MF")) {
                    String mf = new String(readAll(zf.getInputStream(e)), StandardCharsets.UTF_8);
                    for (String line : mf.split("\r?\n")) {
                        if (line.startsWith("Main-Class:")) mainClass = line.substring(11).trim();
                    }
                }
                if (n.startsWith("META-INF/services/")) services = true;
                if (n.startsWith("META-INF/versions/") || n.equals("module-info.class")
                        || n.endsWith("/module-info.class")) {
                    lwjglCore.add(n + "  (multi-release/module leftover)");
                }
                // LWJGL core modules must NOT be bundled (FCL provides them)
                if (n.startsWith("org/lwjgl/glfw/") || n.startsWith("org/lwjgl/nanovg/")
                        || n.startsWith("org/lwjgl/stb/") || n.startsWith("org/lwjgl/openal/")
                        || n.startsWith("org/lwjgl/system/") || n.startsWith("org/lwjgl/vulkan/")
                        || n.startsWith("org/lwjgl/freetype/") || n.startsWith("org/lwjgl/opengles/")
                        || n.startsWith("org/lwjgl/egl/")) {
                    lwjglCore.add(n);
                }
                // org/lwjgl top level: only the restored bridge classes may exist
                if (n.startsWith("org/lwjgl/") && n.indexOf('/', 10) < 0 && n.endsWith(".class")) {
                    String cls = n.substring(10, n.length() - 6);
                    if (!cls.equals("Sys") && !cls.equals("LWJGLException")
                            && !cls.startsWith("LWJGLException$")) {
                        lwjglCore.add(n + "  (unexpected top-level org.lwjgl class)");
                    }
                }
                // org/lwjgl/opengl: only the bridge set (no GL11 etc.)
                if (n.startsWith("org/lwjgl/opengl/") && n.endsWith(".class")) {
                    String cls = n.substring("org/lwjgl/opengl/".length(), n.length() - 6);
                    String base = cls.contains("$") ? cls.substring(0, cls.indexOf('$')) : cls;
                    if (!Arrays.asList("Display", "DisplayMode", "GLContext", "ContextAttribs",
                            "ContextCapabilities", "PixelFormat", "PixelFormatLWJGL",
                            "OpenGLException", "Util", "Drawable").contains(base)) {
                        lwjglCore.add(n + "  (non-bridge org.lwjgl.opengl class)");
                    }
                }
            }
        }

        check(fat.isFile() && fat.length() > 10_000_000L,
                "fat jar exists (" + (fat.length() / 1_000_000) + " MB)");
        check("net.minecraft.client.main.Main".equals(mainClass),
                "manifest Main-Class = " + mainClass);
        check(natives.isEmpty(), "no desktop native binaries bundled (found " + natives.size() + ")");
        check(lwjglCore.isEmpty(), "no LWJGL core / multi-release leftovers (found "
                + lwjglCore.size() + (lwjglCore.isEmpty() ? "" : " e.g. " + lwjglCore.get(0)) + ")");
        check(services, "META-INF/services merged");

        String[] required = {
                "net/minecraft/client/main/Main.class",
                "net/minecraft/client/Minecraft.class",
                "com/adjustclient/Adjust.class",
                "com/adjustclient/render/font/NvgContext.class",
                "com/adjustclient/render/font/Fonts.class",
                "com/adjustclient/module/impl/player/voicechat/audio/MicrophoneWorker.class",
                "com/adjustclient/module/impl/player/voicechat/playback/AudioStream.class",
                "com/adjustclient/audio/opus/OpusCodec.class",
                "com/adjustclient/audio/openal/AlContext.class",
                "org/lwjgl/util/opus/Opus.class",
                "org/lwjgl/opengl/Display.class",
                "org/lwjgl/input/Keyboard.class",
                "org/lwjgl/input/Mouse.class",
                "paulscode/sound/libraries/LibraryLWJGLOpenAL.class",
                "assets/adjust/sounds.json",
                "pack.png",
                "log4j2.xml",
                "yggdrasil_session_pubkey.der",
        };
        for (String r : required) {
            check(names.contains(r), "required entry present: " + r);
        }
        check(names.stream().anyMatch(n -> n.startsWith("assets/minecraft/")),
                "assets/minecraft resources bundled");
        check(names.stream().anyMatch(n -> n.startsWith("assets/adjust/")),
                "assets/adjust resources bundled");
        check(!names.contains("assets/adjust/natives/opus.dll"), "opus.dll stripped");

        // ---------------- Stage 2: linkage battery ----------------
        System.out.println("== Stage 2: class linkage battery (FCL classpath order) ==");
        Map<String, Boolean> battery = new HashMap<>(); // name -> initialize
        battery.put("net.minecraft.client.main.Main", Boolean.TRUE);
        battery.put("net.minecraft.client.Minecraft", Boolean.FALSE);
        battery.put("com.adjustclient.Adjust", Boolean.FALSE);
        battery.put("com.adjustclient.render.font.NvgContext", Boolean.FALSE);
        battery.put("com.adjustclient.render.font.FontFamily", Boolean.FALSE);
        battery.put("com.adjustclient.render.RenderUtil", Boolean.FALSE);
        battery.put("com.adjustclient.module.impl.player.voicechat.audio.MicrophoneWorker", Boolean.FALSE);
        battery.put("com.adjustclient.module.impl.player.voicechat.playback.AudioStream", Boolean.FALSE);
        battery.put("com.adjustclient.audio.opus.OpusCodec", Boolean.TRUE); // static guard must be a no-op on linux
        battery.put("com.adjustclient.audio.Denoiser", Boolean.TRUE);
        battery.put("com.adjustclient.audio.openal.AlContext", Boolean.FALSE);
        battery.put("org.lwjgl.opengl.Display", Boolean.FALSE);
        battery.put("org.lwjgl.input.Keyboard", Boolean.FALSE);
        battery.put("org.lwjgl.input.Mouse", Boolean.FALSE);
        battery.put("org.lwjgl.Sys", Boolean.FALSE);
        battery.put("paulscode.sound.libraries.LibraryLWJGLOpenAL", Boolean.FALSE);
        battery.put("paulscode.sound.SoundSystemConfig", Boolean.FALSE);
        battery.put("org.lwjgl.util.glu.Project", Boolean.FALSE);
        battery.put("org.lwjgl.util.glu.GLU", Boolean.FALSE);
        battery.put("org.joml.Vector4f", Boolean.TRUE);
        for (Map.Entry<String, Boolean> e : battery.entrySet()) {
            try {
                Class.forName(e.getKey(), e.getValue().booleanValue(),
                        ProbeAdjust.class.getClassLoader());
                check(true, "links: " + e.getKey() + (e.getValue() ? " (initialized)" : ""));
            } catch (Throwable t) {
                check(false, "links: " + e.getKey() + " -> " + t);
            }
        }

        // ---------------- Stage 3: boot to the native boundary ----------------
        System.out.println("== Stage 3: headless boot to the LWJGL native boundary ==");
        File gameDir = Files.createTempDirectory("adjust-gamedir").toFile();
        File assetsDir = new File(gameDir, "assets");
        assetsDir.mkdirs();
        List<String> cmd = new ArrayList<>();
        cmd.add(System.getProperty("java.home") + File.separator + "bin"
                + File.separator + (System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win") ? "java.exe" : "java"));
        cmd.add("-Xmx1G");
        cmd.add("-Dfile.encoding=UTF-8");
        cmd.add("--add-opens=java.base/java.nio=ALL-UNNAMED");
        for (String cp : bootCp) cmd.add("-cp");
        cmd.add(String.join(File.pathSeparator, bootCp));
        cmd.add("net.minecraft.client.main.Main");
        cmd.addAll(Arrays.asList(
                "--version", "1.8.9",
                "--accessToken", "0",
                "--gameDir", gameDir.getAbsolutePath(),
                "--assetsDir", assetsDir.getAbsolutePath(),
                "--assetIndex", "1.8",
                "--userProperties", "{}"));

        Process p = new ProcessBuilder(cmd).redirectErrorStream(true).start();
        ByteArrayOutputStream outBuf = new ByteArrayOutputStream();
        Thread reader = new Thread(() -> {
            try (InputStream in = p.getInputStream()) {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) outBuf.write(buf, 0, n);
            } catch (Exception ignored) {
            }
        });
        reader.setDaemon(true);
        reader.start();
        boolean finished = p.waitFor(180, TimeUnit.SECONDS);
        String out = new String(outBuf.toByteArray(), StandardCharsets.UTF_8);
        String tail = out.length() > 4000 ? "... " + out.substring(out.length() - 4000) : out;
        System.out.println("---- boot output (tail) ----");
        System.out.println(tail);
        System.out.println("----------------------------");

        check(finished, "boot process terminated (no hang)");
        check(out.contains("UnsatisfiedLinkError")
                        || out.contains("Failed to load a library")
                        || out.contains("can't load library"),
                "boot failed exactly at the LWJGL native boundary (expected headless CI)");
        boolean cleanBoundary = true;
        String[] forbidden = {"ClassNotFoundException", "NoClassDefFoundError",
                "NoSuchMethodError", "NoSuchFieldError", "VerifyError"};
        List<String> hits = new ArrayList<>();
        for (String f : forbidden) {
            if (out.contains(f)) {
                hits.add(f);
                cleanBoundary = false;
            }
        }
        check(cleanBoundary, "no class/ linkage errors before the boundary" + hits);

        if (failures > 0) {
            System.err.println("PROBE-FAILED: " + failures + " check(s) failed");
            System.exit(1);
        }
        System.out.println("PROBE-PASSED: Android jar is sound up to the LWJGL native boundary");
    }

    private static byte[] readAll(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toByteArray();
    }
}
