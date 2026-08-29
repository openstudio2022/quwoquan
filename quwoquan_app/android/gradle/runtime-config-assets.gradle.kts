import groovy.json.JsonSlurper
import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.security.MessageDigest
import java.util.Base64

// runtime config trust envelope 进入 Android assets 的唯一准入校验。
//
// 生产 Runner 与 Patrol UAT test host 两个 Gradle 工程 apply 同一份：宿主装进 APK 的
// trust envelope 必须与生产 App 受同一组判否约束，否则「宿主起得来」证明不了生产启动路径。
// 校验产出经 extra 交给主脚本，主脚本只负责把结果挂成 assets srcDir。
//
// 仓库根由消费方 Gradle 根显式声明（qwq.repositoryRoot），不按固定相对深度推断：
// 两个工程到仓库根的深度不同，而「assets 根必须在源码树外」这条判否依赖它。

val declaredRepositoryRoot =
    (project.findProperty("qwq.repositoryRoot") as String?)?.trim().orEmpty()
require(declaredRepositoryRoot.isNotEmpty()) {
    "GATE_BLOCK: gradle property qwq.repositoryRoot must be declared by this Gradle root"
}
val repositoryRoot = rootProject.projectDir.resolve(declaredRepositoryRoot).canonicalFile

val configuredAssetRoot =
    System.getenv("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT")?.trim().orEmpty()
val resolvedAssetRoot =
    configuredAssetRoot.takeIf { it.isNotEmpty() }?.let(::File)?.canonicalFile

fun requiresRuntimeConfigTrust(taskName: String): Boolean {
    val normalized = taskName.lowercase()
    if (normalized.contains("unittest")) {
        return false
    }
    return listOf(
        "assemble",
        "bundle",
        "package",
        "install",
        "connected",
        "device",
        "publish",
        "upload",
    ).any(normalized::startsWith)
}

fun isExplicitPureUnitTestRequest(taskPath: String): Boolean {
    val taskName = taskPath.substringAfterLast(':').lowercase()
    return taskName == "test" ||
        (taskName.startsWith("test") && taskName.contains("unittest"))
}

fun explicitTaskSelectors(rawArguments: List<String>): List<String> {
    val selectors = mutableListOf<String>()
    var skipNextValue = false
    rawArguments.forEach { argument ->
        if (skipNextValue) {
            skipNextValue = false
        } else if (argument == "--tests") {
            skipNextValue = true
        } else if (!argument.startsWith("-")) {
            selectors.add(argument)
        }
    }
    return selectors
}

fun consumesGeneratedLaunchContract(taskName: String): Boolean {
    val normalized = taskName.lowercase()
    return listOf(
        "assemble",
        "bundle",
        "check",
        "compile",
        "connected",
        "device",
        "install",
        "lint",
        "package",
        "publish",
        "test",
        "upload",
    ).any(normalized::startsWith)
}

@Suppress("UNCHECKED_CAST")
fun loadGeneratedLaunchContract(): Map<String, Any?> {
    val contractFile =
        repositoryRoot.resolve(
            "quwoquan_app/tool/app_launch_contract_codegen/app_launch_contract.generated.json",
        )
    if (!contractFile.isFile) {
        throw GradleException(
            "GATE_BLOCK: generated App launch contract is missing; run the canonical " +
                "app-launch-contract codegen before producing an Android artifact.",
        )
    }
    val generatedManifestFile =
        repositoryRoot.resolve(
            "quwoquan_app/tool/app_launch_contract_codegen/generated_manifest.json",
        )
    if (!generatedManifestFile.isFile) {
        throw GradleException(
            "GATE_BLOCK: generated App launch contract freshness manifest is missing; run the " +
                "canonical app-launch-contract codegen before producing an Android artifact.",
        )
    }
    val generatedManifest =
        try {
            JsonSlurper().parse(generatedManifestFile) as? Map<String, Any?>
        } catch (_: Exception) {
            null
        } ?: throw GradleException(
            "GATE_BLOCK: generated App launch contract freshness manifest is malformed.",
        )
    val declaredFiles =
        listOf("inputs", "outputs").flatMap { section ->
            (generatedManifest[section] as? List<*>)
                ?.mapNotNull { item -> item as? Map<String, Any?> }
                .orEmpty()
        }
    if (declaredFiles.isEmpty()) {
        throw GradleException(
            "GATE_BLOCK: generated App launch contract freshness manifest has no inputs/outputs.",
        )
    }
    declaredFiles.forEach { declaration ->
        val relativePath = declaration["path"]?.toString().orEmpty()
        val expectedDigest = declaration["sha256"]?.toString().orEmpty()
        val source = repositoryRoot.resolve(relativePath).canonicalFile
        if (relativePath.isEmpty() || File(relativePath).isAbsolute ||
            !source.toPath().startsWith(repositoryRoot.toPath())
        ) {
            throw GradleException(
                "GATE_BLOCK: generated App launch contract manifest contains an illegal path.",
            )
        }
        val actualDigest =
            if (source.isFile) {
                val digest = MessageDigest.getInstance("SHA-256").digest(source.readBytes())
                "sha256:" + digest.joinToString("") { byte -> "%02x".format(byte) }
            } else {
                ""
            }
        if (actualDigest != expectedDigest) {
            throw GradleException(
                "GATE_BLOCK: generated App launch contract is stale at $relativePath; run the " +
                    "canonical app-launch-contract codegen before producing an Android artifact.",
            )
        }
    }
    return (JsonSlurper().parse(contractFile) as? Map<String, Any?>)
        ?: throw GradleException(
            "GATE_BLOCK: generated App launch contract is malformed; regenerate it before " +
                "producing an Android artifact.",
        )
}

@Suppress("UNCHECKED_CAST")
fun validateRuntimeConfigTrust(generatedContract: Map<String, Any?>) {
    val launchBlockers = generatedContract["launchBlockers"] as? Map<String, Any?>
        ?: throw GradleException("GATE_BLOCK: generated launchBlockers projection is missing.")
    val blocker =
        launchBlockers.keys.singleOrNull { it.endsWith(".runtime_config_trust_missing") }
            ?: throw GradleException(
                "GATE_BLOCK: generated runtime-config trust blocker projection is missing.",
            )
    fun reject(reason: String): Nothing {
        throw GradleException(
            "GATE_BLOCK: $blocker: $reason " +
                "Launch through ./quwoquan_app/run.sh -d <device> to materialize the " +
                "build-profile trust envelope.",
        )
    }

    val appLaunchManifest = generatedContract["appLaunchManifest"] as? Map<String, Any?>
        ?: reject("The generated App launch manifest projection is missing.")
    val schemas = appLaunchManifest["schemas"] as? Map<String, Any?>
        ?: reject("The generated App launch schema projection is missing.")
    val trustSchema = schemas["runtime_config_trust_envelope"] as? Map<String, Any?>
        ?: reject("The generated runtime trust schema is missing.")
    val requiredFields =
        (trustSchema["required_fields"] as? List<*>)?.map { it.toString() }?.toSet()
            ?: reject("The generated runtime trust required fields are missing.")
    val schemaValue = trustSchema["schema_value"]?.toString()
        ?: reject("The generated runtime trust schema value is missing.")
    val fieldContracts = trustSchema["fields"] as? Map<String, Any?>
        ?: reject("The generated runtime trust field contracts are missing.")
    val signatureAlgorithm =
        (fieldContracts["signatureAlgorithm"] as? Map<String, Any?>)?.get("const")?.toString()
            ?: reject("The generated runtime trust signature algorithm is missing.")
    val trustedBuildProfiles =
        ((appLaunchManifest["runtime_config_trust"] as? Map<String, Any?>)
            ?.get("build_profiles") as? List<*>)?.map { it.toString() }?.toSet()
            ?: reject("The generated runtime trust build profiles are missing.")

    if (configuredAssetRoot.isEmpty()) {
        reject("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT is absent.")
    }
    val configuredRoot = File(configuredAssetRoot)
    if (!configuredRoot.isAbsolute) {
        reject("The Android runtime configuration asset root must be absolute.")
    }
    val canonicalRoot =
        try {
            configuredRoot.canonicalFile
        } catch (_: Exception) {
            reject("The Android runtime configuration asset root cannot be resolved.")
        }
    if (canonicalRoot.toPath().startsWith(repositoryRoot.toPath())) {
        reject("The Android runtime configuration asset root must stay outside the source tree.")
    }
    if (!canonicalRoot.isDirectory ||
        Files.isSymbolicLink(configuredRoot.toPath()) ||
        canonicalRoot.listFiles()?.map { it.name }?.toSet() != setOf("qwq_runtime")
    ) {
        reject("The Android runtime configuration asset root must contain only qwq_runtime.")
    }
    val runtimeRoot = canonicalRoot.resolve("qwq_runtime")
    val trustFile = runtimeRoot.resolve("runtime-config-trust.json")
    val packageFile = runtimeRoot.resolve("runtime-config-package.json")
    if (!runtimeRoot.isDirectory ||
        Files.isSymbolicLink(runtimeRoot.toPath()) ||
        runtimeRoot.listFiles()?.map { it.name }?.toSet() != setOf("runtime-config-trust.json")
    ) {
        reject("A target runtime package must not enter Android assets.")
    }
    if (!Files.isRegularFile(trustFile.toPath(), LinkOption.NOFOLLOW_LINKS) ||
        Files.isSymbolicLink(trustFile.toPath()) ||
        trustFile.length() !in 1..(1024 * 1024) ||
        packageFile.exists()
    ) {
        reject("The Android build-profile trust asset is missing or invalid.")
    }
    val trust =
        try {
            JsonSlurper().parse(trustFile) as? Map<String, Any?>
        } catch (_: Exception) {
            null
        } ?: reject("The Android build-profile trust envelope is malformed.")
    val selectedBuildProfile = System.getenv("QWQ_APP_BUILD_PROFILE")?.trim().orEmpty()
    if (selectedBuildProfile !in trustedBuildProfiles ||
        trust.keys != requiredFields ||
        trust["schema"] != schemaValue ||
        trust["buildProfile"] != selectedBuildProfile ||
        trust["signatureAlgorithm"] != signatureAlgorithm
    ) {
        reject("The Android runtime trust envelope conflicts with the selected build profile.")
    }
    val trustedPublicKeys = trust["trustedPublicKeys"] as? Map<*, *>
        ?: reject("The Android runtime trust keyring must be a non-empty object.")
    if (trustedPublicKeys.isEmpty()) {
        reject("The Android runtime trust keyring must be a non-empty object.")
    }
    val keyIdPattern = Regex("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    trustedPublicKeys.forEach { (rawKeyId, rawEncodedKey) ->
        val keyId = rawKeyId as? String
            ?: reject("The Android runtime trust key id must be a canonical string.")
        val encodedKey = rawEncodedKey as? String
            ?: reject("The Android runtime trust public key must be canonical base64.")
        if (!keyIdPattern.matches(keyId)) {
            reject("The Android runtime trust key id is not canonical: $keyId")
        }
        val decodedKey =
            try {
                Base64.getDecoder().decode(encodedKey)
            } catch (_: IllegalArgumentException) {
                reject("The Android runtime trust public key must be strict canonical base64.")
            }
        if (decodedKey.size != 32 ||
            Base64.getEncoder().encodeToString(decodedKey) != encodedKey
        ) {
            reject("The Android runtime trust public key must be a canonical 32-byte Ed25519 key.")
        }
    }
}

val runtimeConfigTrustConsumerProject = project
gradle.taskGraph.whenReady {
    val requestedTasks = explicitTaskSelectors(gradle.startParameter.taskNames)
    val pureUnitTestInvocation =
        requestedTasks.isNotEmpty() && requestedTasks.all(::isExplicitPureUnitTestRequest)
    val consumerTasks =
        allTasks.filter { task ->
            task.project == runtimeConfigTrustConsumerProject &&
                consumesGeneratedLaunchContract(task.name)
        }
    val generatedContract =
        if (consumerTasks.isNotEmpty()) loadGeneratedLaunchContract() else null
    val artifactTasks =
        allTasks.filter { task ->
            task.project == runtimeConfigTrustConsumerProject && requiresRuntimeConfigTrust(task.name)
        }
    logger.info(
        "[android-runtime-config] requestedTasks=$requestedTasks " +
            "pureUnitTestInvocation=$pureUnitTestInvocation " +
            "artifactTasks=${artifactTasks.map { it.path }}",
    )
    if (artifactTasks.isNotEmpty() && !pureUnitTestInvocation) {
        validateRuntimeConfigTrust(
            requireNotNull(generatedContract) {
                "artifact tasks must consume the generated App launch contract"
            },
        )
    }
}

project.extra["qwqRuntimeConfigAssetRoot"] = resolvedAssetRoot
