import com.flutter.gradle.tasks.FlutterTask
import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets
import java.util.Base64

plugins {
    id("com.android.application")
    id("dev.flutter.flutter-gradle-plugin")
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
val alphaLocalCaCert =
    repoRootDir.resolve(
        ".qwq_output/env/alpha/local/alpha-local/tls/ca/root.crt",
    )
val alphaLocalStackScript =
    repoRootDir.resolve("quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh")
val alphaLocalAdbReversePorts = listOf("17000", "17010", "17100")
val alphaLocalDefaultDartDefines =
    linkedMapOf(
        "APP_RUNTIME_ENV" to "alpha",
        "APP_DATA_SOURCE" to "mock",
        "CLOUD_GATEWAY_BASE_URL" to "https://localhost:17000",
        "APP_LEGAL_BASE_URL" to "https://localhost:17000/legal",
        "MEDIA_AVATAR_CDN_BASE_URL" to "https://localhost:17100",
        "MEDIA_IMAGE_CDN_BASE_URL" to "https://localhost:17100",
        "MEDIA_VIDEO_CDN_BASE_URL" to "https://localhost:17100",
        "MEDIA_UPLOAD_BASE_URL" to "https://localhost:17100",
        "CONTRACT_FIXTURE_PROFILE" to "lite",
        "APP_CURRENT_USER_ID" to "fixture_user_current",
        "APP_INSTANCE_NAMESPACE" to "android-plain-flutter-run",
    )

android {
    namespace = "com.quwoquan.quwoquan_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

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

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
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

fun mergeAlphaLocalDartDefines(encoded: String?): String {
    val defines = decodeDartDefines(encoded)
    val valuesByKey = defines
        .mapNotNull { define ->
            val separator = define.indexOf("=")
            if (separator <= 0) null else define.substring(0, separator) to define.substring(separator + 1)
        }
        .toMap()
    val runtimeEnv = valuesByKey["APP_RUNTIME_ENV"]?.trim()
    if (!runtimeEnv.isNullOrEmpty() && runtimeEnv != "alpha") {
        return encoded ?: ""
    }
    val existingKeys = valuesByKey.keys.toMutableSet()
    for ((key, value) in alphaLocalDefaultDartDefines) {
        if (existingKeys.add(key)) {
            defines.add("$key=$value")
        }
    }
    return encodeDartDefines(defines)
}

tasks.withType<FlutterTask>().configureEach {
    if (
        name.contains("Debug", ignoreCase = true) ||
            name.contains("Profile", ignoreCase = true)
    ) {
        dartDefines = mergeAlphaLocalDartDefines(dartDefines)
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
                alphaLocalCaCert
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

tasks.matching { task ->
    task.name == "preDebugBuild" || task.name == "preProfileBuild"
}.configureEach {
    dependsOn(prepareAndroidLocalAlphaStack)
    dependsOn(prepareAndroidLocalAdbReverse)
    dependsOn(prepareLocalEnvDebugRes)
}

val vendoredAndroidArtifactsDir =
    rootProject.file("../vendor/android_artifacts")

dependencies {
    implementation("androidx.core:core-splashscreen:1.0.1")
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
