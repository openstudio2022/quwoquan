import java.io.File

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// trust envelope 的 assets 准入校验与生产 Runner 共用同一份脚本：宿主装进 APK 的 trust
// envelope 与生产 App 受同一组判否约束，否则「宿主起得来」证明不了生产启动路径。
apply(from = rootProject.file("../../../android/gradle/runtime-config-assets.gradle.kts"))
val externalAndroidRuntimeConfigAssetRoot = extra["qwqRuntimeConfigAssetRoot"] as File?

android {
    namespace = "com.quwoquan.testhost.patrol"
    // 与生产工程同构：宿主消费同一套插件（flutter_secure_storage 11 / permission_handler 13
    // 要求 37），且 sdkmanager 发布的 platforms/android-37 其 ApiLevel 为 37.1，必须显式给出
    // minor 才能解析到与生产一致的 platform。
    compileSdk = maxOf(flutter.compileSdkVersion, 37)
    compileSdkMinor = 0
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.quwoquan.testhost.patrol"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        testInstrumentationRunner = "pl.leancode.patrol.PatrolJUnitRunner"
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    externalAndroidRuntimeConfigAssetRoot?.let { externalAssetRoot ->
        sourceSets.getByName("main").assets.srcDir(externalAssetRoot)
    }

    // UAT 宿主与生产 App 共编译同一份 runtime config 供给面，而不是维护副本：宿主读到的
    // package 必须与生产 App 出自同一实现，否则页面 suite 证明不了生产启动路径。
    // 该供给面被物理隔离为生产源树下的独立 source root，因此这里纳入的就是它的完整闭包，
    // 不会牵入生产包其余部分（依赖微信、支付宝等本宿主不具备的 SDK）。
    sourceSets {
        getByName("main") {
            java.srcDir("../../../../android/app/src/runtimeConfigShared/java")
        }
    }
}

dependencies {
    // 与生产 app/build.gradle.kts 同版本：共编译的 store 用 tink 验签、gson 解析 package。
    implementation("com.google.crypto.tink:tink-android:1.23.0")
    implementation("com.google.code.gson:gson:2.13.2")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
