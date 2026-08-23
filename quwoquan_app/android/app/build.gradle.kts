@file:Suppress("DEPRECATION")

import com.flutter.gradle.tasks.FlutterTask
import groovy.json.JsonSlurper
import java.io.File
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.util.Base64

plugins {
    id("com.android.application")
    id("dev.flutter.flutter-gradle-plugin")
}

data class AppIdentityProjection(
    val applicationId: String,
    val displayName: String,
)

@Suppress("UNCHECKED_CAST")
val generatedAppIdentity =
    JsonSlurper().parse(projectDir.resolve("app_identity.generated.json")) as Map<String, Any?>
val generatedIdentityBuildProfiles =
    (generatedAppIdentity["buildProfiles"] as? List<*>)
        ?.map { it.toString() }
        .orEmpty()
val generatedEnvironmentProfiles =
    (generatedAppIdentity["environmentProfiles"] as? Map<*, *>)
        ?.entries
        ?.associate { entry -> entry.key.toString() to entry.value.toString() }
        .orEmpty()
val generatedAndroidIdentities =
    ((generatedAppIdentity["identities"] as? Map<*, *>)?.get("android") as? Map<*, *>)
        ?.entries
        ?.associate { entry ->
            val value = entry.value as Map<*, *>
            entry.key.toString() to AppIdentityProjection(
                applicationId = value["applicationId"].toString(),
                displayName = value["displayName"].toString(),
            )
        }
        .orEmpty()
check(generatedIdentityBuildProfiles == listOf("nonprod", "prod")) {
    "GATE_BLOCK: generated App identity buildProfile matrix is incomplete"
}
check(
    generatedEnvironmentProfiles ==
        mapOf(
            "alpha" to "nonprod",
            "beta" to "nonprod",
            "gamma" to "nonprod",
            "prod" to "prod",
        ),
) {
    "GATE_BLOCK: generated App identity environmentProfiles mapping is incomplete"
}

val requestedAppTasks =
    gradle.startParameter.taskNames.map { task -> task.substringAfterLast(':') }
val requestedBuildProfiles =
    requestedAppTasks
        .asSequence()
        .mapNotNull { task ->
            val taskName = task.lowercase()
            when {
                Regex("(^|[^a-z])nonprod([^a-z]|$)").containsMatchIn(taskName) -> "nonprod"
                Regex("(^|[^a-z])prod([^a-z]|$)").containsMatchIn(taskName) -> "prod"
                taskName.contains("nonprod") -> "nonprod"
                taskName.contains("prod") && !taskName.contains("nonprod") -> "prod"
                else -> null
            }
        }
        .distinct()
        .toList()
check(requestedBuildProfiles.size <= 1) {
    "GATE_BLOCK: one Android invocation must select exactly one buildProfile."
}
val googleServicesConfig = projectDir.resolve("google-services.json")
val releaseKeystorePath = System.getenv("QWQ_ANDROID_RELEASE_KEYSTORE_PATH")?.trim().orEmpty()
val releaseKeystorePassword = System.getenv("QWQ_ANDROID_RELEASE_STORE_PASSWORD")?.trim().orEmpty()
val releaseKeyAlias = System.getenv("QWQ_ANDROID_RELEASE_KEY_ALIAS")?.trim().orEmpty()
val releaseKeyPassword = System.getenv("QWQ_ANDROID_RELEASE_KEY_PASSWORD")?.trim().orEmpty()
fun appIdentity(buildProfile: String, buildMode: String): AppIdentityProjection =
    generatedAndroidIdentities["$buildProfile/$buildMode"]
        ?: throw GradleException(
            "GATE_BLOCK: generated App identity is missing for $buildProfile/$buildMode",
        )

fun generatedModeApplicationIdSuffix(
    buildProfile: String,
    buildMode: String,
): String {
    val releaseId = appIdentity(buildProfile, "release").applicationId
    val modeId = appIdentity(buildProfile, buildMode).applicationId
    check(modeId.startsWith(releaseId)) {
        "GATE_BLOCK: generated Android $buildProfile/$buildMode identity does not extend release identity"
    }
    return modeId.removePrefix(releaseId)
}

fun generatedModeDisplayMark(
    buildProfile: String,
    buildMode: String,
): String {
    val releaseName = appIdentity(buildProfile, "release").displayName
    val modeName = appIdentity(buildProfile, buildMode).displayName
    check(modeName.startsWith(releaseName)) {
        "GATE_BLOCK: generated Android $buildProfile/$buildMode display name does not extend release display name"
    }
    return modeName.removePrefix(releaseName)
}

generatedIdentityBuildProfiles.forEach { buildProfile ->
    generatedModeApplicationIdSuffix(buildProfile, "debug")
    generatedModeApplicationIdSuffix(buildProfile, "profile")
    generatedModeDisplayMark(buildProfile, "debug")
    generatedModeDisplayMark(buildProfile, "profile")
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
        "QWQ_LAUNCH_TARGET",
        "APP_LAUNCH_TARGET",
        "APP_LAUNCH_POLICY",
    )
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
val configuredAndroidRuntimeConfigAssetRoot =
    System.getenv("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT")?.trim().orEmpty()
val externalAndroidRuntimeConfigAssetRoot =
    configuredAndroidRuntimeConfigAssetRoot.takeIf { it.isNotEmpty() }?.let { configured ->
        val root = File(configured)
        check(root.isAbsolute) {
            "GATE_BLOCK: Android runtime configuration asset root must be absolute"
        }
        val canonicalRoot = root.canonicalFile
        val repositoryRoot = projectDir.resolve("../../..").canonicalFile
        check(!canonicalRoot.toPath().startsWith(repositoryRoot.toPath())) {
            "GATE_BLOCK: Android runtime configuration asset root must stay outside the source tree"
        }
        check(
            canonicalRoot.isDirectory &&
                !Files.isSymbolicLink(root.toPath()) &&
                canonicalRoot.listFiles()?.map { it.name }?.toSet() == setOf("qwq_runtime"),
        ) {
            "GATE_BLOCK: Android runtime configuration asset root must contain only qwq_runtime"
        }
        val runtimeRoot = canonicalRoot.resolve("qwq_runtime")
        val trustFile = runtimeRoot.resolve("runtime-config-trust.json")
        val packageFile = runtimeRoot.resolve("runtime-config-package.json")
        check(
            runtimeRoot.isDirectory &&
                !Files.isSymbolicLink(runtimeRoot.toPath()) &&
                runtimeRoot.listFiles()?.map { it.name }?.toSet() ==
                setOf("runtime-config-trust.json"),
        ) {
            "GATE_BLOCK: target runtime package must not enter Android assets"
        }
        check(
            Files.isRegularFile(trustFile.toPath(), LinkOption.NOFOLLOW_LINKS) &&
                !Files.isSymbolicLink(trustFile.toPath()) &&
                trustFile.length() in 1..(1024 * 1024) &&
                !packageFile.exists(),
        ) {
            "GATE_BLOCK: Android build-profile trust asset is missing or invalid"
        }
        @Suppress("UNCHECKED_CAST")
        val trust = JsonSlurper().parse(trustFile) as? Map<String, Any?>
        val selectedBuildProfile = System.getenv("QWQ_APP_BUILD_PROFILE")?.trim().orEmpty()
        check(
            trust != null &&
                trust.keys ==
                setOf(
                    "schema",
                    "schemaVersion",
                    "buildProfile",
                    "signatureAlgorithm",
                    "trustedPublicKeys",
                ) &&
                trust["schema"] == "app-runtime-config-trust" &&
                trust["schemaVersion"] == "1" &&
                trust["buildProfile"] == selectedBuildProfile &&
                trust["signatureAlgorithm"] == "ed25519" &&
                (trust["trustedPublicKeys"] as? Map<*, *>)?.isNotEmpty() == true,
        ) {
            "GATE_BLOCK: Android runtime trust envelope conflicts with the selected build profile"
        }
        canonicalRoot
    }
androidComponents {
    beforeVariants { variantBuilder ->
        val buildProfile =
            variantBuilder.productFlavors
                .firstOrNull { (dimension, _) -> dimension == "buildProfile" }
                ?.second
        if (variantBuilder.buildType in setOf("debug", "profile") && buildProfile != "nonprod") {
            variantBuilder.enable = false
        }
    }
}

android {
    namespace = "com.quwoquan.quwoquan_app"
    // Flutter 3.47 默认 compileSdk 36；flutter_secure_storage 11 / permission_handler 13
    // 要求 37。插件 compileSdk 高于工程时，把工程抬到最高值（不改 targetSdk）。
    // sdkmanager 发布的是 platforms/android-37.0（ApiLevel=37.0），AGP 8.11 需 minor=0。
    compileSdk = maxOf(flutter.compileSdkVersion, 37)
    compileSdkMinor = 0
    ndkVersion = flutter.ndkVersion
    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // Patrol/AndroidX Test 依赖在产品 minSdk 上使用 Java 8+ API，需要 desugaring。
        isCoreLibraryDesugaringEnabled = true
    }

    externalAndroidRuntimeConfigAssetRoot?.let { externalAssetRoot ->
        sourceSets.getByName("main").assets.srcDir(externalAssetRoot)
    }

    flavorDimensions += "buildProfile"
    productFlavors {
        generatedIdentityBuildProfiles.forEach { buildProfile ->
            create(buildProfile) {
                dimension = "buildProfile"
                val releaseIdentity = appIdentity(buildProfile, "release")
                applicationId = releaseIdentity.applicationId
                manifestPlaceholders["qwqAppLabel"] = releaseIdentity.displayName
                manifestPlaceholders["qwqDebugModeLabel"] =
                    generatedModeDisplayMark(buildProfile, "debug")
                manifestPlaceholders["qwqProfileModeLabel"] =
                    generatedModeDisplayMark(buildProfile, "profile")
            }
        }
    }

    defaultConfig {
        manifestPlaceholders["qwqModeLabel"] = ""
        manifestPlaceholders["qwqDebugModeLabel"] = ""
        manifestPlaceholders["qwqProfileModeLabel"] = ""
        // 产品安装下限跟随 Flutter SDK（DEC-006）：能下探就下探。
        // 对应 Android 正式发布须已满五年；未满五年时不得人为或跟随 SDK 上浮。
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
        // 生产 App 只保留原生 Gate runner；Patrol instrumentation 属于独立 test host。
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
        debug {
            applicationIdSuffix = generatedModeApplicationIdSuffix("nonprod", "debug")
            manifestPlaceholders["qwqModeLabel"] = "\${qwqDebugModeLabel}"
        }
        release {
            manifestPlaceholders["qwqModeLabel"] = ""
            signingConfig = signingConfigs.findByName("officialRelease")
        }
        // Debug/Profile 变体只允许 nonprod；Prod 仅保留 Release。
        findByName("profile")?.apply {
            applicationIdSuffix = generatedModeApplicationIdSuffix("nonprod", "profile")
            manifestPlaceholders["qwqModeLabel"] = "\${qwqProfileModeLabel}"
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

fun forbiddenRuntimeDartDefineKeys(encoded: String?): List<String> =
    decodeDartDefines(encoded)
        .mapNotNull { define -> define.substringBefore("=", "").ifEmpty { null } }
        .filter { it in nativeRuntimeDefineKeys }
        .distinct()
        .sorted()

afterEvaluate {
    tasks.withType<FlutterTask>().configureEach {
        doFirst {
            val forbiddenKeys = forbiddenRuntimeDartDefineKeys(dartDefines)
            check(forbiddenKeys.isEmpty()) {
                "GATE_BLOCK: Android compilation must not consume runtime environment, " +
                    "endpoint, launch policy, or target dart-defines: " +
                    forbiddenKeys.joinToString(", ")
            }
        }
    }
}

val vendoredAndroidArtifactsDir =
    rootProject.file("../vendor/android_artifacts")

dependencies {
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("com.google.crypto.tink:tink-android:1.23.0")
    implementation("com.google.code.gson:gson:2.13.2")
    // 原生视频编辑（trim/mute 导出）：media3 Transformer，与 iOS AVFoundation
    // 桥共用 quwoquan/video_editing channel 契约。
    implementation("androidx.media3:media3-transformer:1.4.1")
    implementation("androidx.media3:media3-common:1.4.1")
    implementation("androidx.media3:media3-effect:1.4.1")
    implementation("com.google.android.gms:play-services-auth-api-phone:18.3.1")
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
    testImplementation("junit:junit:4.13.2")
    // Keep versions aligned with Patrol's strict AndroidX test resolution.
    androidTestImplementation("androidx.test:runner:1.5.1")
    androidTestImplementation("androidx.test:rules:1.2.0")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.0")
    androidTestUtil("androidx.test:orchestrator:1.5.1")
}
