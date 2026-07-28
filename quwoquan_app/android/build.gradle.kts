import com.android.build.gradle.LibraryExtension
import org.gradle.api.tasks.compile.JavaCompile

// FlutterFire 16.4.3 still implements FCM registration-token semantics.
// Keep the last compatible Firebase BoM until the device identity contract is
// migrated to distinguish Firebase Installation ID from registration tokens.
rootProject.extra["FlutterFire"] =
    mapOf("FirebaseSDKVersion" to "34.14.1")

val pinnedAndroidxTestArtifacts = mapOf(
    "androidx.test:runner" to "1.3.0",
    "androidx.test:rules" to "1.2.0",
    "androidx.test.espresso:espresso-core" to "3.3.0",
)
val warningCleanJavaModules =
    setOf("app", "firebase_messaging", "flutter_webrtc", "video_thumbnail")
val java8CompatibilityModules = setOf("flutter_webrtc", "video_thumbnail")

allprojects {
    repositories {
        google()
        mavenCentral()
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
            if (
                requested.group == "com.google.firebase" &&
                    requested.name == "firebase-common"
            ) {
                useVersion("22.1.0")
                because(
                    "firebase_core 4.12.1 compiles against FirebaseOptions reCAPTCHA APIs " +
                        "introduced after the 34.14.1 BoM firebase-common constraint.",
                )
                return@eachDependency
            }
            if (
                requested.group == "com.google.firebase" &&
                    requested.name == "firebase-messaging"
            ) {
                useVersion("25.0.2")
                because(
                    "FlutterFire 16.4.3 still exposes registration-token semantics; " +
                        "FCM 25.1.0 requires an explicit FID contract migration.",
                )
                return@eachDependency
            }
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

subprojects {
    if (name == "firebase_messaging") {
        val upstreamSourceDir = projectDir.resolve("src/main/java")
        val overlayScript =
            rootProject.projectDir.parentFile.resolve(
                "vendor/patches/firebase_messaging/prepare_android_sources.py",
            )
        val patchedSourceDir =
            rootProject.layout.buildDirectory.dir("firebase_messaging_patched_android/java")
        val preparePatchedFirebaseMessagingSources =
            tasks.register<Exec>("preparePatchedFirebaseMessagingSources") {
                inputs.dir(upstreamSourceDir)
                inputs.file(overlayScript)
                outputs.dir(patchedSourceDir)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(
                    "python3",
                    overlayScript.absolutePath,
                    "--source",
                    upstreamSourceDir.absolutePath,
                    "--output",
                    patchedSourceDir.get().asFile.absolutePath,
                )
            }
        plugins.withId("com.android.library") {
            extensions.configure<LibraryExtension> {
                sourceSets.getByName("main").java.setSrcDirs(
                    listOf(patchedSourceDir.get().asFile),
                )
            }
            tasks.withType<JavaCompile>().configureEach {
                dependsOn(preparePatchedFirebaseMessagingSources)
            }
            // AGP's annotation extractor reads the configured Java source set
            // directly rather than through JavaCompile, so it must declare the
            // generated overlay producer as well (Gradle validation is strict
            // about this implicit dependency).
            tasks.matching {
                it.name.startsWith("extract") && it.name.endsWith("Annotations")
            }.configureEach {
                dependsOn(preparePatchedFirebaseMessagingSources)
            }
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
