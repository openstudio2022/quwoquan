// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
package com.quwoquan.quwoquan_app;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import com.google.crypto.tink.subtle.Ed25519Sign;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public final class RuntimeConfigPackageStoreTest {
  private static final Instant NOW = Instant.parse("2026-08-23T00:00:00Z");
  private static final Gson GSON = new Gson();

  @Rule public final TemporaryFolder temporaryFolder = new TemporaryFolder();

  @Test
  public void firstReadIsTypedAbsentAndIncludesArtifactTrust() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store = createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());

    RuntimeConfigPackageStore.ReadState state = store.readState();

    assertEquals(RuntimeConfigPackageStore.ReadKind.ABSENT, state.kind);
    assertEquals(RuntimeConfigPackageStore.ABSENT_REASON, state.payload.get("reason"));
    assertEquals("absent", state.payload.get("state"));
    assertTrue(state.payload.containsKey("artifactTrustEnvelope"));
    assertDigest(state.payload.get("trustEnvelopeDigest"));
  }

  @Test
  public void missingRequiredFieldFailsBeforeWrite() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.remove("runtime");

    assertInstallFails(material, "runtime_config_schema_mismatch");
    assertFalse(activeFile().exists());
  }

  @Test
  public void packageProfileMustMatchArtifactTrustProfile() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.addProperty("buildProfile", "prod");
    material.resign();

    assertInstallFails(material, "runtime_config_profile_mismatch");
  }

  @Test
  public void packageKeyringMustEqualArtifactTrustKeyring() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument
        .getAsJsonObject("trustedPublicKeys")
        .addProperty("other", material.encodedPublicKey);
    material.resign();

    assertInstallFails(material, "runtime_config_keyring_mismatch");
  }

  @Test
  public void signatureKeyIdMustBeTrustedByArtifact() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.addProperty("signatureKeyId", "other");
    material.resign();

    assertInstallFails(material, "runtime_config_signature_key_untrusted");
  }

  @Test
  public void activationRejectsNestedNonStringRuntimeValues() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    JsonObject packageDocument = material.packageDocument.deepCopy();
    packageDocument.getAsJsonObject("runtime").addProperty("gatewayBaseUrl", 7);
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(
            () ->
                store.activate(
                    packageDocument, material.packageDigest(), material.trustDigest(), ""));

    assertEquals("runtime_config_runtime_values_invalid", error.code);
    assertFalse(activeFile().exists());
  }

  @Test
  public void packageDigestMismatchFailsBeforeActivation() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store = createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(
            () ->
                store.activate(
                    material.packageDocument,
                    differentDigest(),
                    material.trustDigest(),
                    ""));

    assertEquals("runtime_config_package_digest_mismatch", error.code);
    assertFalse(activeFile().exists());
  }

  @Test
  public void payloadDigestMismatchFailsBeforeSignatureVerification() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.addProperty("payloadDigest", differentDigest());

    assertInstallFails(material, "runtime_config_payload_digest_mismatch");
  }

  @Test
  public void invalidSignatureFailsBeforeActivation() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    byte[] invalid = Base64.getDecoder().decode(material.packageDocument.get("signature").getAsString());
    invalid[0] ^= 1;
    material.packageDocument.addProperty("signature", Base64.getEncoder().encodeToString(invalid));

    assertInstallFails(material, "runtime_config_signature_invalid");
  }

  @Test
  public void expiredPackageFailsBeforeActivation() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.addProperty("issuedAt", "2026-08-21T22:00:00Z");
    material.packageDocument.addProperty("expiresAt", "2026-08-22T22:00:00Z");
    material.resign();

    assertInstallFails(material, "runtime_config_freshness_invalid");
  }

  @Test
  public void canonicalRfc3339FractionalUtcTimestampsAreAccepted() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.addProperty("issuedAt", "2026-08-22T23:55:00.125Z");
    material.packageDocument.addProperty("expiresAt", "2026-08-23T23:55:00.125Z");
    material.resign();
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());

    RuntimeConfigPackageStore.ActivationResult result = installFirst(store, material);

    assertEquals(material.packageDigest(), result.packageDigest);
  }

  @Test
  public void casConflictPreservesCurrentActivePackage() throws Exception {
    TestMaterial current = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store = createStore(current, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigPackageStore.ActivationResult activated = installFirst(store, current);
    byte[] before = Files.readAllBytes(activeFile().toPath());
    TestMaterial next = current.nextPackage("beta", "beta-local");

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(
            () ->
                store.activate(
                    next.packageDocument,
                    next.packageDigest(),
                    next.trustDigest(),
                    differentDigest()));

    assertEquals("runtime_config_active_digest_conflict", error.code);
    assertEquals(current.packageDigest(), activated.packageDigest);
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
  }

  @Test
  public void atomicWriteFailureRetainsPreviousActivePackage() throws Exception {
    TestMaterial current = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore initialStore =
        createStore(current, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigPackageStore.ActivationResult activated = installFirst(initialStore, current);
    byte[] previous = Files.readAllBytes(activeFile().toPath());
    TestMaterial next = current.nextPackage("beta", "beta-local");
    RuntimeConfigPackageStore.AtomicWriter corruptingWriter =
        (destination, payload) -> {
          throw new IOException("injected pre-replacement activation failure");
        };
    RuntimeConfigPackageStore failingStore = createStore(current, corruptingWriter);

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(
            () ->
                failingStore.activate(
                    next.packageDocument,
                    next.packageDigest(),
                    next.trustDigest(),
                    activated.packageDigest));

    assertEquals("runtime_config_activation_write_failed", error.code);
    assertArrayEquals(previous, Files.readAllBytes(activeFile().toPath()));
    assertEquals(RuntimeConfigPackageStore.ReadKind.PRESENT, failingStore.readState().kind);
  }

  @Test
  public void postReplacementWriteFailureRestoresPreviousActivePackage() throws Exception {
    TestMaterial current = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore initialStore =
        createStore(current, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigPackageStore.ActivationResult activated = installFirst(initialStore, current);
    byte[] previous = Files.readAllBytes(activeFile().toPath());
    TestMaterial next = current.nextPackage("beta", "beta-local");
    int[] writes = {0};
    RuntimeConfigPackageStore.AtomicWriter postReplacementFailure =
        (destination, payload) -> {
          RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
          if (writes[0]++ == 0) {
            throw new IOException("injected post-replacement durability failure");
          }
        };
    RuntimeConfigPackageStore failingStore = createStore(current, postReplacementFailure);

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(
            () ->
                failingStore.activate(
                    next.packageDocument,
                    next.packageDigest(),
                    next.trustDigest(),
                    activated.packageDigest));

    assertEquals("runtime_config_activation_write_failed", error.code);
    assertArrayEquals(previous, Files.readAllBytes(activeFile().toPath()));
    assertEquals(2, writes[0]);
    assertEquals(RuntimeConfigPackageStore.ReadKind.PRESENT, failingStore.readState().kind);
  }

  @Test
  public void successfulActivationReadsBackPackageTrustAndDigests() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store = createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());

    RuntimeConfigPackageStore.ActivationResult result = installFirst(store, material);
    RuntimeConfigPackageStore.ReadState state = store.readState();

    assertEquals(RuntimeConfigPackageStore.ReadKind.PRESENT, state.kind);
    assertEquals("present", state.payload.get("state"));
    assertEquals(result.packageDigest, state.payload.get("packageDigest"));
    assertEquals(result.trustEnvelopeDigest, state.payload.get("trustEnvelopeDigest"));
    assertTrue(state.payload.containsKey("package"));
    assertTrue(state.payload.containsKey("artifactTrustEnvelope"));
  }

  @Test
  public void canonicalJsonMatchesCanonicalContractForUnicodeAndKeyOrdering() throws Exception {
    JsonObject document = new JsonObject();
    document.addProperty("z", "趣我圈/路径");
    document.addProperty("a", true);

    assertEquals(
        "{\"a\":true,\"z\":\"趣我圈/路径\"}",
        new String(
            RuntimeConfigPackageStore.canonicalJsonBytes(document), StandardCharsets.UTF_8));
  }

  @Test
  public void trustDigestUsesCanonicalDocumentNotAssetWhitespace() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    byte[] paddedTrust =
        ("  " + GSON.toJson(material.trustDocument) + "\n")
            .getBytes(StandardCharsets.UTF_8);
    RuntimeConfigPackageStore store =
        new RuntimeConfigPackageStore(
            temporaryFolder.getRoot(),
            () -> new ByteArrayInputStream(paddedTrust),
            () -> NOW,
            RuntimeConfigPackageStore.durableAtomicWriter());

    RuntimeConfigPackageStore.ReadState state = store.readState();

    assertEquals(RuntimeConfigPackageStore.ReadKind.ABSENT, state.kind);
    assertEquals(material.trustDigest(), state.payload.get("trustEnvelopeDigest"));
    assertFalse(material.trustDigest().equals(sha256(paddedTrust)));
  }

  @Test
  public void coordinatorRejectsActivationRequestFieldDriftBeforeWrite() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(material, "");
    request.addProperty("extra", "forbidden");

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(writeActivationRequest(request));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_activation_request_malformed", result.errorCode);
    assertTrue(result.validationIssues.contains(result.errorCode));
    assertFalse(activeFile().exists());
  }

  @Test
  public void coordinatorActivatesBeforeDartAndProjectsManifestDigest() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(material, "");
    String requestDigest = sha256(RuntimeConfigPackageStore.canonicalJsonBytes(request));
    Files.write(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .toPath(),
        RuntimeConfigPackageStore.canonicalJsonBytes(request));

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(requestDigest);
    Map<String, Object> envelope = coordinator.readVerifiedFlutterEnvelope();

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    assertEquals(
        request.get("effectiveLaunchManifestDigest").getAsString(),
        envelope.get("effectiveLaunchManifestDigest"));
    assertEquals(material.packageDigest(), envelope.get("runtimeConfigPackageDigest"));
    assertEquals(material.trustDigest(), envelope.get("runtimeConfigTrustEnvelopeDigest"));
    assertFalse(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .exists());
    assertTrue(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)
            .isFile());
    assertTrue(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME)
            .isFile());
  }

  @Test
  public void coordinatorRestoresPreviousActiveReceiptWhenSecondReceiptWriteFails()
      throws Exception {
    TestMaterial current = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(current, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator initialCoordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject initialRequest = activationRequest(current, "");
    String initialRequestDigest = writeActivationRequest(initialRequest);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        initialCoordinator.consumePendingRequest(initialRequestDigest).kind);
    byte[] previousActivePackage = Files.readAllBytes(activeFile().toPath());
    File activeReceipt =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME);
    byte[] previousActiveReceipt = Files.readAllBytes(activeReceipt.toPath());
    String previousManifestDigest =
        initialRequest.get("effectiveLaunchManifestDigest").getAsString();

    TestMaterial next = current.nextPackage("alpha", "alpha-local");
    JsonObject nextRequest = activationRequest(next, current.packageDigest());
    String nextRequestDigest = writeActivationRequest(nextRequest);
    boolean[] failedSecondReceipt = {false};
    RuntimeConfigActivationCoordinator failingCoordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            (destination, payload) -> {
              if (destination.getName().equals(RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)
                  && !failedSecondReceipt[0]) {
                failedSecondReceipt[0] = true;
                throw new IOException("injected secondary receipt write failure");
              }
              RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
            },
            requestFile -> Files.deleteIfExists(requestFile.toPath()));

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        failingCoordinator.consumePendingRequest(nextRequestDigest);
    Map<String, Object> envelope = failingCoordinator.readVerifiedFlutterEnvelope();

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_activation_receipt_write_failed", result.errorCode);
    assertTrue(failedSecondReceipt[0]);
    assertArrayEquals(previousActivePackage, Files.readAllBytes(activeFile().toPath()));
    assertArrayEquals(previousActiveReceipt, Files.readAllBytes(activeReceipt.toPath()));
    assertEquals(current.packageDigest(), envelope.get("runtimeConfigPackageDigest"));
    assertEquals(previousManifestDigest, envelope.get("effectiveLaunchManifestDigest"));
  }

  @Test
  public void coordinatorTreatsRequestCleanupFailureAsCommittedActivation() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            RuntimeConfigPackageStore::writeDurablyAndReplace,
            requestFile -> {
              throw new IOException("injected request cleanup failure");
            });
    JsonObject request = activationRequest(material, "");
    String requestDigest = writeActivationRequest(request);

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(requestDigest);

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    assertTrue(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .isFile());
    assertEquals(
        material.packageDigest(),
        coordinator.readVerifiedFlutterEnvelope().get("runtimeConfigPackageDigest"));

    RuntimeConfigActivationCoordinator retryCoordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        retryCoordinator.consumePendingRequest(requestDigest).kind);
    assertFalse(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .exists());
  }

  @Test
  public void coordinatorRejectsManifestDigestDriftWithoutActivatingPackage() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(material, "");
    request.addProperty("effectiveLaunchManifestDigest", differentDigest());
    String requestDigest = sha256(RuntimeConfigPackageStore.canonicalJsonBytes(request));
    Files.write(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .toPath(),
        RuntimeConfigPackageStore.canonicalJsonBytes(request));

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(requestDigest);
    JsonObject receipt =
        JsonParser.parseString(
                Files.readString(
                    new File(
                            temporaryFolder.getRoot(),
                            RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)
                        .toPath()))
            .getAsJsonObject();

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_effective_manifest_digest_mismatch", result.errorCode);
    assertEquals("failed", receipt.get("status").getAsString());
    assertEquals(
        "runtime_config_effective_manifest_digest_mismatch",
        receipt.get("errorCode").getAsString());
    assertTrue(
        receipt
            .getAsJsonArray("validationIssues")
            .contains(
                new com.google.gson.JsonPrimitive(
                    "runtime_config_effective_manifest_digest_mismatch")));
    assertFalse(activeFile().exists());
  }

  @Test
  public void coordinatorReportsCorruptedActiveReceiptAsReceiptSemantics() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        coordinator
            .consumePendingRequest(writeActivationRequest(activationRequest(material, "")))
            .kind);
    File activeReceipt =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME);
    Files.write(activeReceipt.toPath(), "not-json".getBytes(StandardCharsets.UTF_8));

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(coordinator::readVerifiedFlutterEnvelope);

    assertEquals("runtime_config_activation_receipt_malformed", error.code);
  }

  @Test
  public void coordinatorReportsEmptyActiveReceiptAsReceiptSemantics() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        coordinator
            .consumePendingRequest(writeActivationRequest(activationRequest(material, "")))
            .kind);
    File activeReceipt =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME);
    Files.write(activeReceipt.toPath(), new byte[0]);

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(coordinator::readVerifiedFlutterEnvelope);

    assertEquals("runtime_config_activation_receipt_malformed", error.code);
  }

  @Test
  public void failureReceiptKeepsLastKnownActiveDigestWhenActiveReadFails() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    byte[] trustBytes = material.trustBytes();
    int[] loadsBeforeBreak = {-1};
    RuntimeConfigPackageStore store =
        new RuntimeConfigPackageStore(
            temporaryFolder.getRoot(),
            () -> {
              if (loadsBeforeBreak[0] == 0) {
                throw new IOException("injected trust read failure");
              }
              if (loadsBeforeBreak[0] > 0) {
                loadsBeforeBreak[0]--;
              }
              return new ByteArrayInputStream(trustBytes);
            },
            () -> NOW,
            RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        coordinator
            .consumePendingRequest(writeActivationRequest(activationRequest(material, "")))
            .kind);

    JsonObject driftedRequest = activationRequest(material, material.packageDigest());
    driftedRequest.addProperty("extra", "forbidden");
    String driftedDigest = writeActivationRequest(driftedRequest);
    loadsBeforeBreak[0] = 1;

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(driftedDigest);
    JsonObject receipt =
        JsonParser.parseString(
                Files.readString(
                    new File(
                            temporaryFolder.getRoot(),
                            RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)
                        .toPath()))
            .getAsJsonObject();

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_activation_request_malformed", result.errorCode);
    assertTrue(
        result.validationIssues.contains("runtime_config_activation_rollback_failed"));
    assertEquals(
        material.packageDigest(), receipt.get("previousActiveDigest").getAsString());
    assertEquals(
        material.packageDigest(), receipt.get("activePackageDigest").getAsString());
    assertEquals(
        "runtime_config_activation_request_malformed",
        receipt.get("errorCode").getAsString());
    assertTrue(
        receipt
            .getAsJsonArray("validationIssues")
            .contains(
                new com.google.gson.JsonPrimitive(
                    "runtime_config_activation_rollback_failed")));
  }

  private JsonObject activationRequest(TestMaterial material, String expectedActiveDigest)
      throws Exception {
    JsonObject transport = new JsonObject();
    transport.addProperty("required", false);
    transport.addProperty("reverseExpectedPorts", "");
    transport.addProperty("reverseActualPorts", "");
    transport.addProperty("reverseReceiptDigest", "");
    transport.addProperty("consumerLeaseId", "");
    JsonObject manifest = new JsonObject();
    manifest.addProperty("schema", "app-effective-launch-manifest");
    manifest.addProperty("environment", "alpha");
    manifest.addProperty("buildProfile", "nonprod");
    manifest.addProperty("target", "alpha-local");
    manifest.addProperty("entrypoint", "lib/main_prod.dart");
    manifest.addProperty("launchMode", "canonical_launcher");
    manifest.addProperty("launchPolicy", "test_live");
    manifest.addProperty("runtimeConfigPackageDigest", material.packageDigest());
    manifest.addProperty("runtimeConfigTrustEnvelopeDigest", material.trustDigest());
    manifest.addProperty("requiresLocalTransport", false);
    manifest.add("transport", transport);

    JsonObject request = new JsonObject();
    request.addProperty("schema", "app-runtime-config-activation-request");
    request.addProperty("schemaVersion", "1");
    request.addProperty("environment", "alpha");
    request.addProperty("buildProfile", "nonprod");
    request.addProperty("target", "alpha-local");
    request.add("package", material.packageDocument.deepCopy());
    request.addProperty("packageDigest", material.packageDigest());
    request.addProperty("trustEnvelopeDigest", material.trustDigest());
    request.add("effectiveLaunchManifest", manifest);
    request.addProperty(
        "effectiveLaunchManifestDigest",
        sha256(RuntimeConfigPackageStore.canonicalJsonBytes(manifest)));
    request.addProperty("expectedActiveDigest", expectedActiveDigest);
    return request;
  }

  private String writeActivationRequest(JsonObject request) throws Exception {
    byte[] payload = RuntimeConfigPackageStore.canonicalJsonBytes(request);
    Files.write(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .toPath(),
        payload);
    return sha256(payload);
  }

  private RuntimeConfigPackageStore createStore(
      TestMaterial material, RuntimeConfigPackageStore.AtomicWriter writer) throws Exception {
    File root = temporaryFolder.getRoot();
    byte[] trustBytes = material.trustBytes();
    return new RuntimeConfigPackageStore(
        root,
        () -> new ByteArrayInputStream(trustBytes),
        () -> NOW,
        writer);
  }

  private File activeFile() {
    return new File(temporaryFolder.getRoot(), RuntimeConfigPackageStore.PACKAGE_FILE_NAME);
  }

  private RuntimeConfigPackageStore.ActivationResult installFirst(
      RuntimeConfigPackageStore store, TestMaterial material) throws Exception {
    return store.activate(
        material.packageDocument, material.packageDigest(), material.trustDigest(), "");
  }

  private void assertInstallFails(TestMaterial material, String expectedCode) throws Exception {
    RuntimeConfigPackageStore store = createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(
            () ->
                store.activate(
                    material.packageDocument,
                    material.packageDigest(),
                    material.trustDigest(),
                    ""));
    assertEquals(expectedCode, error.code);
  }

  private static RuntimeConfigPackageStore.RuntimeConfigException expectFailure(
      ThrowingAction action) throws Exception {
    try {
      action.run();
      fail("expected runtime config failure");
      return null;
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      return error;
    }
  }

  private static void assertDigest(Object value) {
    assertTrue(value instanceof String);
    assertTrue(((String) value).matches("sha256:[0-9a-f]{64}"));
  }

  private static String differentDigest() {
    return "sha256:" + "0".repeat(64);
  }

  private interface ThrowingAction {
    void run() throws Exception;
  }

  private static final class TestMaterial {
    final Ed25519Sign signer;
    final String encodedPublicKey;
    final JsonObject trustDocument;
    final JsonObject packageDocument;

    private TestMaterial(
        Ed25519Sign signer,
        String encodedPublicKey,
        JsonObject trustDocument,
        JsonObject packageDocument) {
      this.signer = signer;
      this.encodedPublicKey = encodedPublicKey;
      this.trustDocument = trustDocument;
      this.packageDocument = packageDocument;
    }

    static TestMaterial create(String trustProfile) throws Exception {
      Ed25519Sign.KeyPair keyPair = Ed25519Sign.KeyPair.newKeyPair();
      Ed25519Sign signer = new Ed25519Sign(keyPair.getPrivateKey());
      String publicKey = Base64.getEncoder().encodeToString(keyPair.getPublicKey());
      JsonObject trust = new JsonObject();
      trust.addProperty("schema", "app-runtime-config-trust");
      trust.addProperty("schemaVersion", "1");
      trust.addProperty("buildProfile", trustProfile);
      trust.addProperty("signatureAlgorithm", "ed25519");
      JsonObject trustKeys = new JsonObject();
      trustKeys.addProperty("primary", publicKey);
      trust.add("trustedPublicKeys", trustKeys);

      JsonObject runtimePackage = new JsonObject();
      runtimePackage.addProperty("schema", "app-runtime-config-package");
      runtimePackage.addProperty("schemaVersion", "1");
      runtimePackage.addProperty("environment", "alpha");
      runtimePackage.addProperty("buildProfile", "nonprod");
      runtimePackage.addProperty("target", "alpha-local");
      runtimePackage.addProperty("launchPolicy", "test_live");
      runtimePackage.addProperty("issuedAt", "2026-08-22T23:55:00Z");
      runtimePackage.addProperty("expiresAt", "2026-08-23T23:55:00Z");
      runtimePackage.addProperty("sourceGitSha", "a".repeat(40));
      runtimePackage.addProperty("sourceTreeDigest", "sha256:" + "b".repeat(64));
      runtimePackage.add("runtime", runtimeValues("alpha"));
      runtimePackage.addProperty("payloadDigest", "");
      runtimePackage.addProperty("signatureAlgorithm", "ed25519");
      runtimePackage.addProperty("signatureKeyId", "primary");
      runtimePackage.add("trustedPublicKeys", trustKeys.deepCopy());
      runtimePackage.addProperty("signature", "");
      TestMaterial material = new TestMaterial(signer, publicKey, trust, runtimePackage);
      material.resign();
      return material;
    }

    TestMaterial nextPackage(String environment, String target) throws Exception {
      JsonObject next = packageDocument.deepCopy();
      next.addProperty("environment", environment);
      next.addProperty("target", target);
      next.getAsJsonObject("runtime").addProperty("appRuntimeEnv", environment);
      next.addProperty("sourceGitSha", "c".repeat(40));
      TestMaterial material =
          new TestMaterial(signer, encodedPublicKey, trustDocument.deepCopy(), next);
      material.resign();
      return material;
    }

    void resign() throws Exception {
      JsonObject digestInput = packageDocument.deepCopy();
      digestInput.remove("signature");
      digestInput.addProperty("payloadDigest", "");
      packageDocument.addProperty(
          "payloadDigest", sha256(RuntimeConfigPackageStore.canonicalJsonBytes(digestInput)));
      JsonObject signedPayload = packageDocument.deepCopy();
      signedPayload.remove("signature");
      packageDocument.addProperty(
          "signature",
          Base64.getEncoder()
              .encodeToString(signer.sign(RuntimeConfigPackageStore.canonicalJsonBytes(signedPayload))));
    }

    byte[] trustBytes() throws Exception {
      return RuntimeConfigPackageStore.canonicalJsonBytes(trustDocument);
    }

    String trustDigest() throws Exception {
      return sha256(trustBytes());
    }

    String packageDigest() throws Exception {
      return sha256(RuntimeConfigPackageStore.canonicalJsonBytes(packageDocument));
    }
    private static JsonObject runtimeValues(String environment) {
      JsonObject runtime = new JsonObject();
      runtime.addProperty("appRuntimeEnv", environment);
      runtime.addProperty("gatewayBaseUrl", "https://gateway.example.test");
      runtime.addProperty("legalBaseUrl", "https://legal.example.test");
      runtime.addProperty("publicWebBaseUrl", "https://web.example.test");
      runtime.addProperty("appDownloadBaseUrl", "https://download.example.test");
      runtime.addProperty("realtimeBaseUrl", "wss://realtime.example.test");
      runtime.addProperty("mediaAvatarCdnBaseUrl", "https://avatar.example.test");
      runtime.addProperty("mediaImageCdnBaseUrl", "https://image.example.test");
      runtime.addProperty("mediaVideoCdnBaseUrl", "https://video.example.test");
      runtime.addProperty("mediaUploadBaseUrl", "https://upload.example.test");
      runtime.addProperty("rtcMediaConnectionUrl", "wss://rtc.example.test");
      return runtime;
    }
  }

  private static String sha256(byte[] payload) throws Exception {
    byte[] digest = MessageDigest.getInstance("SHA-256").digest(payload);
    StringBuilder output = new StringBuilder("sha256:");
    for (byte value : digest) {
      output.append(String.format("%02x", value & 0xff));
    }
    return output.toString();
  }
}
