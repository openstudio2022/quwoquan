package com.quwoquan.quwoquan_app;

import com.google.crypto.tink.subtle.Ed25519Verify;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardCopyOption;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

final class RuntimeConfigPackageStore {
  static final String PACKAGE_FILE_NAME = "runtime-config-package.json";
  static final String TRUST_FILE_NAME = "runtime-config-trust.json";
  static final String ASSET_ROOT = "qwq_runtime";
  static final int MAX_BYTES = 1024 * 1024;
  static final String ABSENT_REASON = registeredErrorCode("runtime_config_package_missing");

  private static final String TRUST_SCHEMA =
      requiredGeneratedSchemaValue("runtime_config_trust_envelope");
  private static final String PACKAGE_SCHEMA =
      requiredGeneratedSchemaValue("runtime_config_package");
  private static final String SIGNATURE_ALGORITHM =
      AppLaunchContract.RUNTIME_CONFIG_PACKAGE_SIGNATURE_ALGORITHM;
  private static final long MAXIMUM_LIFETIME_MILLIS =
      TimeUnit.SECONDS.toMillis(AppLaunchContract.RUNTIME_CONFIG_PACKAGE_MAX_LIFETIME_SECONDS);
  private static final long MAXIMUM_FUTURE_SKEW_MILLIS =
      TimeUnit.SECONDS.toMillis(AppLaunchContract.RUNTIME_CONFIG_PACKAGE_MAX_FUTURE_SKEW_SECONDS);
  private static final Pattern DIGEST_PATTERN = Pattern.compile("^sha256:[0-9a-f]{64}$");
  private static final Pattern SOURCE_GIT_SHA_PATTERN = Pattern.compile("^[0-9a-f]{40}$");
  private static final Pattern SOURCE_TREE_DIGEST_PATTERN =
      Pattern.compile("^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$");
  private static final Pattern KEY_ID_PATTERN =
      Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$");
  private static final Pattern SECRET_KEY_PATTERN =
      Pattern.compile(
          "(secret|password|private.?key|access.?token|api.?key|credential)",
          Pattern.CASE_INSENSITIVE);
  private static final List<String> TRUST_FIELDS =
      AppLaunchContract.RUNTIME_CONFIG_TRUST_ENVELOPE_REQUIRED_FIELDS;
  private static final List<String> PACKAGE_FIELDS =
      AppLaunchContract.RUNTIME_CONFIG_PACKAGE_REQUIRED_FIELDS;
  private static final List<String> RUNTIME_FIELDS =
      AppLaunchContract.RUNTIME_CONFIG_PACKAGE_RUNTIME_REQUIRED_FIELDS;
  private static final Set<String> WEBSOCKET_RUNTIME_FIELDS =
      Set.of("realtimeBaseUrl", "rtcMediaConnectionUrl");
  private static final Set<String> RECOVERY_RUNTIME_FIELDS =
      Set.of("gatewayBaseUrl", "publicWebBaseUrl", "appDownloadBaseUrl");
  private static final Map<String, String> TARGET_ENVIRONMENTS =
      AppLaunchContract.TARGET_ENVIRONMENT;
  // canonical JSON 哈希必须与执行体侧 Python json.dumps 字节一致；GSON 默认的
  // HTML-safe 转义会把 `=`、`<`、`&` 写成 \u003d 等，导致 digest 漂移。
  private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();

  interface TrustSource {
    InputStream open() throws IOException;
  }

  interface Clock {
    Instant now();
  }

  interface AtomicWriter {
    void write(File destination, byte[] payload) throws IOException;
  }

  interface ActivationCommitter {
    void commit(ActivationResult result) throws RuntimeConfigException;
  }

  enum ReadKind {
    PRESENT,
    ABSENT,
    FAILURE
  }

  static final class ReadState {
    final ReadKind kind;
    final Map<String, Object> payload;
    final RuntimeConfigException error;

    private ReadState(ReadKind kind, Map<String, Object> payload, RuntimeConfigException error) {
      this.kind = kind;
      this.payload = payload;
      this.error = error;
    }

    static ReadState present(Map<String, Object> payload) {
      return new ReadState(ReadKind.PRESENT, payload, null);
    }

    static ReadState absent(Map<String, Object> payload) {
      return new ReadState(ReadKind.ABSENT, payload, null);
    }

    static ReadState failure(RuntimeConfigException error) {
      return new ReadState(ReadKind.FAILURE, null, error);
    }
  }

  static final class RuntimeConfigException extends Exception {
    final String code;

    RuntimeConfigException(String code) {
      super(registeredErrorCode(code));
      this.code = registeredErrorCode(code);
    }

    RuntimeConfigException(String code, Throwable cause) {
      super(registeredErrorCode(code), cause);
      this.code = registeredErrorCode(code);
    }
  }

  static final class ActivationResult {
    final String packageDigest;
    final String trustEnvelopeDigest;
    final String previousActiveDigest;

    ActivationResult(
        String packageDigest, String trustEnvelopeDigest, String previousActiveDigest) {
      this.packageDigest = packageDigest;
      this.trustEnvelopeDigest = trustEnvelopeDigest;
      this.previousActiveDigest = previousActiveDigest;
    }

  }

  private static final class WriteResult {
    final byte[] previousActivePackage;
    final File destination;

    WriteResult(byte[] previousActivePackage, File destination) {
      this.previousActivePackage = previousActivePackage;
      this.destination = destination;
    }
  }

  private static final class TrustProjection {
    final JsonObject document;
    final Map<String, String> trustedPublicKeys;
    final String digest;

    TrustProjection(JsonObject document, Map<String, String> trustedPublicKeys, String digest) {
      this.document = document;
      this.trustedPublicKeys = trustedPublicKeys;
      this.digest = digest;
    }
  }

  private static final class ActiveProjection {
    final JsonObject packageDocument;
    final TrustProjection trust;
    final String packageDigest;

    ActiveProjection(JsonObject packageDocument, TrustProjection trust, String packageDigest) {
      this.packageDocument = packageDocument;
      this.trust = trust;
      this.packageDigest = packageDigest;
    }

    Map<String, Object> flutterEnvelope() {
      Map<String, Object> envelope = new LinkedHashMap<>();
      envelope.put("package", objectMap(packageDocument));
      envelope.put("trustedBuildProfile", requiredStringUnchecked(trust.document, "buildProfile"));
      envelope.put("trustedTarget", requiredStringUnchecked(packageDocument, "target"));
      envelope.put("trustedPublicKeys", new LinkedHashMap<>(trust.trustedPublicKeys));
      return envelope;
    }

    Map<String, Object> readerEnvelope() {
      Map<String, Object> envelope = new LinkedHashMap<>();
      envelope.put("state", "present");
      envelope.put("package", objectMap(packageDocument));
      envelope.put("artifactTrustEnvelope", objectMap(trust.document));
      envelope.put("packageDigest", packageDigest);
      envelope.put("trustEnvelopeDigest", trust.digest);
      return envelope;
    }
  }

  private final File noBackupRoot;
  private final TrustSource trustSource;
  private final Clock clock;
  private final AtomicWriter atomicWriter;

  RuntimeConfigPackageStore(
      File noBackupRoot,
      TrustSource trustSource,
      Clock clock,
      AtomicWriter atomicWriter) {
    this.noBackupRoot = noBackupRoot;
    this.trustSource = trustSource;
    this.clock = clock;
    this.atomicWriter = atomicWriter;
  }

  static AtomicWriter durableAtomicWriter() {
    return RuntimeConfigPackageStore::writeDurablyAndReplace;
  }

  ReadState readState() {
    try {
      TrustProjection trust = loadTrustEnvelope();
      File activeFile = activePackageFile(false);
      if (activeFile == null) {
        Map<String, Object> absent = new LinkedHashMap<>();
        absent.put("state", "absent");
        absent.put("reason", ABSENT_REASON);
        absent.put("artifactTrustEnvelope", objectMap(trust.document));
        absent.put("trustEnvelopeDigest", trust.digest);
        return ReadState.absent(absent);
      }
      JsonObject packageDocument = decodeDocument(readFile(activeFile), "runtime_config_package_malformed");
      ActiveProjection active = validatePackage(packageDocument, trust, null);
      return ReadState.present(active.readerEnvelope());
    } catch (RuntimeConfigException error) {
      return ReadState.failure(error);
    }
  }

  Map<String, Object> readStateEnvelope() {
    ReadState state = readState();
    if (state.kind != ReadKind.FAILURE) {
      return state.payload;
    }
    Map<String, Object> failure = new LinkedHashMap<>();
    failure.put("state", "failure");
    failure.put("errorCode", state.error.code);
    return failure;
  }

  Map<String, Object> readFlutterEnvelope() throws RuntimeConfigException {
    TrustProjection trust = loadTrustEnvelope();
    File activeFile = activePackageFile(false);
    if (activeFile == null) {
      throw new RuntimeConfigException(ABSENT_REASON);
    }
    JsonObject packageDocument = decodeDocument(readFile(activeFile), "runtime_config_package_malformed");
    return validatePackage(packageDocument, trust, null).flutterEnvelope();
  }

  String readCurrentActiveDigest() throws RuntimeConfigException {
    return currentActiveDigest(loadTrustEnvelope());
  }

  synchronized ActivationResult activate(
      JsonObject packageDocument,
      String expectedPackageDigest,
      String expectedTrustEnvelopeDigest,
      String expectedActiveDigest)
      throws RuntimeConfigException {
    return activate(
        packageDocument,
        expectedPackageDigest,
        expectedTrustEnvelopeDigest,
        expectedActiveDigest,
        result -> {});
  }

  synchronized ActivationResult activate(
      JsonObject packageDocument,
      String expectedPackageDigest,
      String expectedTrustEnvelopeDigest,
      String expectedActiveDigest,
      ActivationCommitter committer)
      throws RuntimeConfigException {
    if (packageDocument == null) {
      throw new RuntimeConfigException("runtime_config_package_malformed");
    }
    if (!isDigest(expectedPackageDigest)) {
      throw new RuntimeConfigException("runtime_config_package_digest_mismatch");
    }
    if (!isDigest(expectedTrustEnvelopeDigest)) {
      throw new RuntimeConfigException("runtime_config_trust_digest_mismatch");
    }
    if (expectedActiveDigest == null
        || (!expectedActiveDigest.isEmpty() && !isDigest(expectedActiveDigest))) {
      throw new RuntimeConfigException("runtime_config_active_digest_conflict");
    }
    TrustProjection trust = loadTrustEnvelope();
    if (!MessageDigest.isEqual(
        trust.digest.getBytes(StandardCharsets.UTF_8),
        expectedTrustEnvelopeDigest.getBytes(StandardCharsets.UTF_8))) {
      throw new RuntimeConfigException("runtime_config_trust_digest_mismatch");
    }

    String currentDigest = currentActiveDigest(trust);
    if (!MessageDigest.isEqual(
        currentDigest.getBytes(StandardCharsets.UTF_8),
        expectedActiveDigest.getBytes(StandardCharsets.UTF_8))) {
      throw new RuntimeConfigException("runtime_config_active_digest_conflict");
    }

    validatePackage(packageDocument, trust, expectedPackageDigest);
    byte[] canonicalPackage = canonicalJsonBytes(packageDocument);
    WriteResult writeResult = writeActivePackage(canonicalPackage);

    try {
      JsonObject readback =
          decodeDocument(readFile(writeResult.destination), "runtime_config_package_malformed");
      ActiveProjection activated = validatePackage(readback, trust, expectedPackageDigest);
      if (!MessageDigest.isEqual(canonicalPackage, canonicalJsonBytes(readback))) {
        throw new RuntimeConfigException("runtime_config_activation_readback_failed");
      }
      ActivationResult result =
          new ActivationResult(activated.packageDigest, trust.digest, currentDigest);
      committer.commit(result);
      return result;
    } catch (RuntimeConfigException error) {
      restorePreviousActivePackage(writeResult, error);
      throw error;
    } catch (RuntimeException error) {
      RuntimeConfigException typedError =
          new RuntimeConfigException("runtime_config_activation_readback_failed", error);
      restorePreviousActivePackage(writeResult, typedError);
      throw typedError;
    }
  }

  Map<String, String> readRecoveryRuntimeValues() throws RuntimeConfigException {
    Map<String, Object> envelope = readFlutterEnvelope();
    Object rawPackage = envelope.get("package");
    if (!(rawPackage instanceof Map)) {
      throw new RuntimeConfigException("runtime_config_package_malformed");
    }
    Object rawRuntime = ((Map<?, ?>) rawPackage).get("runtime");
    if (!(rawRuntime instanceof Map)) {
      throw new RuntimeConfigException("runtime_config_package_malformed");
    }
    Map<String, String> values = new LinkedHashMap<>();
    for (String key : RECOVERY_RUNTIME_FIELDS) {
      Object rawValue = ((Map<?, ?>) rawRuntime).get(key);
      if (!(rawValue instanceof String) || ((String) rawValue).isEmpty()) {
        throw new RuntimeConfigException("runtime_config_runtime_values_invalid");
      }
      values.put(key, (String) rawValue);
    }
    return Collections.unmodifiableMap(values);
  }

  String currentIdentity() {
    ReadState state = readState();
    if (state.kind == ReadKind.PRESENT) {
      @SuppressWarnings("unchecked")
      Map<String, Object> packageDocument =
          (Map<String, Object>) state.payload.get("package");
      return packageDocument.get("buildProfile")
          + "|"
          + packageDocument.get("environment")
          + "|"
          + packageDocument.get("target")
          + "|"
          + state.payload.get("packageDigest");
    }
    if (state.kind == ReadKind.ABSENT) {
      @SuppressWarnings("unchecked")
      Map<String, Object> trustDocument =
          (Map<String, Object>) state.payload.get("artifactTrustEnvelope");
      return trustDocument.get("buildProfile")
          + "|runtime-config-absent|"
          + state.payload.get("trustEnvelopeDigest");
    }
    return "runtime-config-failure|" + state.error.code;
  }

  private String currentActiveDigest(TrustProjection trust) throws RuntimeConfigException {
    File activeFile = activePackageFile(false);
    if (activeFile == null) {
      return "";
    }
    JsonObject current = decodeDocument(readFile(activeFile), "runtime_config_package_malformed");
    // CAS 前值只需要身份：时间窗过期的旧包必须仍可被替换，不得死锁激活。
    return validatePackage(current, trust, null, true).packageDigest;
  }

  private WriteResult writeActivePackage(byte[] canonicalPackage) throws RuntimeConfigException {
    File previousActiveFile = activePackageFile(false);
    byte[] previousActivePackage =
        previousActiveFile == null ? null : readFile(previousActiveFile);
    File destination = activePackageFile(true);
    try {
      atomicWriter.write(destination, canonicalPackage);
    } catch (IOException error) {
      RuntimeConfigException writeError =
          new RuntimeConfigException("runtime_config_activation_write_failed", error);
      if (!activePackageUnchanged(previousActiveFile, previousActivePackage, destination)) {
        restorePreviousActivePackage(
            new WriteResult(previousActivePackage, destination), writeError);
      }
      throw writeError;
    }
    return new WriteResult(previousActivePackage, destination);
  }

  private boolean activePackageUnchanged(
      File previousActiveFile, byte[] previousActivePackage, File destination) {
    try {
      File activeFile = activePackageFile(false);
      if (previousActiveFile == null) {
        return activeFile == null;
      }
      return activeFile != null
          && activeFile.getCanonicalFile().equals(destination.getCanonicalFile())
          && MessageDigest.isEqual(previousActivePackage, readFile(activeFile));
    } catch (IOException | RuntimeConfigException error) {
      return false;
    }
  }

  private void restorePreviousActivePackage(
      WriteResult writeResult, RuntimeConfigException originalError)
      throws RuntimeConfigException {
    try {
      if (writeResult.previousActivePackage == null) {
        Files.deleteIfExists(writeResult.destination.toPath());
        fsyncDirectory(writeResult.destination.getParentFile());
      } else {
        atomicWriter.write(writeResult.destination, writeResult.previousActivePackage);
      }
    } catch (IOException restoreError) {
      originalError.addSuppressed(restoreError);
      throw new RuntimeConfigException("runtime_config_activation_rollback_failed", originalError);
    }
  }

  private TrustProjection loadTrustEnvelope() throws RuntimeConfigException {
    byte[] bytes;
    try (InputStream stream = trustSource.open()) {
      bytes = readBounded(stream, "runtime_config_trust_empty", "runtime_config_trust_too_large");
    } catch (FileNotFoundException error) {
      throw new RuntimeConfigException("runtime_config_trust_missing", error);
    } catch (IOException error) {
      throw new RuntimeConfigException("runtime_config_trust_read_failed", error);
    }
    JsonObject trust = decodeDocument(bytes, "runtime_config_trust_malformed");
    if (!exactFields(trust, TRUST_FIELDS)
        || !TRUST_SCHEMA.equals(stringValue(trust, "schema"))
        || !SIGNATURE_ALGORITHM.equals(stringValue(trust, "signatureAlgorithm"))) {
      throw new RuntimeConfigException("runtime_config_trust_malformed");
    }
    String trustProfile = requiredString(trust, "buildProfile", "runtime_config_trust_malformed");
    if (!AppLaunchContract.BUILD_PROFILE_ENVIRONMENTS.containsKey(trustProfile)) {
      throw new RuntimeConfigException("runtime_config_trust_malformed");
    }
    Map<String, String> keyring =
        normalizedKeyring(trust.get("trustedPublicKeys"), "runtime_config_trust_keyring_invalid");
    return new TrustProjection(
        trust,
        Collections.unmodifiableMap(keyring),
        sha256Identity(canonicalJsonBytes(trust)));
  }

  private ActiveProjection validatePackage(
      JsonObject packageDocument, TrustProjection trust, String expectedPackageDigest)
      throws RuntimeConfigException {
    return validatePackage(packageDocument, trust, expectedPackageDigest, false);
  }

  // allowStaleIdentity 只供激活流程读取 CAS 前值：豁免 expiresAt 时间窗，
  // trust/签名/结构校验全部保留；消费路径必须走严格重载
  //（environment-topology-and-packaging spec：过期即死锁的实现是违约）。
  private ActiveProjection validatePackage(
      JsonObject packageDocument,
      TrustProjection trust,
      String expectedPackageDigest,
      boolean allowStaleIdentity)
      throws RuntimeConfigException {
    if (!exactFields(packageDocument, PACKAGE_FIELDS)
        || !PACKAGE_SCHEMA.equals(stringValue(packageDocument, "schema"))) {
      throw new RuntimeConfigException("runtime_config_schema_mismatch");
    }
    if (!SIGNATURE_ALGORITHM.equals(stringValue(packageDocument, "signatureAlgorithm"))) {
      throw new RuntimeConfigException("runtime_config_signature_algorithm_mismatch");
    }
    String profile =
        requiredString(packageDocument, "buildProfile", "runtime_config_package_malformed");
    if (!profile.equals(requiredStringUnchecked(trust.document, "buildProfile"))) {
      throw new RuntimeConfigException("runtime_config_profile_mismatch");
    }
    String environment =
        requiredString(packageDocument, "environment", "runtime_config_package_malformed");
    String target =
        requiredString(packageDocument, "target", "runtime_config_package_malformed");
    if (!environment.equals(TARGET_ENVIRONMENTS.get(target))) {
      throw new RuntimeConfigException("runtime_config_target_mismatch");
    }
    List<String> allowedEnvironments =
        AppLaunchContract.BUILD_PROFILE_ENVIRONMENTS.get(profile);
    String expectedPolicy = AppLaunchContract.BUILD_PROFILE_LAUNCH_POLICIES.get(profile);
    if (allowedEnvironments == null
        || expectedPolicy == null
        || !allowedEnvironments.contains(environment)
        || !expectedPolicy.equals(stringValue(packageDocument, "launchPolicy"))) {
      throw new RuntimeConfigException("runtime_config_launch_policy_mismatch");
    }

    JsonElement rawRuntime = packageDocument.get("runtime");
    if (rawRuntime == null || !rawRuntime.isJsonObject()) {
      throw new RuntimeConfigException("runtime_config_runtime_values_invalid");
    }
    JsonObject runtime = rawRuntime.getAsJsonObject();
    if (!exactFields(runtime, RUNTIME_FIELDS)
        || !environment.equals(stringValue(runtime, "appRuntimeEnv"))) {
      throw new RuntimeConfigException("runtime_config_runtime_values_invalid");
    }
    for (String key : RUNTIME_FIELDS) {
      String value = requiredString(runtime, key, "runtime_config_runtime_values_invalid");
      if (SECRET_KEY_PATTERN.matcher(key).find()) {
        throw new RuntimeConfigException("runtime_config_runtime_values_invalid");
      }
      if (!"appRuntimeEnv".equals(key)) {
        validateEndpoint(key, value);
      }
    }

    if (!SOURCE_GIT_SHA_PATTERN
            .matcher(requiredString(packageDocument, "sourceGitSha", "runtime_config_package_malformed"))
            .matches()
        || !SOURCE_TREE_DIGEST_PATTERN
            .matcher(
                requiredString(
                    packageDocument, "sourceTreeDigest", "runtime_config_package_malformed"))
            .matches()) {
      throw new RuntimeConfigException("runtime_config_source_identity_invalid");
    }

    Map<String, String> packageKeyring =
        normalizedKeyring(
            packageDocument.get("trustedPublicKeys"), "runtime_config_keyring_mismatch");
    if (!packageKeyring.equals(trust.trustedPublicKeys)) {
      throw new RuntimeConfigException("runtime_config_keyring_mismatch");
    }
    String signatureKeyId =
        requiredString(packageDocument, "signatureKeyId", "runtime_config_package_malformed");
    String encodedPublicKey = trust.trustedPublicKeys.get(signatureKeyId);
    if (encodedPublicKey == null) {
      throw new RuntimeConfigException("runtime_config_signature_key_untrusted");
    }

    JsonObject digestDocument = packageDocument.deepCopy();
    digestDocument.remove("signature");
    digestDocument.addProperty("payloadDigest", "");
    String calculatedPayloadDigest = sha256Identity(canonicalJsonBytes(digestDocument));
    String declaredPayloadDigest =
        requiredString(packageDocument, "payloadDigest", "runtime_config_package_malformed");
    if (!isDigest(declaredPayloadDigest)
        || !MessageDigest.isEqual(
            calculatedPayloadDigest.getBytes(StandardCharsets.UTF_8),
            declaredPayloadDigest.getBytes(StandardCharsets.UTF_8))) {
      throw new RuntimeConfigException("runtime_config_payload_digest_mismatch");
    }

    verifySignature(packageDocument, encodedPublicKey);
    validateFreshness(packageDocument, allowStaleIdentity);
    String packageDigest = sha256Identity(canonicalJsonBytes(packageDocument));
    if (expectedPackageDigest != null
        && !MessageDigest.isEqual(
            packageDigest.getBytes(StandardCharsets.UTF_8),
            expectedPackageDigest.getBytes(StandardCharsets.UTF_8))) {
      throw new RuntimeConfigException("runtime_config_package_digest_mismatch");
    }
    return new ActiveProjection(packageDocument, trust, packageDigest);
  }

  private void verifySignature(JsonObject packageDocument, String encodedPublicKey)
      throws RuntimeConfigException {
    byte[] publicKey = strictBase64(encodedPublicKey, 32, "runtime_config_trust_keyring_invalid");
    byte[] signature =
        strictBase64(
            requiredString(packageDocument, "signature", "runtime_config_package_malformed"),
            64,
            "runtime_config_signature_invalid");
    JsonObject signedDocument = packageDocument.deepCopy();
    signedDocument.remove("signature");
    try {
      new Ed25519Verify(publicKey).verify(signature, canonicalJsonBytes(signedDocument));
    } catch (GeneralSecurityException error) {
      throw new RuntimeConfigException("runtime_config_signature_invalid", error);
    }
  }

  private void validateFreshness(JsonObject packageDocument, boolean allowStaleIdentity)
      throws RuntimeConfigException {
    Instant issuedAt =
        parseTimestamp(
            requiredString(packageDocument, "issuedAt", "runtime_config_package_malformed"));
    Instant expiresAt =
        parseTimestamp(
            requiredString(packageDocument, "expiresAt", "runtime_config_package_malformed"));
    Instant now = clock.now();
    long lifetime;
    try {
      lifetime = expiresAt.toEpochMilli() - issuedAt.toEpochMilli();
    } catch (ArithmeticException error) {
      throw new RuntimeConfigException("runtime_config_freshness_invalid", error);
    }
    if (lifetime <= 0
        || lifetime > MAXIMUM_LIFETIME_MILLIS
        || issuedAt.isAfter(now.plusMillis(MAXIMUM_FUTURE_SKEW_MILLIS))) {
      throw new RuntimeConfigException("runtime_config_freshness_invalid");
    }
    if (!allowStaleIdentity && !expiresAt.isAfter(now)) {
      throw new RuntimeConfigException("runtime_config_freshness_invalid");
    }
  }

  private File activePackageFile(boolean createRoot) throws RuntimeConfigException {
    try {
      if (createRoot && !noBackupRoot.exists() && !noBackupRoot.mkdirs()) {
        throw new RuntimeConfigException("runtime_config_activation_write_failed");
      }
      File canonicalRoot = noBackupRoot.getCanonicalFile();
      if (!canonicalRoot.isDirectory()) {
        if (!createRoot && !canonicalRoot.exists()) {
          return null;
        }
        throw new RuntimeConfigException("runtime_config_package_path_invalid");
      }
      if (Files.isSymbolicLink(canonicalRoot.toPath())) {
        throw new RuntimeConfigException("runtime_config_package_path_invalid");
      }
      File candidate = new File(canonicalRoot, PACKAGE_FILE_NAME).getCanonicalFile();
      if (!candidate.getPath().startsWith(canonicalRoot.getPath() + File.separator)) {
        throw new RuntimeConfigException("runtime_config_package_path_invalid");
      }
      if (!candidate.exists()) {
        return createRoot ? candidate : null;
      }
      if (!Files.isRegularFile(candidate.toPath(), LinkOption.NOFOLLOW_LINKS)
          || Files.isSymbolicLink(candidate.toPath())) {
        throw new RuntimeConfigException("runtime_config_package_path_invalid");
      }
      return candidate;
    } catch (IOException error) {
      throw new RuntimeConfigException("runtime_config_package_path_invalid", error);
    }
  }

  private static byte[] readFile(File file) throws RuntimeConfigException {
    try (InputStream stream = new FileInputStream(file)) {
      return readBounded(
          stream, "runtime_config_package_empty", "runtime_config_package_too_large");
    } catch (IOException error) {
      throw new RuntimeConfigException("runtime_config_package_read_failed", error);
    }
  }

  private static byte[] readBounded(InputStream stream, String emptyCode, String oversizedCode)
      throws IOException, RuntimeConfigException {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] buffer = new byte[8192];
    int count;
    while ((count = stream.read(buffer)) != -1) {
      if (output.size() + count > MAX_BYTES) {
        throw new RuntimeConfigException(oversizedCode);
      }
      output.write(buffer, 0, count);
    }
    if (output.size() == 0) {
      throw new RuntimeConfigException(emptyCode);
    }
    return output.toByteArray();
  }

  private static JsonObject decodeDocument(byte[] bytes, String malformedCode)
      throws RuntimeConfigException {
    try {
      JsonElement decoded = JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8));
      if (!decoded.isJsonObject() || decoded.getAsJsonObject().size() == 0) {
        throw new RuntimeConfigException(malformedCode);
      }
      rejectUnsupportedJson(decoded, malformedCode);
      return decoded.getAsJsonObject();
    } catch (RuntimeConfigException error) {
      throw error;
    } catch (RuntimeException error) {
      throw new RuntimeConfigException(malformedCode, error);
    }
  }

  private static void rejectUnsupportedJson(JsonElement value, String malformedCode)
      throws RuntimeConfigException {
    if (value == null || value.isJsonNull()) {
      throw new RuntimeConfigException(malformedCode);
    }
    if (value.isJsonObject()) {
      for (Map.Entry<String, JsonElement> entry : value.getAsJsonObject().entrySet()) {
        rejectUnsupportedJson(entry.getValue(), malformedCode);
      }
      return;
    }
    if (value.isJsonArray()) {
      for (JsonElement item : value.getAsJsonArray()) {
        rejectUnsupportedJson(item, malformedCode);
      }
      return;
    }
    JsonPrimitive primitive = value.getAsJsonPrimitive();
    if (!primitive.isString() && !primitive.isBoolean()) {
      throw new RuntimeConfigException(malformedCode);
    }
  }

  static byte[] canonicalJsonBytes(JsonElement value) throws RuntimeConfigException {
    StringBuilder output = new StringBuilder();
    appendCanonicalJson(output, value);
    return output.toString().getBytes(StandardCharsets.UTF_8);
  }

  private static void appendCanonicalJson(StringBuilder output, JsonElement value)
      throws RuntimeConfigException {
    if (value == null || value.isJsonNull()) {
      output.append("null");
      return;
    }
    if (value.isJsonObject()) {
      output.append('{');
      List<String> keys = new ArrayList<>();
      for (Map.Entry<String, JsonElement> entry : value.getAsJsonObject().entrySet()) {
        keys.add(entry.getKey());
      }
      Collections.sort(keys);
      for (int index = 0; index < keys.size(); index += 1) {
        if (index > 0) {
          output.append(',');
        }
        String key = keys.get(index);
        output.append(GSON.toJson(key)).append(':');
        appendCanonicalJson(output, value.getAsJsonObject().get(key));
      }
      output.append('}');
      return;
    }
    if (value.isJsonArray()) {
      output.append('[');
      for (int index = 0; index < value.getAsJsonArray().size(); index += 1) {
        if (index > 0) {
          output.append(',');
        }
        appendCanonicalJson(output, value.getAsJsonArray().get(index));
      }
      output.append(']');
      return;
    }
    JsonPrimitive primitive = value.getAsJsonPrimitive();
    if (primitive.isString()) {
      output.append(GSON.toJson(primitive.getAsString()));
      return;
    }
    if (primitive.isBoolean()) {
      output.append(primitive.getAsBoolean());
      return;
    }
    throw new RuntimeConfigException("runtime_config_package_malformed");
  }

  static String sha256Identity(byte[] payload) throws RuntimeConfigException {
    try {
      byte[] digest = MessageDigest.getInstance("SHA-256").digest(payload);
      char[] alphabet = "0123456789abcdef".toCharArray();
      char[] encoded = new char[digest.length * 2];
      for (int index = 0; index < digest.length; index += 1) {
        int value = digest[index] & 0xff;
        encoded[index * 2] = alphabet[value >>> 4];
        encoded[index * 2 + 1] = alphabet[value & 0x0f];
      }
      return "sha256:" + new String(encoded);
    } catch (GeneralSecurityException error) {
      throw new RuntimeConfigException("runtime_config_digest_unavailable", error);
    }
  }

  private static Map<String, String> normalizedKeyring(JsonElement raw, String errorCode)
      throws RuntimeConfigException {
    if (raw == null || !raw.isJsonObject() || raw.getAsJsonObject().size() == 0) {
      throw new RuntimeConfigException(errorCode);
    }
    Map<String, String> keyring = new LinkedHashMap<>();
    List<String> keyIds = new ArrayList<>();
    for (Map.Entry<String, JsonElement> entry : raw.getAsJsonObject().entrySet()) {
      keyIds.add(entry.getKey());
    }
    Collections.sort(keyIds);
    for (String keyId : keyIds) {
      if (!KEY_ID_PATTERN.matcher(keyId).matches()) {
        throw new RuntimeConfigException(errorCode);
      }
      JsonElement encodedElement = raw.getAsJsonObject().get(keyId);
      if (!encodedElement.isJsonPrimitive() || !encodedElement.getAsJsonPrimitive().isString()) {
        throw new RuntimeConfigException(errorCode);
      }
      String encoded = encodedElement.getAsString();
      strictBase64(encoded, 32, errorCode);
      keyring.put(keyId, encoded);
    }
    return keyring;
  }

  private static byte[] strictBase64(String encoded, int expectedLength, String errorCode)
      throws RuntimeConfigException {
    if (encoded == null || encoded.isEmpty() || !encoded.equals(encoded.trim())) {
      throw new RuntimeConfigException(errorCode);
    }
    try {
      byte[] decoded = Base64.getDecoder().decode(encoded);
      if (decoded.length != expectedLength
          || !MessageDigest.isEqual(
              Base64.getEncoder().encode(decoded), encoded.getBytes(StandardCharsets.US_ASCII))) {
        throw new RuntimeConfigException(errorCode);
      }
      return decoded;
    } catch (IllegalArgumentException error) {
      throw new RuntimeConfigException(errorCode, error);
    }
  }

  private static Instant parseTimestamp(String raw) throws RuntimeConfigException {
    if (!raw.endsWith("Z")) {
      throw new RuntimeConfigException("runtime_config_freshness_invalid");
    }
    try {
      return Instant.parse(raw);
    } catch (DateTimeParseException error) {
      throw new RuntimeConfigException("runtime_config_freshness_invalid", error);
    }
  }

  private static void validateEndpoint(String key, String raw) throws RuntimeConfigException {
    try {
      java.net.URI uri = new java.net.URI(raw);
      String expectedScheme = WEBSOCKET_RUNTIME_FIELDS.contains(key) ? "wss" : "https";
      if (!expectedScheme.equalsIgnoreCase(uri.getScheme())
          || uri.getHost() == null
          || uri.getHost().isEmpty()
          || uri.getUserInfo() != null
          || uri.getQuery() != null
          || uri.getFragment() != null) {
        throw new RuntimeConfigException("runtime_config_endpoint_invalid");
      }
    } catch (java.net.URISyntaxException error) {
      throw new RuntimeConfigException("runtime_config_endpoint_invalid", error);
    }
  }

  private static boolean exactFields(JsonObject object, List<String> expected) {
    return object.keySet().size() == expected.size() && object.keySet().containsAll(expected);
  }

  static String registeredErrorCode(String code) {
    if (!AppLaunchContract.RUNTIME_CONFIG_ERROR_CODES.containsKey(code)) {
      throw new IllegalArgumentException("Unregistered runtime config error code: " + code);
    }
    return code;
  }

  private static String requiredGeneratedSchemaValue(String schemaName) {
    String value = AppLaunchContract.SCHEMA_VALUES.get(schemaName);
    if (value == null || value.isEmpty()) {
      throw new IllegalStateException("Generated App launch schema is missing: " + schemaName);
    }
    return value;
  }

  private static String requiredString(JsonObject object, String key, String errorCode)
      throws RuntimeConfigException {
    String value = stringValue(object, key);
    if (value == null || value.isEmpty() || !value.equals(value.trim())) {
      throw new RuntimeConfigException(errorCode);
    }
    return value;
  }

  private static String requiredStringUnchecked(JsonObject object, String key) {
    return object.get(key).getAsString();
  }

  private static String stringValue(JsonObject object, String key) {
    JsonElement raw = object.get(key);
    return raw != null && raw.isJsonPrimitive() && raw.getAsJsonPrimitive().isString()
        ? raw.getAsString()
        : null;
  }

  private static boolean isDigest(String value) {
    return value != null && DIGEST_PATTERN.matcher(value).matches();
  }

  private static Map<String, Object> objectMap(JsonObject object) {
    @SuppressWarnings("unchecked")
    Map<String, Object> result = GSON.fromJson(object, LinkedHashMap.class);
    return result;
  }

  static void writeDurablyAndReplace(File destination, byte[] payload) throws IOException {
    File directory = destination.getParentFile();
    if (directory == null || (!directory.isDirectory() && !directory.mkdirs())) {
      throw new IOException("runtime config directory unavailable");
    }
    File temporary = File.createTempFile(".runtime-config-package.", ".tmp", directory);
    boolean moved = false;
    try {
      try (FileOutputStream output = new FileOutputStream(temporary, false)) {
        output.write(payload);
        output.flush();
        output.getFD().sync();
      }
      try {
        Files.move(
            temporary.toPath(),
            destination.toPath(),
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
      } catch (AtomicMoveNotSupportedException error) {
        throw new IOException("atomic replacement is unsupported", error);
      }
      moved = true;
      fsyncDirectory(directory);
    } finally {
      if (!moved) {
        Files.deleteIfExists(temporary.toPath());
      }
    }
  }

  private static void fsyncDirectory(File directory) throws IOException {
    try (FileInputStream input = new FileInputStream(directory)) {
      input.getFD().sync();
    } catch (FileNotFoundException error) {
      if (!directory.isDirectory()) {
        throw error;
      }
    }
  }
}
