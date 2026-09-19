import com.android.build.gradle.LibraryExtension
import org.gradle.api.tasks.compile.JavaCompile

val pinnedAndroidxTestArtifacts = mapOf(
    "androidx.test:runner" to "1.3.0",
    "androidx.test:rules" to "1.2.0",
    "androidx.test.espresso:espresso-core" to "3.3.0",
)
val warningCleanJavaModules =
    setOf("app", "flutter_webrtc", "video_thumbnail")
val java8CompatibilityModules = setOf("flutter_webrtc", "video_thumbnail")

// 官方 Google/Maven Central 是坐标权威来源；阿里镜像只作网络 fallback。Gradle 按声明顺序
// 解析，避免镜像 TLS 故障阻断官方源可满足的 production package 依赖。
val mirroredMavenRepositories =
    listOf(
        "https://maven.aliyun.com/repository/google",
        "https://maven.aliyun.com/repository/public",
        "https://maven.aliyun.com/repository/gradle-plugin",
    )

allprojects {
    repositories {
        google()
        mavenCentral()
        mirroredMavenRepositories.forEach { maven(url = it) }
    }
    buildscript {
        repositories {
            google()
            mavenCentral()
            gradlePluginPortal()
            mirroredMavenRepositories.forEach { maven(url = it) }
        }
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    if (name in warningCleanJavaModules) {
        tasks.withType<JavaCompile>().configureEach {
            options.compilerArgs.addAll(
                listOf("-Xlint:deprecation", "-Xlint:unchecked", "-Werror"),
            )
            if (project.name in java8CompatibilityModules) {
                // These vendored plugins stay on Java 8 bytecode for their
                // Android compatibility floor. JDK 21 warns about that target
                // even when the plugin sources themselves are warning-clean.
                options.compilerArgs.add("-Xlint:-options")
            }
        }
    }
}
subprojects {
    configurations.configureEach {
        resolutionStrategy.eachDependency {
            val requestedId = "${requested.group}:${requested.name}"
            val pinnedVersion =
                pinnedAndroidxTestArtifacts[requestedId] ?: return@eachDependency
            if (requested.version?.contains('+') == true) {
                useVersion(pinnedVersion)
                because(
                    "Flutter integration_test still requests dynamic androidx.test versions, which makes debug builds flaky when Maven metadata TLS handshakes fail.",
                )
            }
        }
    }
}
subprojects {
    project.evaluationDependsOn(":app")
}


tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
