val pinnedAndroidxTestArtifacts = mapOf(
    "androidx.test:runner" to "1.3.0",
    "androidx.test:rules" to "1.2.0",
    "androidx.test.espresso:espresso-core" to "3.3.0",
)

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
