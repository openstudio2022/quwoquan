import com.flutter.gradle.tasks.FlutterTask
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.URI
import java.nio.charset.StandardCharsets
import java.util.Base64

plugins {
    id("com.android.application")
    id("dev.flutter.flutter-gradle-plugin")
}

val googleServicesConfig = projectDir.resolve("google-services.json")
val releaseKeystorePath = System.getenv("QWQ_ANDROID_RELEASE_KEYSTORE_PATH")?.trim().orEmpty()
val releaseKeystorePassword = System.getenv("QWQ_ANDROID_RELEASE_STORE_PASSWORD")?.trim().orEmpty()
val releaseKeyAlias = System.getenv("QWQ_ANDROID_RELEASE_KEY_ALIAS")?.trim().orEmpty()
val releaseKeyPassword = System.getenv("QWQ_ANDROID_RELEASE_KEY_PASSWORD")?.trim().orEmpty()
val releaseSigningConfigured =
    releaseKeystorePath.isNotEmpty() &&
        releaseKeystorePassword.isNotEmpty() &&
        releaseKeyAlias.isNotEmpty() &&
        releaseKeyPassword.isNotEmpty() &&
        File(releaseKeystorePath).isFile
if (googleServicesConfig.isFile) {
    apply(plugin = "com.google.gms.google-services")
} else {
    logger.lifecycle(
        "[rtc] google-services.json is absent; Firebase incoming calls remain fail-closed.",
    )
}
gradle.taskGraph.whenReady {
    val shipsProductionBinary =
        allTasks.any { task ->
            task.project == project &&
                task.name.contains("Release", ignoreCase = true)
        }
    if (shipsProductionBinary && !googleServicesConfig.isFile) {
        throw GradleException(
            "production Android build requires android/app/google-services.json; " +
                "inject the protected Firebase config before building and remove it afterwards",
        )
    }
    if (shipsProductionBinary && !releaseSigningConfigured) {
        throw GradleException(
            "production Android release requires QWQ_ANDROID_RELEASE_KEYSTORE_PATH, " +
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD, QWQ_ANDROID_RELEASE_KEY_ALIAS and " +
                "QWQ_ANDROID_RELEASE_KEY_PASSWORD; debug signing is forbidden",
        )
    }
}

val repoRootDir = rootProject.projectDir.parentFile.parentFile
val localEnvDebugPlaceholderCert =
    projectDir.resolve("src/debug-res-templates/local_env_debug_root_placeholder.crt")
val generatedLocalEnvDebugResDir = layout.buildDirectory.dir("generated/local-env-debug-res")
val localEnvCaEnvVar = "QWQ_ANDROID_LOCAL_ENV_CA_PATH"
val localEnvCaRequiredEnvVar = "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED"
val androidLocalAutoPrepareEnvVar = "QWQ_ANDROID_LOCAL_AUTO_PREPARE"
val androidLocalAutoReverseEnvVar = "QWQ_ANDROID_LOCAL_AUTO_REVERSE"
val androidAbiSplitsEnvVar = "QWQ_ANDROID_ABI_SPLITS"
val androidAbiSplitsEnabled = envFlagEnabled(androidAbiSplitsEnvVar, false)
fun escapedBuildConfigString(name: String): String {
    val value = System.getenv(name)?.trim().orEmpty()
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
}
fun escapedBuildConfigString(name: String, defaultValue: String): String {
    val value = System.getenv(name)?.trim().takeUnless { it.isNullOrEmpty() } ?: defaultValue
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
}
val deploymentWorkRoot =
    System.getenv("QWQ_DEPLOY_WORK_ROOT")?.takeIf { it.isNotBlank() }
        ?: System.getProperty("user.home") + "/.cache/quwoquan/deploy"
val alphaLocalCaCert =
    File(deploymentWorkRoot, "alpha-local/certificates/root.crt")
val alphaLocalObjectStorageCaCert =
    File(deploymentWorkRoot, "alpha-local/certificates/object-storage/ca.crt")
val alphaLocalAppTrustBundle =
    File(deploymentWorkRoot, "alpha-local/certificates/app-local-trust-bundle.crt")
val localTargetTlsScript =
    repoRootDir.resolve("quwoquan_ops/cli/lib/local_target_tls.py")
val alphaLocalStackScript =
    repoRootDir.resolve("quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh")
val alphaLocalAdbReversePorts = listOf("17000", "17010", "17100")
val alphaLocalTransportDartDefineKeys =
    setOf(
        "CLOUD_GATEWAY_BASE_URL",
        "APP_LEGAL_BASE_URL",
        "MEDIA_AVATAR_CDN_BASE_URL",
        "MEDIA_IMAGE_CDN_BASE_URL",
        "MEDIA_VIDEO_CDN_BASE_URL",
        "MEDIA_UPLOAD_BASE_URL",
    )

fun loadRuntimePackageDartDefines(env: String): LinkedHashMap<String, String> {
    val output = ByteArrayOutputStream()
    exec {
        workingDir = repoRootDir
        commandLine(
            "python3",
            repoRootDir.resolve("quwoquan_app/scripts/env/print_app_env_dart_defines.py").absolutePath,
            "--env",
            env,
            "--format",
            "args",
        )
        standardOutput = output
    }
    val definitions = linkedMapOf<String, String>()
    for (raw in output.toString(StandardCharsets.UTF_8.name()).lineSequence()) {
        val define = raw.trim().removePrefix("--dart-define=")
        val separator = define.indexOf("=")
        if (separator > 0) {
            definitions[define.substring(0, separator)] = define.substring(separator + 1)
        }
    }
    check(definitions.containsKey("CLOUD_GATEWAY_BASE_URL")) {
        "runtime package $env did not produce CLOUD_GATEWAY_BASE_URL"
    }
    return definitions
}

fun rewriteAlphaLocalTransport(rawUrl: String): String {
    val parsed = URI(rawUrl)
    check(parsed.scheme == "https" && parsed.port > 0) {
        "alpha local transport requires an explicit HTTPS port: $rawUrl"
    }
    return URI(
        parsed.scheme,
        parsed.userInfo,
        "localhost",
        parsed.port,
        parsed.path,
        parsed.query,
        parsed.fragment,
    ).toASCIIString()
}

// 裸 Android Debug/Profile 仍以同一个环境包为入口；仅 transport 覆盖到 adb reverse
// 的 localhost，避免把开发机域名硬编码为第二份配置。
val alphaLocalDefaultDartDefines =
    loadRuntimePackageDartDefines("alpha").apply {
        alphaLocalTransportDartDefineKeys.forEach { key ->
            put(key, rewriteAlphaLocalTransport(getValue(key)))
        }
        put("APP_INSTANCE_NAMESPACE", "android-plain-flutter-run")
    }

android {
    namespace = "com.quwoquan.quwoquan_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion
    buildFeatures {
        buildConfig = true
    }

    sourceSets {
        getByName("debug").res.srcDir(generatedLocalEnvDebugResDir)
        getByName("profile").res.srcDir(generatedLocalEnvDebugResDir)
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // Patrol/AndroidX Test 依赖在 minSdk 24 上使用 Java 8+ API，需要 desugaring。
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        applicationId = "com.quwoquan.quwoquan_app"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        buildConfigField("String", "QWQ_WECHAT_APP_ID", escapedBuildConfigString("QWQ_WECHAT_APP_ID"))
        buildConfigField(
            "String",
            "QWQ_WECHAT_ANDROID_SIGNATURE",
            escapedBuildConfigString("QWQ_WECHAT_ANDROID_SIGNATURE"),
        )
        buildConfigField("String", "QWQ_QQ_APP_ID", escapedBuildConfigString("QWQ_QQ_APP_ID"))
        buildConfigField(
            "String",
            "QWQ_ALIPAY_CALLBACK_SCHEME",
            escapedBuildConfigString("QWQ_ALIPAY_CALLBACK_SCHEME"),
        )
        buildConfigField(
            "String",
            "QWQ_ALIYUN_PNVS_SECRET_INFO",
            escapedBuildConfigString("QWQ_ALIYUN_PNVS_SECRET_INFO"),
        )
        buildConfigField(
            "String",
            "QWQ_RECOVERY_BASE_URL",
            escapedBuildConfigString("QWQ_APP_RECOVERY_BASE_URL", "https://api.quwoquan.com"),
        )
        buildConfigField(
            "String",
            "QWQ_PUBLIC_WEB_URL",
            escapedBuildConfigString("QWQ_APP_PUBLIC_WEB_URL", "https://quwoquan.com"),
        )
        // Patrol native 接线：让 Android Test Orchestrator 能发现并执行 Dart 测试。
        testInstrumentationRunner = "pl.leancode.patrol.PatrolJUnitRunner"
        testInstrumentationRunnerArguments["clearPackageData"] = "true"
        ndk {
            if (androidAbiSplitsEnabled) {
                // splits.abi 与 Flutter 默认 abiFilters 冲突；显式拆包时由 split 决定 ABI。
                abiFilters.clear()
            }
        }
    }

    testOptions {
        execution = "ANDROIDX_TEST_ORCHESTRATOR"
    }

    signingConfigs {
        if (releaseSigningConfigured) {
            create("officialRelease") {
                storeFile = File(releaseKeystorePath)
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = true
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("officialRelease")
        }
    }

    splits {
        abi {
            isEnable = androidAbiSplitsEnabled
            if (androidAbiSplitsEnabled) {
                reset()
                include("armeabi-v7a", "arm64-v8a", "x86_64")
                isUniversalApk = false
            }
        }
    }
}

flutter {
    source = "../.."
}

fun envFlagEnabled(name: String, defaultValue: Boolean = true): Boolean {
    val raw = providers.environmentVariable(name).orElse(if (defaultValue) "1" else "0").get().trim()
    return raw.equals("1", ignoreCase = true) ||
        raw.equals("true", ignoreCase = true) ||
        raw.equals("yes", ignoreCase = true) ||
        raw.equals("on", ignoreCase = true)
}

fun decodeDartDefines(encoded: String?): MutableList<String> {
    if (encoded.isNullOrBlank()) {
        return mutableListOf()
    }
    val decoder = Base64.getDecoder()
    return encoded
        .split(",")
        .filter { it.isNotBlank() }
        .map { String(decoder.decode(it), StandardCharsets.UTF_8) }
        .toMutableList()
}

fun encodeDartDefines(defines: List<String>): String {
    val encoder = Base64.getEncoder()
    return defines.joinToString(",") {
        encoder.encodeToString(it.toByteArray(StandardCharsets.UTF_8))
    }
}

fun requireCompleteRuntimeDartDefines(encoded: String?, taskName: String) {
    val valuesByKey =
        decodeDartDefines(encoded)
            .mapNotNull { define ->
                val separator = define.indexOf("=")
                if (separator <= 0) {
                    null
                } else {
                    define.substring(0, separator) to define.substring(separator + 1).trim()
                }
            }
            .toMap()
    val requiredKeys =
        setOf(
            "APP_RUNTIME_ENV",
            "CLOUD_GATEWAY_BASE_URL",
            "APP_LEGAL_BASE_URL",
            "MEDIA_AVATAR_CDN_BASE_URL",
            "MEDIA_IMAGE_CDN_BASE_URL",
            "MEDIA_VIDEO_CDN_BASE_URL",
            "MEDIA_UPLOAD_BASE_URL",
        )
    val missing = requiredKeys.filter { valuesByKey[it].isNullOrBlank() }
    check(missing.isEmpty()) {
        "Release Flutter build requires complete runtime dart-defines; missing " +
            missing.joinToString(", ") +
            ". Use quwoquan_app/scripts/env/print_app_env_dart_defines.py " +
            "or a supported environment build entrypoint. task=$taskName"
    }
}

// Plain `flutter run` alpha debug/profile only. Transport URL keys are force-
// overwritten to localhost so stale `*.quwoquan-env.test` dart-defines cannot
// reach the APK. beta/gamma/prod packages skip this entire merge.
fun mergeAlphaLocalDartDefines(encoded: String?): String {
    val defines = decodeDartDefines(encoded)
    val valuesByKey =
        defines
            .mapNotNull { define ->
                val separator = define.indexOf("=")
                if (separator <= 0) {
                    null
                } else {
                    define.substring(0, separator) to define.substring(separator + 1)
                }
            }.toMap()
            .toMutableMap()
    val runtimeEnv = valuesByKey["APP_RUNTIME_ENV"]?.trim()
    if (!runtimeEnv.isNullOrEmpty() && runtimeEnv != "alpha") {
        return encoded ?: ""
    }
    for ((key, value) in alphaLocalDefaultDartDefines) {
        val shouldForceTransport = key in alphaLocalTransportDartDefineKeys
        if (shouldForceTransport || !valuesByKey.containsKey(key)) {
            valuesByKey[key] = value
        }
    }
    val mergedDefines = valuesByKey.map { (key, value) -> "$key=$value" }
    return encodeDartDefines(mergedDefines)
}

// Flutter 插件在自身 afterEvaluate 中才创建并填充 FlutterTask。这里也在
// afterEvaluate 之后合并，避免先写入的本地环境定义被插件的原始空值覆盖。
afterEvaluate {
    tasks.withType<FlutterTask>().configureEach {
        if (
            name.contains("Debug", ignoreCase = true) ||
                name.contains("Profile", ignoreCase = true)
        ) {
            dartDefines = mergeAlphaLocalDartDefines(dartDefines)
        }
        if (name.contains("Release", ignoreCase = true)) {
            doFirst {
                requireCompleteRuntimeDartDefines(dartDefines, name)
            }
        }
    }
}

tasks.matching { task ->
    task.name.endsWith("JavaWithJavac")
}.configureEach {
    doFirst {
        exec {
            workingDir = rootProject.projectDir.parentFile
            commandLine("bash", "scripts/patch_android_plugin_registrant.sh")
        }
    }
}

val prepareAndroidLocalAlphaStack by tasks.registering {
    inputs.file(alphaLocalStackScript)
    outputs.file(alphaLocalCaCert)

    doLast {
        if (!envFlagEnabled(androidLocalAutoPrepareEnvVar)) {
            logger.lifecycle(
                "Android alpha local stack auto-prepare skipped by $androidLocalAutoPrepareEnvVar=0",
            )
            return@doLast
        }
        if (!alphaLocalStackScript.isFile) {
            throw GradleException("Android alpha local stack script not found: ${alphaLocalStackScript.absolutePath}")
        }
        exec {
            workingDir = repoRootDir
            environment("QWQ_ALPHA_LOCAL_PUBLIC_HOST_SETUP", "skip")
            commandLine("bash", alphaLocalStackScript.absolutePath, "up")
        }
    }
}

val prepareAndroidLocalAdbReverse by tasks.registering {
    doLast {
        if (!envFlagEnabled(androidLocalAutoReverseEnvVar)) {
            logger.lifecycle(
                "Android adb reverse auto-prepare skipped by $androidLocalAutoReverseEnvVar=0",
            )
            return@doLast
        }
        val adbPath = android.adbExecutable
        if (!adbPath.isFile) {
            logger.warn("Android adb executable not found; skip local adb reverse: ${adbPath.absolutePath}")
            return@doLast
        }
        val serialFromEnv = providers.environmentVariable("ANDROID_SERIAL").orElse("").get().trim()
        val devices =
            if (serialFromEnv.isNotEmpty()) {
                listOf(serialFromEnv)
            } else {
                val stdout = ByteArrayOutputStream()
                exec {
                    commandLine(adbPath.absolutePath, "devices")
                    standardOutput = stdout
                }
                stdout
                    .toString(StandardCharsets.UTF_8.name())
                    .lineSequence()
                    .drop(1)
                    .map { it.trim() }
                    .filter { it.endsWith("\tdevice") }
                    .map { it.substringBefore("\t").trim() }
                    .filter { it.isNotEmpty() }
                    .toList()
            }
        if (devices.isEmpty()) {
            logger.lifecycle("No Android device is ready for adb reverse; flutter run will retry after a device is selected.")
            return@doLast
        }
        for (device in devices) {
            for (port in alphaLocalAdbReversePorts) {
                exec {
                    commandLine(
                        adbPath.absolutePath,
                        "-s",
                        device,
                        "reverse",
                        "tcp:$port",
                        "tcp:$port",
                    )
                }
            }
        }
    }
}

val prepareLocalEnvDebugRes by tasks.registering {
    val envProvider = providers.environmentVariable(localEnvCaEnvVar).orElse("")
    val requiredProvider = providers.environmentVariable(localEnvCaRequiredEnvVar).orElse("")
    inputs.file(localEnvDebugPlaceholderCert)
    inputs.file(alphaLocalCaCert).optional()
    inputs.file(alphaLocalObjectStorageCaCert).optional()
    inputs.file(localTargetTlsScript)
    inputs.property("localEnvCaPath", envProvider)
    inputs.property("localEnvCaRequired", requiredProvider)
    outputs.dir(generatedLocalEnvDebugResDir)
    dependsOn(prepareAndroidLocalAlphaStack)

    doLast {
        val outputDir = generatedLocalEnvDebugResDir.get().dir("raw").asFile
        outputDir.mkdirs()
        val outputFile = outputDir.resolve("local_env_debug_root.crt")
        val configuredPath = envProvider.get().trim()
        val requiredValue = requiredProvider.get().trim()
        val caRequired =
            requiredValue.equals("1", ignoreCase = true) ||
                requiredValue.equals("true", ignoreCase = true) ||
                envFlagEnabled(androidLocalAutoPrepareEnvVar)
        if (configuredPath.isEmpty() && caRequired) {
            if (!alphaLocalCaCert.isFile) {
                throw GradleException(
                    "Android local debug CA certificate is required but neither " +
                        "$localEnvCaEnvVar nor ${alphaLocalCaCert.absolutePath} is available.",
                )
            }
        }
        val sourceFile =
            if (configuredPath.isNotEmpty()) {
                file(configuredPath)
            } else if (alphaLocalCaCert.isFile) {
                exec {
                    workingDir = repoRootDir
                    environment("PYTHONDONTWRITEBYTECODE", "1")
                    commandLine(
                        "python3",
                        localTargetTlsScript.absolutePath,
                        "materialize-app-trust-bundle",
                        "--target",
                        "alpha-local",
                    )
                }
                alphaLocalAppTrustBundle
            } else {
                localEnvDebugPlaceholderCert
            }
        if (!sourceFile.isFile) {
            throw GradleException(
                "Android local debug CA certificate not found: ${sourceFile.absolutePath}",
            )
        }
        sourceFile.copyTo(outputFile, overwrite = true)
    }
}

val verifyAndroidLocalAlphaCaSource by tasks.registering {
    inputs.file(alphaLocalCaCert).optional()
    inputs.dir(generatedLocalEnvDebugResDir)
    dependsOn(prepareLocalEnvDebugRes)

    doLast {
        val configuredPath =
            providers.environmentVariable(localEnvCaEnvVar).orElse("").get().trim()
        if (configuredPath.isNotEmpty()) {
            return@doLast
        }
        check(alphaLocalCaCert.isFile) {
            "Android alpha debug CA must be the TLS proxy signing root: ${alphaLocalCaCert.absolutePath}"
        }
        val packagedRoot =
            generatedLocalEnvDebugResDir
                .get()
                .dir("raw")
                .file("local_env_debug_root.crt")
                .asFile
        check(
            alphaLocalAppTrustBundle.isFile &&
                packagedRoot.isFile &&
                packagedRoot.readBytes().contentEquals(alphaLocalAppTrustBundle.readBytes())
        ) {
            "Android packaged local_env_debug_root.crt must exactly equal the alpha local trust bundle"
        }
    }
}

tasks.matching { task ->
    task.name == "preDebugBuild" || task.name == "preProfileBuild"
}.configureEach {
    dependsOn(prepareAndroidLocalAlphaStack)
    dependsOn(prepareAndroidLocalAdbReverse)
    dependsOn(prepareLocalEnvDebugRes)
    dependsOn(verifyAndroidLocalAlphaCaSource)
}

val vendoredAndroidArtifactsDir =
    rootProject.file("../vendor/android_artifacts")

dependencies {
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("com.tencent.mm.opensdk:wechat-sdk-android:6.8.34")
    implementation("com.alipay.sdk:alipaysdk-android:15.8.42")
    implementation(
        files(
            rootProject.file(
                "../vendor/commercial_auth/qq/android/open_sdk_3.5.19_r9483ffc7_lite.jar",
            ),
        ),
    )
    implementation(
        fileTree(
            mapOf(
                "dir" to rootProject.file("../vendor/commercial_auth/aliyun/android"),
                "include" to listOf("*.aar", "*.jar"),
            ),
        ),
    )
    // flutter_webrtc + livekit_client use compileOnly for vendored AARs (AGP 8+).
    implementation(
        files(
            vendoredAndroidArtifactsDir.resolve("android-144.7559.01.aar"),
            vendoredAndroidArtifactsDir.resolve(
                "audioswitch-89582c47c9a04c62f90aa5e57251af4800a62c9a.aar",
            ),
            vendoredAndroidArtifactsDir.resolve("noise-2.0.0.aar"),
        ),
    )
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.3")
    androidTestUtil("androidx.test:orchestrator:1.5.1")
}
