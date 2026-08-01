@file:Suppress("DEPRECATION")

import com.flutter.gradle.tasks.FlutterTask
import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.charset.StandardCharsets
import java.util.Base64

plugins {
    id("com.android.application")
    id("dev.flutter.flutter-gradle-plugin")
}

fun buildCanonicalDirectDebugHandoff(): Map<String, Any?> {
    val output =
        providers.exec {
            commandLine(
                "python3",
                rootProject.file("../scripts/device/build_launcher_handoff.py").absolutePath,
                "--env",
                "alpha",
                "--target",
                "alpha-local",
                "--launch-mode",
                "direct_flutter_run",
                "--app-instance-id",
                "direct-flutter-run",
                "--app-instance-namespace",
                "direct-flutter-run",
            )
            environment("PYTHONDONTWRITEBYTECODE", "1")
        }.standardOutput.asText.get()
    @Suppress("UNCHECKED_CAST")
    return JsonSlurper().parseText(output) as Map<String, Any?>
}

fun handoffString(handoff: Map<String, Any?>?, key: String): String =
    handoff?.get(key)?.toString()?.trim().orEmpty()

fun handoffStringMap(handoff: Map<String, Any?>?, key: String): Map<String, String> =
    (handoff?.get(key) as? Map<*, *>)
        ?.entries
        ?.associate { entry -> entry.key.toString() to entry.value.toString() }
        .orEmpty()

val googleServicesConfig = projectDir.resolve("google-services.json")
val releaseKeystorePath = System.getenv("QWQ_ANDROID_RELEASE_KEYSTORE_PATH")?.trim().orEmpty()
val releaseKeystorePassword = System.getenv("QWQ_ANDROID_RELEASE_STORE_PASSWORD")?.trim().orEmpty()
val releaseKeyAlias = System.getenv("QWQ_ANDROID_RELEASE_KEY_ALIAS")?.trim().orEmpty()
val releaseKeyPassword = System.getenv("QWQ_ANDROID_RELEASE_KEY_PASSWORD")?.trim().orEmpty()
val explicitAppRuntimeEnvironment = System.getenv("QWQ_APP_RUNTIME_ENV")?.trim().orEmpty()
val explicitAppLaunchTarget = System.getenv("QWQ_LAUNCH_TARGET")?.trim().orEmpty()
val explicitAppLaunchMode = System.getenv("QWQ_APP_LAUNCH_MODE")?.trim().orEmpty()
val explicitAppBuildContext = System.getenv("QWQ_APP_BUILD_CONTEXT")?.trim().orEmpty()
val explicitDartDefinesDigest = System.getenv("QWQ_DART_DEFINES_DIGEST")?.trim().orEmpty()
val explicitRuntimeConfigDigest =
    System.getenv("QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST")?.trim().orEmpty()
val explicitEffectiveLaunchManifestDigest =
    System.getenv("QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST")?.trim().orEmpty()
val directDebugHandoff =
    if (
        listOf(
            explicitAppRuntimeEnvironment,
            explicitAppLaunchTarget,
            explicitAppLaunchMode,
            explicitAppBuildContext,
            explicitDartDefinesDigest,
            explicitRuntimeConfigDigest,
            explicitEffectiveLaunchManifestDigest,
        ).all { it.isEmpty() }
    ) {
        buildCanonicalDirectDebugHandoff()
    } else {
        null
    }
val isDirectDebugHandoff = directDebugHandoff != null
val appRuntimeEnvironment =
    explicitAppRuntimeEnvironment.ifEmpty {
        handoffString(directDebugHandoff, "environment")
    }
val effectiveAppRuntimeEnvironment = appRuntimeEnvironment.ifEmpty { "alpha" }
val appLaunchTarget =
    explicitAppLaunchTarget.ifEmpty { handoffString(directDebugHandoff, "target") }
val appBuildContext =
    explicitAppBuildContext.ifEmpty {
        if (isDirectDebugHandoff) "direct-debug" else ""
    }
val dartDefinesDigest =
    explicitDartDefinesDigest.ifEmpty {
        handoffString(directDebugHandoff, "dartDefinesDigest")
    }
val expectedRuntimeConfigDigest =
    explicitRuntimeConfigDigest.ifEmpty {
        handoffString(directDebugHandoff, "runtimeConfigDigest")
    }
val effectiveLaunchManifestDigest =
    explicitEffectiveLaunchManifestDigest.ifEmpty {
        handoffString(directDebugHandoff, "effectiveLaunchManifestDigest")
    }
require(effectiveAppRuntimeEnvironment in setOf("alpha", "beta", "gamma", "prod")) {
    "QWQ_APP_RUNTIME_ENV must be alpha|beta|gamma|prod"
}
val runNativeStartupInstrumentation =
    providers.gradleProperty("qwq.nativeStartupInstrumentation").orNull == "true"
val nativeRecoveryBaseUrl =
    System.getenv("QWQ_APP_RECOVERY_BASE_URL")?.trim().orEmpty().ifEmpty {
        handoffString(directDebugHandoff, "recoveryBaseUrl")
    }
val nativePublicWebUrl =
    System.getenv("QWQ_APP_PUBLIC_WEB_URL")?.trim().orEmpty().ifEmpty {
        handoffString(directDebugHandoff, "publicWebBaseUrl")
    }
val nativeAppDownloadBaseUrl =
    System.getenv("QWQ_APP_DOWNLOAD_BASE_URL")?.trim().orEmpty().ifEmpty {
        handoffString(directDebugHandoff, "appDownloadBaseUrl")
    }
val nativeRuntimeDefineKeys =
    setOf(
        "APP_RUNTIME_ENV",
        "CLOUD_GATEWAY_BASE_URL",
        "APP_LEGAL_BASE_URL",
        "PUBLIC_WEB_BASE_URL",
        "APP_DOWNLOAD_BASE_URL",
        "REALTIME_CONNECTION_URL",
        "MEDIA_AVATAR_CDN_BASE_URL",
        "MEDIA_IMAGE_CDN_BASE_URL",
        "MEDIA_VIDEO_CDN_BASE_URL",
        "MEDIA_UPLOAD_BASE_URL",
        "RTC_MEDIA_CONNECTION_URL",
        "QWQ_APP_LAUNCH_MODE",
    )
val suppliedRuntimeDefines =
    decodeDartDefines(providers.gradleProperty("dart-defines").orNull)
        .mapNotNull { define ->
            val separator = define.indexOf("=")
            if (separator <= 0) {
                null
            } else {
                define.substring(0, separator) to define.substring(separator + 1)
            }
        }
        .toMap()
val nativeRuntimeDefines =
    (if (isDirectDebugHandoff) {
        handoffStringMap(directDebugHandoff, "dartDefines")
    } else {
        suppliedRuntimeDefines
    }).filterKeys { it in nativeRuntimeDefineKeys }
val nativeRuntimeDefinesJson = JsonOutput.toJson(nativeRuntimeDefines.toSortedMap())
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
    if (
        shipsProductionBinary &&
            (
                nativeRecoveryBaseUrl.isEmpty() ||
                    nativePublicWebUrl.isEmpty() ||
                    nativeAppDownloadBaseUrl.isEmpty()
            )
    ) {
        throw GradleException(
            "production Android build requires topology-projected " +
                "recovery, public-web, and app-download base URLs",
        )
    }
    if (shipsProductionBinary && !releaseSigningConfigured) {
        throw GradleException(
            "production Android release requires QWQ_ANDROID_RELEASE_KEYSTORE_PATH, " +
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD, QWQ_ANDROID_RELEASE_KEY_ALIAS and " +
                "QWQ_ANDROID_RELEASE_KEY_PASSWORD; debug signing is forbidden",
        )
    }
    if (shipsProductionBinary && explicitAppRuntimeEnvironment.isEmpty()) {
        throw GradleException(
            "production Android release requires explicit QWQ_APP_RUNTIME_ENV",
        )
    }
    if (
        shipsProductionBinary &&
            !effectiveLaunchManifestDigest.matches(Regex("sha256:[0-9a-f]{64}"))
    ) {
        throw GradleException(
            "production Android release requires canonical effective launch manifest digest",
        )
    }
}

check(
    expectedRuntimeConfigDigest.isEmpty() ||
        expectedRuntimeConfigDigest.matches(Regex("sha256:[0-9a-f]{64}")),
) {
    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST must be the canonical packaged runtime identity"
}
val androidAbiSplitsEnvVar = "QWQ_ANDROID_ABI_SPLITS"
val androidAbiSplitsEnabled = envFlagEnabled(androidAbiSplitsEnvVar, false)
val flutterTargetAndroidAbis =
    providers.gradleProperty("target-platform").orNull
        ?.split(",")
        ?.mapNotNull { targetPlatform ->
            when (targetPlatform.trim()) {
                "android-arm" -> "armeabi-v7a"
                "android-arm64" -> "arm64-v8a"
                "android-x64" -> "x86_64"
                else -> null
            }
        }
        ?.distinct()
        .orEmpty()
fun escapedBuildConfigValue(value: String): String {
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
}
fun escapedBuildConfigString(name: String): String =
    escapedBuildConfigValue(System.getenv(name)?.trim().orEmpty())
fun escapedBuildConfigString(name: String, defaultValue: String): String {
    val value = System.getenv(name)?.trim().takeUnless { it.isNullOrEmpty() } ?: defaultValue
    return escapedBuildConfigValue(value)
}
android {
    namespace = "com.quwoquan.quwoquan_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion
    buildFeatures {
        buildConfig = true
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
            escapedBuildConfigValue(nativeRecoveryBaseUrl),
        )
        buildConfigField(
            "String",
            "QWQ_PUBLIC_WEB_URL",
            escapedBuildConfigValue(nativePublicWebUrl),
        )
        buildConfigField(
            "String",
            "QWQ_APP_DOWNLOAD_BASE_URL",
            escapedBuildConfigValue(nativeAppDownloadBaseUrl),
        )
        buildConfigField(
            "String",
            "QWQ_RUNTIME_ENVIRONMENT",
            "\"$effectiveAppRuntimeEnvironment\"",
        )
        buildConfigField(
            "String",
            "QWQ_RUNTIME_CONFIG_DIGEST",
            "\"${expectedRuntimeConfigDigest.replace("\\", "\\\\").replace("\"", "\\\"")}\"",
        )
        buildConfigField(
            "String",
            "QWQ_DART_DEFINES_DIGEST",
            "\"${dartDefinesDigest.replace("\\", "\\\\").replace("\"", "\\\"")}\"",
        )
        buildConfigField(
            "String",
            "QWQ_LAUNCH_TARGET",
            "\"${appLaunchTarget.replace("\\", "\\\\").replace("\"", "\\\"")}\"",
        )
        buildConfigField(
            "String",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
            "\"${effectiveLaunchManifestDigest.replace("\\", "\\\\").replace("\"", "\\\"")}\"",
        )
        buildConfigField(
            "String",
            "QWQ_RUNTIME_DART_DEFINES_JSON",
            escapedBuildConfigValue(nativeRuntimeDefinesJson),
        )
        // Patrol remains the default runner for Dart tests. Native Gate tests
        // explicitly select AndroidJUnitRunner so they can validate recovery
        // without starting Patrol or a second Flutter product flow.
        testInstrumentationRunner =
            if (runNativeStartupInstrumentation) {
                "androidx.test.runner.AndroidJUnitRunner"
            } else {
                "pl.leancode.patrol.PatrolJUnitRunner"
            }
        testInstrumentationRunnerArguments["clearPackageData"] = "true"
        ndk {
            if (androidAbiSplitsEnabled) {
                // splits.abi 与 Flutter 默认 abiFilters 冲突；显式拆包时由 split 决定 ABI。
                abiFilters.clear()
            } else if (flutterTargetAndroidAbis.isNotEmpty()) {
                // flutter run 已按真机架构编译 Flutter engine；同步过滤三方 native library，
                // 避免向单一真机传输包含无关 ABI 的通用 debug APK。
                abiFilters.clear()
                abiFilters.addAll(flutterTargetAndroidAbis)
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

fun requireCompleteRuntimeDartDefines(
    encoded: String?,
    taskName: String,
    expectedEnvironment: String? = null,
) {
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
            "PUBLIC_WEB_BASE_URL",
            "MEDIA_AVATAR_CDN_BASE_URL",
            "MEDIA_IMAGE_CDN_BASE_URL",
            "MEDIA_VIDEO_CDN_BASE_URL",
            "MEDIA_UPLOAD_BASE_URL",
            "RTC_MEDIA_CONNECTION_URL",
        )
    val missing = requiredKeys.filter { valuesByKey[it].isNullOrBlank() }
    check(missing.isEmpty()) {
        "Flutter build requires complete runtime dart-defines; missing " +
            missing.joinToString(", ") +
            ". Use quwoquan_app/scripts/env/print_app_env_dart_defines.py " +
            "or a supported environment build entrypoint. task=$taskName"
    }
    if (expectedEnvironment != null) {
        check(valuesByKey["APP_RUNTIME_ENV"] == expectedEnvironment) {
            "Flutter build runtime environment must be $expectedEnvironment for $taskName; " +
                "use quwoquan_app/run.sh -d <device>."
        }
    }
}

val verifyAndroidLocalLauncherContract by tasks.registering {
    doLast {
        val runtimeEnvironment = appRuntimeEnvironment
        val launchTarget = appLaunchTarget
        val buildContext = appBuildContext
        val defineDigest = dartDefinesDigest
        val deviceID =
            providers.environmentVariable("QWQ_RUN_DEVICE_ID").orElse("").get().trim()
        val serial =
            providers.environmentVariable("ANDROID_SERIAL").orElse("").get().trim()
        val consumerID =
            providers.environmentVariable("QWQ_RUN_CONSUMER_ID").orElse("").get().trim()
        val portsValue =
            providers.environmentVariable("QWQ_ANDROID_LOCAL_PORTS").orElse("").get().trim()
        val reverseExpectedPorts =
            providers.environmentVariable("QWQ_ANDROID_REVERSE_EXPECTED_PORTS").orElse("").get().trim()
        val reverseActualPorts =
            providers.environmentVariable("QWQ_ANDROID_REVERSE_ACTUAL_PORTS").orElse("").get().trim()
        val reverseReceiptDigest =
            providers.environmentVariable("QWQ_ANDROID_REVERSE_RECEIPT_DIGEST").orElse("").get().trim()
        val consumerLeaseID =
            providers.environmentVariable("QWQ_CONSUMER_LEASE_ID").orElse("").get().trim()
        val leaseAcquired =
            providers.environmentVariable("QWQ_CONSUMER_LEASE_ACQUIRED").orElse("").get().trim()
        val targetEnvironments =
            mapOf(
                "alpha-local" to "alpha",
                "beta-local" to "beta",
                "gamma-local" to "gamma",
                "prod-sim" to "prod",
                "prod-hosted" to "prod",
            )
        check(runtimeEnvironment in setOf("alpha", "beta", "gamma", "prod")) {
            "GATE_BLOCK: Android debug/profile requires explicit local QWQ_APP_RUNTIME_ENV " +
                "(alpha|beta|gamma|prod) from a canonical launcher handoff."
        }
        check(targetEnvironments[launchTarget] == runtimeEnvironment) {
            "GATE_BLOCK: QWQ_LAUNCH_TARGET=$launchTarget does not match " +
                "QWQ_APP_RUNTIME_ENV=$runtimeEnvironment."
        }
        check(defineDigest.matches(Regex("sha256:[0-9a-f]{64}"))) {
            "GATE_BLOCK: canonical QWQ_DART_DEFINES_DIGEST is missing."
        }
        check(expectedRuntimeConfigDigest.matches(Regex("sha256:[0-9a-f]{64}"))) {
            "GATE_BLOCK: canonical packaged runtime config digest is missing."
        }
        check(
            effectiveLaunchManifestDigest.matches(Regex("sha256:[0-9a-f]{64}")),
        ) {
            "GATE_BLOCK: canonical effective launch manifest digest is missing."
        }
        if (buildContext == "direct-debug") {
            check(
                isDirectDebugHandoff &&
                    runtimeEnvironment == "alpha" &&
                    launchTarget == "alpha-local",
            ) {
                "GATE_BLOCK: direct Flutter Debug must use the canonical alpha-local handoff."
            }
            val trustCommand =
                mutableListOf(
                    "python3",
                    rootProject.file("../../quwoquan_ops/cli/stackctl.py").absolutePath,
                    "--output-format",
                    "json",
                    "device-trust",
                    "--target",
                    "alpha-local",
                    "--platform",
                    "android-emulator",
                    "--action",
                    "install",
                    "--lease-id",
                    "direct-flutter-run:${serial.ifEmpty { "auto" }}",
                )
            if (serial.isNotEmpty()) {
                trustCommand.addAll(listOf("--device", serial))
            }
            exec {
                commandLine(trustCommand)
                standardOutput = ByteArrayOutputStream()
            }
            return@doLast
        }
        if (buildContext == "package-only") {
            return@doLast
        }
        check(buildContext == "runtime") {
            "GATE_BLOCK: QWQ_APP_BUILD_CONTEXT must be runtime or package-only."
        }
        check(launchTarget in setOf("alpha-local", "beta-local", "gamma-local", "prod-sim")) {
            "GATE_BLOCK: Android debug/profile runtime launch requires an explicit local target; " +
                "prod-hosted must use a signed release artifact."
        }
        check(deviceID.isNotEmpty() && serial == deviceID) {
            "GATE_BLOCK: Android debug/profile requires QWQ_RUN_DEVICE_ID and matching " +
                "ANDROID_SERIAL from a canonical environment launcher."
        }
        check(consumerID.isNotEmpty() && leaseAcquired == "1") {
            "GATE_BLOCK: Android local runtime consumer lease is absent; " +
                "use a canonical environment launcher."
        }
        check(consumerLeaseID.matches(Regex("sha256:[0-9a-f]{64}"))) {
            "GATE_BLOCK: Android local runtime consumer lease identity is absent."
        }
        check(reverseReceiptDigest.matches(Regex("sha256:[0-9a-f]{64}"))) {
            "GATE_BLOCK: Android adb reverse receipt digest is absent."
        }
        val ports =
            portsValue
                .split(",")
                .map { it.trim() }
                .filter { it.isNotEmpty() }
                .distinct()
        check(ports.isNotEmpty()) {
            "GATE_BLOCK: Android local topology ports are absent; " +
                "use a canonical environment launcher."
        }
        val expectedPorts =
            reverseExpectedPorts
                .split(",")
                .map { it.trim() }
                .filter { it.isNotEmpty() }
                .distinct()
        val actualPorts =
            reverseActualPorts
                .split(",")
                .map { it.trim() }
                .filter { it.isNotEmpty() }
                .distinct()
        check(expectedPorts == ports && actualPorts == ports) {
            "GATE_BLOCK: Android adb reverse expected/actual ports do not match " +
                "the canonical local topology."
        }
        val output = ByteArrayOutputStream()
        exec {
            commandLine(android.adbExecutable, "-s", deviceID, "reverse", "--list")
            standardOutput = output
        }
        val reverseList = output.toString(StandardCharsets.UTF_8)
        val missing = ports.filter { port ->
            reverseList.lineSequence().none { line ->
                line.split(Regex("\\s+")).count { token -> token == "tcp:$port" } >= 2
            }
        }
        check(missing.isEmpty()) {
            "GATE_BLOCK: Android adb reverse is incomplete for $deviceID; missing " +
                missing.joinToString(", ") +
                ". Re-run quwoquan_app/run.sh -d <device>."
        }
    }
}

afterEvaluate {
    tasks.withType<FlutterTask>().configureEach {
        if (
            name.contains("Debug", ignoreCase = true) ||
                name.contains("Profile", ignoreCase = true)
        ) {
            dependsOn(verifyAndroidLocalLauncherContract)
            doFirst {
                if (isDirectDebugHandoff) {
                    check(name.contains("Debug", ignoreCase = true)) {
                        "GATE_BLOCK: direct Flutter handoff is supported only for Debug; " +
                            "Profile requires an explicit canonical launcher handoff."
                    }
                    val suppliedKeys =
                        decodeDartDefines(dartDefines)
                            .mapNotNull { define -> define.substringBefore("=", "").ifEmpty { null } }
                            .filter { it in nativeRuntimeDefineKeys }
                    check(suppliedKeys.isEmpty()) {
                        "GATE_BLOCK: direct Flutter Debug cannot mix synthesized Alpha " +
                            "with explicit runtime dart-defines: " + suppliedKeys.joinToString(", ")
                    }
                    logger.lifecycle(
                        "[android-runtime] direct Debug uses canonical alpha-local handoff.",
                    )
                } else {
                    requireCompleteRuntimeDartDefines(
                        dartDefines,
                        name,
                        expectedEnvironment = effectiveAppRuntimeEnvironment,
                    )
                }
            }
        }
        if (name.contains("Release", ignoreCase = true)) {
            doFirst {
                requireCompleteRuntimeDartDefines(dartDefines, name)
            }
        }
    }
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
    // Keep versions aligned with Patrol's strict AndroidX test resolution.
    androidTestImplementation("androidx.test:runner:1.5.1")
    androidTestImplementation("androidx.test:rules:1.2.0")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.0")
    androidTestUtil("androidx.test:orchestrator:1.5.1")
}
