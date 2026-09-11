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
//
// Debug-nonprod 构建期自供给（REQ-003 build_time_self_supply）：
// QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT 缺席且本次请求只含 nonprod debug artifact task 时，
// 以当前源码树调用 canonical handoff builder 签发独立 Alpha offline bootstrap + nonprod
// trust，物化到源码树外的私有目录并只挂到 debug source set；其余 buildMode/buildProfile
// 缺外部注入仍以 trust blocker fail-closed。

val declaredRepositoryRoot =
    (project.findProperty("qwq.repositoryRoot") as String?)?.trim().orEmpty()
require(declaredRepositoryRoot.isNotEmpty()) {
    "GATE_BLOCK: gradle property qwq.repositoryRoot must be declared by this Gradle root"
}
val repositoryRoot = rootProject.projectDir.resolve(declaredRepositoryRoot).canonicalFile

val configuredAssetRoot =
    System.getenv("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT")?.trim().orEmpty()

val SELF_SUPPLY_REQUEST_FILE_NAME = "runtime-config-self-supply-request.json"
val SELF_SUPPLY_MODE = "build_time_self_supply"
val SELF_SUPPLY_BUILD_PROFILE = "nonprod"
val SELF_SUPPLY_VARIANT_TOKEN = "nonproddebug"

fun explicitTaskSelectorsEarly(rawArguments: List<String>): List<String> {
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

fun requiresRuntimeConfigTrustEarly(taskName: String): Boolean {
    val normalized = taskName.lowercase()
    if (normalized.contains("unittest")) {
        return false
    }
    return listOf("assemble", "bundle", "package", "install", "connected", "device", "publish", "upload")
        .any(normalized::startsWith)
}

// 自供给只在“显式请求的 artifact task 全部属于 nonprod debug 变体”时启用：
// 同一次调用夹带任何 Release/Profile/prod 制品都回到 fail-closed。
val selfSupplyEligible: Boolean =
    configuredAssetRoot.isEmpty() &&
        run {
            val artifactSelectors =
                explicitTaskSelectorsEarly(gradle.startParameter.taskNames)
                    .map { it.substringAfterLast(':') }
                    .filter(::requiresRuntimeConfigTrustEarly)
            artifactSelectors.isNotEmpty() &&
                artifactSelectors.all { it.lowercase().contains(SELF_SUPPLY_VARIANT_TOKEN) }
        }

fun resolveSelfSupplyPython(): String {
    val resolver = repositoryRoot.resolve("quwoquan_app/scripts/ios/build_resolve_stackctl_python.sh")
    val process =
        ProcessBuilder("bash", resolver.path)
            .redirectErrorStream(false)
            .start()
    val output = process.inputStream.bufferedReader().readText().trim()
    val errors = process.errorStream.bufferedReader().readText().trim()
    if (process.waitFor() != 0 || output.isEmpty()) {
        throw GradleException(
            "GATE_BLOCK: build-time self supply requires Python 3.10+ with PyYAML. $errors",
        )
    }
    return output
}

fun materializeSelfSupply(): File {
    // 源码树外、按项目路径隔离的私有目录；每次构建先清空再重生成，不缓存材料。
    val projectKey =
        MessageDigest.getInstance("SHA-256")
            .digest(rootProject.projectDir.canonicalPath.toByteArray())
            .joinToString("") { byte -> "%02x".format(byte) }
            .take(16)
    val root = File(System.getProperty("java.io.tmpdir"), "qwq-android-self-supply/$projectKey").canonicalFile
    if (root.toPath().startsWith(repositoryRoot.toPath())) {
        throw GradleException("GATE_BLOCK: self supply material root must stay outside the source tree.")
    }
    root.deleteRecursively()
    val runtimeRoot = root.resolve("qwq_runtime")
    if (!runtimeRoot.mkdirs()) {
        throw GradleException("GATE_BLOCK: self supply material root could not be created.")
    }
    // canonical handoff builder 要求输出目录仅属主可访问（与 launcher 私有材料同一约束）。
    val privateDirectory = java.nio.file.attribute.PosixFilePermissions.fromString("rwx------")
    for (directory in listOf(root.parentFile, root, runtimeRoot)) {
        Files.setPosixFilePermissions(directory.toPath(), privateDirectory)
    }
    val python = resolveSelfSupplyPython()
    val builder = repositoryRoot.resolve("quwoquan_app/scripts/device/build_self_supply_request.py")
    val process =
        ProcessBuilder(
            python,
            builder.path,
            "--trust-output",
            runtimeRoot.resolve("runtime-config-trust.json").path,
            "--request-output",
            runtimeRoot.resolve(SELF_SUPPLY_REQUEST_FILE_NAME).path,
        )
            .directory(repositoryRoot)
            .apply {
                environment()["PYTHONDONTWRITEBYTECODE"] = "1"
                environment()["PYTHONPATH"] =
                    listOfNotNull(repositoryRoot.path, System.getenv("PYTHONPATH")?.takeIf { it.isNotEmpty() })
                        .joinToString(File.pathSeparator)
            }
            .start()
    val summary = process.inputStream.bufferedReader().readText().trim()
    val errors = process.errorStream.bufferedReader().readText().trim()
    if (process.waitFor() != 0) {
        throw GradleException(
            "GATE_BLOCK: Debug-nonprod build-time self supply failed. $errors",
        )
    }
    logger.lifecycle("[android-runtime-config] runtimeConfigSupplyMode=$SELF_SUPPLY_MODE $summary")
    return root
}

val selfSupplyAssetRoot: File? = if (selfSupplyEligible) materializeSelfSupply() else null

val resolvedAssetRoot: File? =
    configuredAssetRoot.takeIf { it.isNotEmpty() }?.let(::File)?.canonicalFile ?: selfSupplyAssetRoot

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

fun generatedTrustBlocker(generatedContract: Map<String, Any?>): String {
    val launchBlockers = generatedContract["launchBlockers"] as? Map<String, Any?>
        ?: throw GradleException("GATE_BLOCK: generated launchBlockers projection is missing.")
    return launchBlockers.keys.singleOrNull { it.endsWith(".runtime_config_trust_missing") }
        ?: throw GradleException(
            "GATE_BLOCK: generated runtime-config trust blocker projection is missing.",
        )
}

@Suppress("UNCHECKED_CAST")
fun validateRuntimeConfigTrust(
    generatedContract: Map<String, Any?>,
    assetRootDeclaration: String,
    selfSupply: Boolean = false,
) {
    val blocker = generatedTrustBlocker(generatedContract)
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

    if (assetRootDeclaration.isEmpty()) {
        reject("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT is absent.")
    }
    val configuredRoot = File(assetRootDeclaration)
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
    val selfSupplyRequestFile = runtimeRoot.resolve(SELF_SUPPLY_REQUEST_FILE_NAME)
    // canonical 外部注入只嵌 trust envelope；自供给另嵌一份待激活请求。可读 runtime
    // package 都不得进入产物。
    val expectedAssetNames =
        if (selfSupply) setOf("runtime-config-trust.json", SELF_SUPPLY_REQUEST_FILE_NAME)
        else setOf("runtime-config-trust.json")
    if (!runtimeRoot.isDirectory ||
        Files.isSymbolicLink(runtimeRoot.toPath()) ||
        runtimeRoot.listFiles()?.map { it.name }?.toSet() != expectedAssetNames
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
    // 外部注入以 launcher 导出的 QWQ_APP_BUILD_PROFILE 为准；自供给只允许 nonprod 且由变体
    // 判定（raw flutter run 不带该环境变量）。
    val selectedBuildProfile =
        if (selfSupply) SELF_SUPPLY_BUILD_PROFILE
        else System.getenv("QWQ_APP_BUILD_PROFILE")?.trim().orEmpty()
    if (selfSupply) {
        if (!Files.isRegularFile(selfSupplyRequestFile.toPath(), LinkOption.NOFOLLOW_LINKS) ||
            Files.isSymbolicLink(selfSupplyRequestFile.toPath()) ||
            selfSupplyRequestFile.length() !in 1..(1024 * 1024)
        ) {
            reject("The Android build-time self supply request is missing or invalid.")
        }
        val request =
            try {
                JsonSlurper().parse(selfSupplyRequestFile) as? Map<String, Any?>
            } catch (_: Exception) {
                null
            } ?: reject("The Android build-time self supply request is malformed.")
        val requestManifest = request["effectiveLaunchManifest"] as? Map<String, Any?>
        val requestSchema = schemas["runtime_config_activation_request"] as? Map<String, Any?>
        if (request["schema"] != requestSchema?.get("schema_value") ||
            request["buildProfile"] != SELF_SUPPLY_BUILD_PROFILE ||
            request["expectedActiveDigest"] != "" ||
            requestManifest?.get("runtimeConfigSupplyMode") != SELF_SUPPLY_MODE ||
            requestManifest?.get("contentSource") != "bundled_snapshot" ||
            (request["package"] as? Map<*, *>)?.get("schema") !=
                (schemas["offline_bootstrap_document"] as? Map<*, *>)?.get("schema_value")
        ) {
            reject("The Android build-time self supply request identity conflicts with the debug build.")
        }
    }
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
        val contract =
            requireNotNull(generatedContract) {
                "artifact tasks must consume the generated App launch contract"
            }
        if (selfSupplyAssetRoot != null) {
            // 自供给只挂到 debug source set：task graph 里若混入非 nonprod debug 制品，
            // 说明配置期判定与实际图不一致，按 fail-closed 处理。
            val foreign = artifactTasks.filterNot { it.name.lowercase().contains(SELF_SUPPLY_VARIANT_TOKEN) }
            if (foreign.isNotEmpty()) {
                throw GradleException(
                    "GATE_BLOCK: ${generatedTrustBlocker(contract)}: build-time self supply only serves " +
                        "nonprod debug artifacts; ${foreign.map { it.path }} require a canonical handoff.",
                )
            }
            validateRuntimeConfigTrust(contract, selfSupplyAssetRoot.path, selfSupply = true)
        } else {
            validateRuntimeConfigTrust(contract, configuredAssetRoot)
        }
    }
}

project.extra["qwqRuntimeConfigAssetRoot"] = resolvedAssetRoot
project.extra["qwqRuntimeConfigSelfSupply"] = selfSupplyAssetRoot != null
