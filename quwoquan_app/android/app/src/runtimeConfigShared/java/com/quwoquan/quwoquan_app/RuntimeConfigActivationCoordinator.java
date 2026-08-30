package com.quwoquan.quwoquan_app;

import android.content.Intent;
import android.util.Log;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

final class RuntimeConfigActivationCoordinator {
  interface ReceiptWriter {
    void write(File destination, byte[] payload) throws IOException;
  }

  interface RequestCleaner {
    void delete(File requestFile) throws IOException;
  }

  interface RequestDocumentReader {
    JsonObject read(File requestFile, String malformedCode)
        throws IOException, RuntimeConfigPackageStore.RuntimeConfigException;
  }

  interface ErrorLogger {
    void log(String errorCode, Throwable error);
  }

  static final String REQUEST_FILE_NAME = "runtime-config-activation-request.json";
  static final String RECEIPT_FILE_NAME = "runtime-config-activation-receipt.json";
  static final String ACTIVE_RECEIPT_FILE_NAME = "runtime-config-active-receipt.json";
  static final String REQUEST_DIGEST_EXTRA =
      "quwoquan.runtime_config.ACTIVATION_REQUEST_DIGEST";

  private static final String REQUEST_SCHEMA =
      requiredGeneratedSchemaValue("runtime_config_activation_request");
  private static final String RECEIPT_SCHEMA =
      requiredGeneratedSchemaValue("runtime_config_activation_receipt");
  private static final String ACTIVATED_STATUS = requiredGeneratedActivationStatus("activated");
  private static final String FAILED_STATUS = requiredGeneratedActivationStatus("failed");
  private static final Pattern DIGEST_PATTERN = Pattern.compile("^sha256:[0-9a-f]{64}$");
  private static final List<String> REQUEST_FIELDS =
      AppLaunchContract.RUNTIME_CONFIG_ACTIVATION_REQUEST_REQUIRED_FIELDS;
  private static final List<String> RECEIPT_FIELDS =
      AppLaunchContract.RUNTIME_CONFIG_ACTIVATION_RECEIPT_REQUIRED_FIELDS;
  private static final Gson GSON = new Gson();

  enum ConsumeKind {
    NOT_REQUESTED,
    ACTIVATED,
    FAILED
  }

  static final class ConsumeResult {
    final ConsumeKind kind;
    final String errorCode;
    final List<String> validationIssues;

    private ConsumeResult(
        ConsumeKind kind, String errorCode, List<String> validationIssues) {
      this.kind = kind;
      this.errorCode = errorCode;
      this.validationIssues = validationIssues;
    }

    static ConsumeResult notRequested() {
      return new ConsumeResult(ConsumeKind.NOT_REQUESTED, "", Collections.emptyList());
    }

    static ConsumeResult activated() {
      return new ConsumeResult(ConsumeKind.ACTIVATED, "", Collections.emptyList());
    }

    static ConsumeResult failed(String errorCode, List<String> validationIssues) {
      String registeredErrorCode = RuntimeConfigPackageStore.registeredErrorCode(errorCode);
      List<String> registeredIssues = new ArrayList<>();
      for (String issue : validationIssues) {
        registeredIssues.add(RuntimeConfigPackageStore.registeredErrorCode(issue));
      }
      return new ConsumeResult(
          ConsumeKind.FAILED,
          registeredErrorCode,
          Collections.unmodifiableList(new ArrayList<>(registeredIssues)));
    }
  }

  private static final class ActivationFailure extends Exception {
    final String code;
    final List<String> issues;

    ActivationFailure(String code) {
      this(code, List.of(code));
    }

    ActivationFailure(String code, List<String> issues) {
      super(code);
      this.code = RuntimeConfigPackageStore.registeredErrorCode(code);
      List<String> registeredIssues = new ArrayList<>();
      for (String issue : issues) {
        registeredIssues.add(RuntimeConfigPackageStore.registeredErrorCode(issue));
      }
      this.issues = Collections.unmodifiableList(registeredIssues);
    }
  }

  private final File stateRoot;
  private final RuntimeConfigPackageStore store;
  private final ReceiptWriter receiptWriter;
  private final RequestCleaner requestCleaner;
  private final RequestDocumentReader requestDocumentReader;
  private final ErrorLogger errorLogger;

  RuntimeConfigActivationCoordinator(File stateRoot, RuntimeConfigPackageStore store) {
    this(
        stateRoot,
        store,
        RuntimeConfigPackageStore::writeDurablyAndReplace,
        requestFile -> Files.deleteIfExists(requestFile.toPath()),
        RuntimeConfigActivationCoordinator::readDocument,
        RuntimeConfigActivationCoordinator::logNativeError);
  }

  RuntimeConfigActivationCoordinator(
      File stateRoot,
      RuntimeConfigPackageStore store,
      ReceiptWriter receiptWriter,
      RequestCleaner requestCleaner) {
    this(
        stateRoot,
        store,
        receiptWriter,
        requestCleaner,
        RuntimeConfigActivationCoordinator::readDocument,
        RuntimeConfigActivationCoordinator::logNativeError);
  }

  RuntimeConfigActivationCoordinator(
      File stateRoot,
      RuntimeConfigPackageStore store,
      ReceiptWriter receiptWriter,
      RequestCleaner requestCleaner,
      RequestDocumentReader requestDocumentReader,
      ErrorLogger errorLogger) {
    this.stateRoot = stateRoot;
    this.store = store;
    this.receiptWriter = receiptWriter;
    this.requestCleaner = requestCleaner;
    this.requestDocumentReader = requestDocumentReader;
    this.errorLogger = errorLogger;
  }

  ConsumeResult consumePendingRequest(Intent intent, boolean coldStartAllowed) {
    String expectedRequestDigest = intent.getStringExtra(REQUEST_DIGEST_EXTRA);
    if (expectedRequestDigest == null || expectedRequestDigest.isEmpty()) {
      return ConsumeResult.notRequested();
    }
    return consumePendingRequest(expectedRequestDigest, coldStartAllowed);
  }

  ConsumeResult consumePendingRequest(String expectedRequestDigest) {
    return consumePendingRequest(expectedRequestDigest, true);
  }

  private synchronized ConsumeResult consumePendingRequest(
      String expectedRequestDigest, boolean coldStartAllowed) {
    Map<String, Object> request = null;
    String requestDigest = isDigest(expectedRequestDigest) ? expectedRequestDigest : zeroDigest();
    String previousActiveDigest = "";
    boolean previousActiveDigestKnown = false;
    try {
      if (!coldStartAllowed) {
        throw new ActivationFailure("runtime_config_activation_requires_cold_start");
      }
      if (!isDigest(expectedRequestDigest)) {
        throw new ActivationFailure("runtime_config_activation_request_digest_invalid");
      }
      previousActiveDigest = store.readCurrentActiveDigest();
      previousActiveDigestKnown = true;
      JsonObject requestDocument =
          requestDocumentReader.read(
              stateFile(REQUEST_FILE_NAME, false),
              "runtime_config_activation_request_malformed");
      requestDigest =
          RuntimeConfigPackageStore.sha256Identity(
              RuntimeConfigPackageStore.canonicalJsonBytes(requestDocument));
      request = objectMap(requestDocument);
      if (!constantTimeEquals(requestDigest, expectedRequestDigest)) {
        throw new ActivationFailure("runtime_config_activation_request_digest_mismatch");
      }
      List<String> requestIssues = validateRequest(requestDocument);
      if (!requestIssues.isEmpty()) {
        throw new ActivationFailure(requestIssues.get(0), requestIssues);
      }
      if (isAlreadyActivated(request, requestDigest)) {
        deletePendingRequestBestEffort();
        return ConsumeResult.activated();
      }

      JsonObject packageDocument = requestDocument.getAsJsonObject("package");
      Map<String, Object> finalRequest = request;
      String finalRequestDigest = requestDigest;
      store.activate(
              packageDocument,
              (String) request.get("packageDigest"),
              (String) request.get("trustEnvelopeDigest"),
              (String) request.get("expectedActiveDigest"),
              result ->
                  commitActivationReceipts(
                      buildReceipt(
                          finalRequest,
                          finalRequestDigest,
                          ACTIVATED_STATUS,
                          result.previousActiveDigest,
                          result.packageDigest,
                          "",
                          Collections.emptyList())));
      deletePendingRequestBestEffort();
      return ConsumeResult.activated();
    } catch (ActivationFailure error) {
      logFailure(error.code, error);
      return recordFailure(
          request,
          requestDigest,
          previousActiveDigest,
          previousActiveDigestKnown,
          error.code,
          error.issues);
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      logFailure(error.code, error);
      return recordFailure(
          request,
          requestDigest,
          previousActiveDigest,
          previousActiveDigestKnown,
          error.code,
          List.of(error.code));
    } catch (FileNotFoundException error) {
      String code = "runtime_config_activation_request_missing";
      logFailure(code, error);
      return recordFailure(
          request,
          requestDigest,
          previousActiveDigest,
          previousActiveDigestKnown,
          code,
          List.of(code));
    } catch (IOException error) {
      String code = "runtime_config_activation_request_read_failed";
      logFailure(code, error);
      return recordFailure(
          request,
          requestDigest,
          previousActiveDigest,
          previousActiveDigestKnown,
          code,
          List.of(code));
    } catch (RuntimeException error) {
      String code = "runtime_config_internal_failure";
      logFailure(code, error);
      return recordFailure(
          request,
          requestDigest,
          previousActiveDigest,
          previousActiveDigestKnown,
          code,
          List.of(code));
    }
  }

  Map<String, Object> readVerifiedFlutterEnvelope()
      throws RuntimeConfigPackageStore.RuntimeConfigException {
    Map<String, Object> state = store.readStateEnvelope();
    if (!"present".equals(state.get("state"))) {
      Object errorCode = state.get("errorCode");
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          errorCode instanceof String
              ? (String) errorCode
              : RuntimeConfigPackageStore.ABSENT_REASON);
    }
    Map<String, Object> receipt = readActiveReceipt();
    if (!receiptMatchesActiveState(receipt, state)) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_mismatch");
    }
    Map<String, Object> envelope = new LinkedHashMap<>(store.readFlutterEnvelope());
    envelope.put("runtimeConfigPackageDigest", state.get("packageDigest"));
    envelope.put("runtimeConfigTrustEnvelopeDigest", state.get("trustEnvelopeDigest"));
    envelope.put(
        "effectiveLaunchManifestDigest", receipt.get("effectiveLaunchManifestDigest"));
    envelope.put("launchProvenance", receipt.get("launchProvenance"));
    envelope.put("runtimeConfigSupplyMode", receipt.get("runtimeConfigSupplyMode"));
    return envelope;
  }

  String readEffectiveLaunchManifestDigest()
      throws RuntimeConfigPackageStore.RuntimeConfigException {
    Object value = readVerifiedFlutterEnvelope().get("effectiveLaunchManifestDigest");
    if (!(value instanceof String) || !isDigest((String) value)) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_mismatch");
    }
    return (String) value;
  }

  private ConsumeResult recordFailure(
      Map<String, Object> request,
      String requestDigest,
      String previousActiveDigest,
      boolean previousActiveDigestKnown,
      String errorCode,
      List<String> validationIssues) {
    List<String> issues = new ArrayList<>(validationIssues);
    if (issues.isEmpty() || !issues.contains(errorCode)) {
      issues.add(0, errorCode);
    }
    // 读取失败时状态未知：保持最后已知 CAS 值并追加 rollback_failed，不得宣称空 active，
    // 也不得覆盖原始失败码；只有确认读取成功且与 CAS 前不一致才升级为 rollback_failed。
    String activePackageDigest;
    boolean activeDigestUnknown = false;
    try {
      activePackageDigest = store.readCurrentActiveDigest();
      if (!previousActiveDigestKnown) {
        previousActiveDigest = activePackageDigest;
        previousActiveDigestKnown = true;
      }
    } catch (RuntimeConfigPackageStore.RuntimeConfigException readError) {
      activePackageDigest = previousActiveDigest;
      activeDigestUnknown = true;
      logFailure(readError.code, readError);
    }
    if (activeDigestUnknown) {
      if (!issues.contains("runtime_config_activation_rollback_failed")) {
        issues.add("runtime_config_activation_rollback_failed");
      }
    } else if (!activePackageDigest.equals(previousActiveDigest)) {
      errorCode = "runtime_config_activation_rollback_failed";
      if (!issues.contains(errorCode)) {
        issues.add(0, errorCode);
      }
    }
    try {
      writeReceipt(
          RECEIPT_FILE_NAME,
          buildReceipt(
              request == null ? Collections.emptyMap() : request,
              requestDigest,
              FAILED_STATUS,
              previousActiveDigest,
              activePackageDigest,
              errorCode,
              issues));
      deletePendingRequestBestEffort();
    } catch (RuntimeConfigPackageStore.RuntimeConfigException receiptError) {
      logFailure(receiptError.code, receiptError);
      if (!issues.contains("runtime_config_activation_receipt_write_failed")) {
        issues.add("runtime_config_activation_receipt_write_failed");
      }
    }
    return ConsumeResult.failed(errorCode, issues);
  }

  private List<String> validateRequest(JsonObject request) {
    List<String> issues = new ArrayList<>();
    if (!exactFields(request, REQUEST_FIELDS)
        || !REQUEST_SCHEMA.equals(stringValue(request, "schema"))) {
      issues.add("runtime_config_activation_request_malformed");
      return issues;
    }
    String environment = stringValue(request, "environment");
    String buildProfile = stringValue(request, "buildProfile");
    String target = stringValue(request, "target");
    String packageDigest = stringValue(request, "packageDigest");
    String trustDigest = stringValue(request, "trustEnvelopeDigest");
    String manifestDigest = stringValue(request, "effectiveLaunchManifestDigest");
    String expectedActiveDigest = stringValue(request, "expectedActiveDigest");
    if (environment == null
        || buildProfile == null
        || target == null
        || !AppLaunchContract.ENVIRONMENTS.contains(environment)
        || !AppLaunchContract.BUILD_PROFILE_ENVIRONMENTS.containsKey(buildProfile)
        || !environment.equals(AppLaunchContract.TARGET_ENVIRONMENT.get(target))
        || !AppLaunchContract.BUILD_PROFILE_ENVIRONMENTS.get(buildProfile).contains(environment)
        || !isDigest(packageDigest)
        || !isDigest(trustDigest)
        || !isDigest(manifestDigest)
        || expectedActiveDigest == null
        || (!expectedActiveDigest.isEmpty() && !isDigest(expectedActiveDigest))) {
      issues.add("runtime_config_activation_request_malformed");
      return issues;
    }
    JsonElement rawPackage = request.get("package");
    JsonElement rawManifest = request.get("effectiveLaunchManifest");
    if (rawPackage == null
        || !rawPackage.isJsonObject()
        || rawManifest == null
        || !rawManifest.isJsonObject()) {
      issues.add("runtime_config_activation_request_malformed");
      return issues;
    }
    JsonObject manifest = rawManifest.getAsJsonObject();
    if (!RuntimeConfigEffectiveManifestValidator.isValid(manifest)) {
      issues.add("runtime_config_effective_manifest_malformed");
      return issues;
    }
    try {
      String calculatedManifestDigest =
          RuntimeConfigPackageStore.sha256Identity(
              RuntimeConfigPackageStore.canonicalJsonBytes(manifest));
      if (!constantTimeEquals(calculatedManifestDigest, manifestDigest)) {
        issues.add("runtime_config_effective_manifest_digest_mismatch");
      }
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      issues.add(error.code);
    }
    JsonObject packageDocument = rawPackage.getAsJsonObject();
    String packageLaunchPolicy = stringValue(packageDocument, "launchPolicy");
    if (packageLaunchPolicy == null) {
      issues.add("runtime_config_activation_request_malformed");
      return issues;
    }
    for (String field : List.of("environment", "buildProfile", "target")) {
      String requestValue = stringValue(request, field);
      String packageValue = stringValue(packageDocument, field);
      if (packageValue == null
          || !requestValue.equals(packageValue)
          || !requestValue.equals(stringValue(manifest, field))) {
        issues.add("runtime_config_activation_identity_mismatch");
        break;
      }
    }
    if (!packageDigest.equals(stringValue(manifest, "runtimeConfigPackageDigest"))
        || !trustDigest.equals(stringValue(manifest, "runtimeConfigTrustEnvelopeDigest"))
        || !packageLaunchPolicy.equals(stringValue(manifest, "launchPolicy"))) {
      issues.add("runtime_config_activation_identity_mismatch");
    }
    return new ArrayList<>(new java.util.LinkedHashSet<>(issues));
  }

  private Map<String, Object> buildReceipt(
      Map<String, Object> request,
      String requestDigest,
      String status,
      String previousActiveDigest,
      String activePackageDigest,
      String errorCode,
      List<String> validationIssues) {
    Map<String, Object> receipt = new LinkedHashMap<>();
    receipt.put("schema", RECEIPT_SCHEMA);
    receipt.put("status", status);
    receipt.put("requestDigest", requestDigest);
    receipt.put("environment", safeEnvironment(request));
    receipt.put("buildProfile", safeBuildProfile(request));
    receipt.put("target", safeTarget(request));
    receipt.put(
        "launchProvenance",
        safeEffectiveManifestValue(
            request, "launchProvenance", AppLaunchContract.LAUNCH_PROVENANCES));
    receipt.put(
        "runtimeConfigSupplyMode",
        safeEffectiveManifestValue(
            request,
            "runtimeConfigSupplyMode",
            AppLaunchContract.RUNTIME_CONFIG_SUPPLY_MODES));
    receipt.put("packageDigest", safeDigestMapValue(request, "packageDigest"));
    receipt.put("trustEnvelopeDigest", safeDigestMapValue(request, "trustEnvelopeDigest"));
    receipt.put(
        "effectiveLaunchManifestDigest",
        safeDigestMapValue(request, "effectiveLaunchManifestDigest"));
    receipt.put("previousActiveDigest", previousActiveDigest);
    receipt.put("activePackageDigest", activePackageDigest);
    receipt.put("errorCode", errorCode);
    receipt.put("validationIssues", new ArrayList<>(validationIssues));
    return receipt;
  }

  private boolean isAlreadyActivated(Map<String, Object> request, String requestDigest) {
    try {
      Map<String, Object> receipt = readActiveReceipt();
      Map<String, Object> state = store.readStateEnvelope();
      return "present".equals(state.get("state"))
          && receiptMatchesActiveState(receipt, state)
          && requestDigest.equals(receipt.get("requestDigest"))
          && stringMapValue(request, "packageDigest").equals(receipt.get("packageDigest"))
          && stringMapValue(request, "trustEnvelopeDigest")
              .equals(receipt.get("trustEnvelopeDigest"))
          && stringMapValue(request, "effectiveLaunchManifestDigest")
              .equals(receipt.get("effectiveLaunchManifestDigest"))
          && effectiveManifestStringMapValue(request, "launchProvenance")
              .equals(receipt.get("launchProvenance"))
          && effectiveManifestStringMapValue(request, "runtimeConfigSupplyMode")
              .equals(receipt.get("runtimeConfigSupplyMode"));
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      return false;
    }
  }

  private Map<String, Object> readActiveReceipt()
      throws RuntimeConfigPackageStore.RuntimeConfigException {
    try {
      JsonObject receipt =
          readDocument(
              stateFile(ACTIVE_RECEIPT_FILE_NAME, false),
              "runtime_config_activation_receipt_malformed");
      if (!exactFields(receipt, RECEIPT_FIELDS)
          || !RECEIPT_SCHEMA.equals(stringValue(receipt, "schema"))
          || !ACTIVATED_STATUS.equals(stringValue(receipt, "status"))
          || !"".equals(stringValue(receipt, "errorCode"))
          || !AppLaunchContract.LAUNCH_PROVENANCES.contains(
              stringValue(receipt, "launchProvenance"))
          || !AppLaunchContract.RUNTIME_CONFIG_SUPPLY_MODES.contains(
              stringValue(receipt, "runtimeConfigSupplyMode"))) {
        throw new RuntimeConfigPackageStore.RuntimeConfigException(
            "runtime_config_activation_receipt_mismatch");
      }
      JsonElement rawIssues = receipt.get("validationIssues");
      if (rawIssues == null || !rawIssues.isJsonArray() || rawIssues.getAsJsonArray().size() != 0) {
        throw new RuntimeConfigPackageStore.RuntimeConfigException(
            "runtime_config_activation_receipt_mismatch");
      }
      return objectMap(receipt);
    } catch (FileNotFoundException error) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_missing", error);
    } catch (IOException error) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_read_failed", error);
    } catch (RuntimeException error) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_malformed", error);
    }
  }

  private boolean receiptMatchesActiveState(
      Map<String, Object> receipt, Map<String, Object> state) {
    if (!receipt.get("packageDigest").equals(state.get("packageDigest"))
        || !receipt.get("activePackageDigest").equals(state.get("packageDigest"))
        || !receipt.get("trustEnvelopeDigest").equals(state.get("trustEnvelopeDigest"))
        || !isDigest(stringMapValue(receipt, "requestDigest"))
        || !isDigest(stringMapValue(receipt, "effectiveLaunchManifestDigest"))
        || !AppLaunchContract.LAUNCH_PROVENANCES.contains(
            stringMapValue(receipt, "launchProvenance"))
        || !AppLaunchContract.RUNTIME_CONFIG_SUPPLY_MODES.contains(
            stringMapValue(receipt, "runtimeConfigSupplyMode"))) {
      return false;
    }
    Object rawPackage = state.get("package");
    if (!(rawPackage instanceof Map)) {
      return false;
    }
    Map<?, ?> packageDocument = (Map<?, ?>) rawPackage;
    return receipt.get("environment").equals(packageDocument.get("environment"))
        && receipt.get("buildProfile").equals(packageDocument.get("buildProfile"))
        && receipt.get("target").equals(packageDocument.get("target"));
  }

  private void commitActivationReceipts(Map<String, Object> receipt)
      throws RuntimeConfigPackageStore.RuntimeConfigException {
    byte[] previousActiveReceipt = readExistingFile(ACTIVE_RECEIPT_FILE_NAME);
    byte[] previousLaunchReceipt = readExistingFile(RECEIPT_FILE_NAME);
    try {
      writeReceipt(ACTIVE_RECEIPT_FILE_NAME, receipt);
      writeReceipt(RECEIPT_FILE_NAME, receipt);
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      List<Exception> rollbackErrors = new ArrayList<>();
      try {
        restoreExistingFile(ACTIVE_RECEIPT_FILE_NAME, previousActiveReceipt);
      } catch (IOException | RuntimeConfigPackageStore.RuntimeConfigException rollbackError) {
        rollbackErrors.add(rollbackError);
      }
      try {
        restoreExistingFile(RECEIPT_FILE_NAME, previousLaunchReceipt);
      } catch (IOException | RuntimeConfigPackageStore.RuntimeConfigException rollbackError) {
        rollbackErrors.add(rollbackError);
      }
      if (!rollbackErrors.isEmpty()) {
        RuntimeConfigPackageStore.RuntimeConfigException rollbackFailure =
            new RuntimeConfigPackageStore.RuntimeConfigException(
                "runtime_config_activation_rollback_failed", error);
        for (Exception rollbackError : rollbackErrors) {
          rollbackFailure.addSuppressed(rollbackError);
        }
        throw rollbackFailure;
      }
      throw error;
    }
  }

  private byte[] readExistingFile(String fileName)
      throws RuntimeConfigPackageStore.RuntimeConfigException {
    try {
      File file = stateFile(fileName, true);
      return file.isFile() ? Files.readAllBytes(file.toPath()) : null;
    } catch (IOException error) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_write_failed", error);
    }
  }

  private void restoreExistingFile(String fileName, byte[] previousContent)
      throws IOException, RuntimeConfigPackageStore.RuntimeConfigException {
    File file = stateFile(fileName, true);
    if (previousContent == null) {
      Files.deleteIfExists(file.toPath());
    } else {
      receiptWriter.write(file, previousContent);
    }
  }

  private void writeReceipt(String fileName, Map<String, Object> receipt)
      throws RuntimeConfigPackageStore.RuntimeConfigException {
    JsonElement document = GSON.toJsonTree(receipt);
    try {
      receiptWriter.write(
          stateFile(fileName, true), RuntimeConfigPackageStore.canonicalJsonBytes(document));
    } catch (IOException error) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_receipt_write_failed", error);
    }
  }

  private static JsonObject readDocument(File file, String malformedCode)
      throws IOException, RuntimeConfigPackageStore.RuntimeConfigException {
    byte[] payload;
    try (InputStream input = new FileInputStream(file)) {
      payload = input.readNBytes(RuntimeConfigPackageStore.MAX_BYTES + 1);
    }
    if (payload.length == 0 || payload.length > RuntimeConfigPackageStore.MAX_BYTES) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(malformedCode);
    }
    try {
      JsonElement decoded = JsonParser.parseString(new String(payload, StandardCharsets.UTF_8));
      if (!decoded.isJsonObject()) {
        throw new RuntimeConfigPackageStore.RuntimeConfigException(malformedCode);
      }
      RuntimeConfigPackageStore.canonicalJsonBytes(decoded);
      return decoded.getAsJsonObject();
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      throw error;
    } catch (RuntimeException error) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(malformedCode, error);
    }
  }

  private File stateFile(String fileName, boolean createRoot)
      throws IOException, RuntimeConfigPackageStore.RuntimeConfigException {
    if (createRoot && !stateRoot.exists() && !stateRoot.mkdirs()) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_activation_write_failed");
    }
    File root = stateRoot.getCanonicalFile();
    if (!root.isDirectory() || Files.isSymbolicLink(root.toPath())) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_package_path_invalid");
    }
    File candidate = new File(root, fileName).getCanonicalFile();
    if (!candidate.getPath().startsWith(root.getPath() + File.separator)) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_package_path_invalid");
    }
    if (candidate.exists()
        && (!Files.isRegularFile(candidate.toPath(), LinkOption.NOFOLLOW_LINKS)
            || Files.isSymbolicLink(candidate.toPath()))) {
      throw new RuntimeConfigPackageStore.RuntimeConfigException(
          "runtime_config_package_path_invalid");
    }
    if (!createRoot && !candidate.isFile()) {
      throw new FileNotFoundException(fileName);
    }
    return candidate;
  }

  private void deletePendingRequestBestEffort() {
    try {
      requestCleaner.delete(new File(stateRoot, REQUEST_FILE_NAME));
    } catch (IOException ignored) {
      // 激活和回执已经提交；残留请求由相同 request digest 的下一次冷启动幂等处理。
    }
  }

  private static boolean constantTimeEquals(String left, String right) {
    return MessageDigest.isEqual(
        left.getBytes(StandardCharsets.UTF_8), right.getBytes(StandardCharsets.UTF_8));
  }

  private static boolean isDigest(String value) {
    return value != null && DIGEST_PATTERN.matcher(value).matches();
  }

  private static boolean exactFields(JsonObject object, List<String> expected) {
    return object.keySet().size() == expected.size() && object.keySet().containsAll(expected);
  }

  private static String requiredGeneratedSchemaValue(String schemaName) {
    String value = AppLaunchContract.SCHEMA_VALUES.get(schemaName);
    if (value == null || value.isEmpty()) {
      throw new IllegalStateException("Generated App launch schema is missing: " + schemaName);
    }
    return value;
  }

  private static String requiredGeneratedActivationStatus(String status) {
    if (!AppLaunchContract.RUNTIME_CONFIG_ACTIVATION_RECEIPT_STATUSES.contains(status)) {
      throw new IllegalStateException(
          "Generated runtime config activation status is missing: " + status);
    }
    return status;
  }

  private static String zeroDigest() {
    return "sha256:" + "0".repeat(64);
  }

  private static String stringValue(JsonObject object, String key) {
    JsonElement raw = object.get(key);
    return raw != null && raw.isJsonPrimitive() && raw.getAsJsonPrimitive().isString()
        ? raw.getAsString()
        : null;
  }

  private static String stringMapValue(Map<String, Object> object, String key) {
    Object raw = object.get(key);
    return raw instanceof String ? (String) raw : "";
  }

  private static String safeEnvironment(Map<String, Object> request) {
    String value = stringMapValue(request, "environment");
    return AppLaunchContract.ENVIRONMENTS.contains(value) ? value : "";
  }

  private static String safeBuildProfile(Map<String, Object> request) {
    String value = stringMapValue(request, "buildProfile");
    return AppLaunchContract.BUILD_PROFILE_ENVIRONMENTS.containsKey(value) ? value : "";
  }

  private static String safeTarget(Map<String, Object> request) {
    String value = stringMapValue(request, "target");
    return AppLaunchContract.TARGET_ENVIRONMENT.containsKey(value) ? value : "";
  }

  private static String safeDigestMapValue(Map<String, Object> request, String key) {
    String value = stringMapValue(request, key);
    return isDigest(value) ? value : "";
  }

  private static String safeEffectiveManifestValue(
      Map<String, Object> request, String key, List<String> allowedValues) {
    String value = effectiveManifestStringMapValue(request, key);
    return allowedValues.contains(value) ? value : "";
  }

  private static String effectiveManifestStringMapValue(
      Map<String, Object> request, String key) {
    Object rawManifest = request.get("effectiveLaunchManifest");
    if (!(rawManifest instanceof Map)) {
      return "";
    }
    Object rawValue = ((Map<?, ?>) rawManifest).get(key);
    return rawValue instanceof String ? (String) rawValue : "";
  }

  private static Map<String, Object> objectMap(JsonObject object) {
    @SuppressWarnings("unchecked")
    Map<String, Object> result = GSON.fromJson(object, LinkedHashMap.class);
    return result;
  }

  private void logFailure(String errorCode, Throwable error) {
    try {
      errorLogger.log(RuntimeConfigPackageStore.registeredErrorCode(errorCode), error);
    } catch (RuntimeException ignored) {
      // Diagnostics must never mask the typed fail-closed result.
    }
  }

  private static void logNativeError(String errorCode, Throwable error) {
    try {
      Log.e("QWQRuntimeConfig", "Native runtime config gate failed: " + errorCode, error);
    } catch (RuntimeException ignored) {
      // android.jar stubs throw in host-side JVM tests; device builds emit the native log.
    }
  }
}
