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
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public final class RuntimeConfigPackageStoreTest {
  private static final Instant NOW = Instant.parse("2026-08-23T00:00:00Z");
  private static final Gson GSON = new Gson();

  @Rule public final TemporaryFolder temporaryFolder = new TemporaryFolder();

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
  @Test
  public void activationReaderSupportsShortReadsWithoutNewerAndroidStreamApi() throws Exception {
    byte[] payload = "{\"value\":\"short-read\"}".getBytes(StandardCharsets.UTF_8);
    ByteArrayInputStream input = new ByteArrayInputStream(payload) {
      @Override public byte[] readNBytes(int length) {
        throw new AssertionError("readNBytes is unavailable on API 31");
      }
      @Override public synchronized int read(byte[] buffer, int offset, int length) {
        return super.read(buffer, offset, Math.min(length, 3));
      }
    };
    assertEquals("short-read", RuntimeConfigActivationCoordinator.readStreamDocument(
        input, "runtime_config_activation_request_malformed").get("value").getAsString());
  }

  @Test
  public void activationReaderRejectsNumbersOutsideCanonicalDocumentContract() throws Exception {
    assertEquals("runtime_config_package_malformed", expectFailure(() ->
        RuntimeConfigActivationCoordinator.readStreamDocument(
            new ByteArrayInputStream("{\"value\":17}".getBytes(StandardCharsets.UTF_8)),
            "runtime_config_activation_request_malformed")).code);
  }

  @Test
  public void activationReaderEnforcesExactSizeBoundaryAndRejectsEmpty() throws Exception {
    byte[] boundary = new byte[RuntimeConfigPackageStore.MAX_BYTES];
    java.util.Arrays.fill(boundary, (byte) ' ');
    boundary[0] = '{';
    boundary[1] = '}';
    assertTrue(RuntimeConfigActivationCoordinator.readStreamDocument(
        new ByteArrayInputStream(boundary), "runtime_config_activation_request_malformed").entrySet().isEmpty());
    for (byte[] payload : new byte[][] {new byte[0], java.util.Arrays.copyOf(boundary, boundary.length + 1)}) {
      assertEquals("runtime_config_activation_request_malformed", expectFailure(() ->
          RuntimeConfigActivationCoordinator.readStreamDocument(new ByteArrayInputStream(payload),
              "runtime_config_activation_request_malformed")).code);
    }
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
  @Test
  public void offlineDocumentSurvivesNextDayWithoutEndpointAuthority() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    material.packageDocument.addProperty("schema", "app-offline-bootstrap-document");
    material.packageDocument.addProperty("environment", "alpha");
    material.packageDocument.addProperty("target", "alpha-local");
    material.packageDocument.addProperty("contentSource", "bundled_snapshot");
    material.packageDocument.addProperty("trustEnvelopeDigest", material.trustDigest());
    material.packageDocument.add("rehearsalSpace", standardRehearsalSpace());
    material.packageDocument.remove("issuedAt");
    material.packageDocument.remove("expiresAt");
    JsonObject runtime = new JsonObject();
    runtime.addProperty("appRuntimeEnv", "alpha");
    material.packageDocument.add("runtime", runtime);
    material.resign();
    RuntimeConfigPackageStore store = createStoreAt(material, RuntimeConfigPackageStore.durableAtomicWriter(), NOW.plusSeconds(86400 * 100));
    installFirst(store, material);
    assertEquals("present", store.readStateEnvelope().get("state"));
    assertFalse(store.networkAccessAllowed());
    assertEquals("runtime_config_network_forbidden", expectFailure(store::readRecoveryRuntimeValues).code);
    material.packageDocument.getAsJsonObject("runtime").addProperty("gatewayBaseUrl", "");
    material.resign();
    assertEquals("runtime_config_runtime_values_invalid", expectFailure(() -> store.activate(
        material.packageDocument, material.packageDigest(), material.trustDigest(),
        store.readCurrentActiveDigest())).code);
  }

  @Test
  public void selfSupplyDoesNotReplaceExpiredOrCorruptedRemoteActive() throws Exception {
    TestMaterial remote = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore initial = createStore(remote, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), initial);
    JsonObject remoteRequest = activationRequest(remote, "");
    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        coordinator.consumePendingRequest(writeActivationRequest(remoteRequest)).kind);
    byte[] previous = Files.readAllBytes(activeFile().toPath());
    TestMaterial offline = remote.nextPackage("alpha", "alpha-local");
    offline.packageDocument.addProperty("schema", "app-offline-bootstrap-document");
    offline.packageDocument.remove("issuedAt");
    offline.packageDocument.remove("expiresAt");
    offline.packageDocument.addProperty("contentSource", "bundled_snapshot");
    offline.packageDocument.addProperty("trustEnvelopeDigest", offline.trustDigest());
    offline.packageDocument.add("rehearsalSpace", standardRehearsalSpace());
    JsonObject runtime = new JsonObject();
    runtime.addProperty("appRuntimeEnv", "alpha");
    offline.packageDocument.add("runtime", runtime);
    offline.resign();
    JsonObject request = activationRequest(offline, "");
    request.addProperty("environment", "alpha");
    request.addProperty("target", "alpha-local");
    JsonObject manifest = request.getAsJsonObject("effectiveLaunchManifest");
    manifest.addProperty("environment", "alpha");
    manifest.addProperty("target", "alpha-local");
    manifest.addProperty("contentSource", "bundled_snapshot");
    manifest.addProperty("entrypoint", AppLaunchContract.APP_EFFECTIVE_LAUNCH_MANIFEST_ENTRYPOINT.get("bundled_snapshot"));
    manifest.addProperty("requiresLocalTransport", false);
    manifest.addProperty("runtimeConfigSupplyMode", "build_time_self_supply");
    refreshEffectiveManifestDigest(request);
    RuntimeConfigPackageStore stale = createStoreAt(remote, RuntimeConfigPackageStore.durableAtomicWriter(), NOW.plusSeconds(86400 * 2));
    RuntimeConfigActivationCoordinator staleCoordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), stale);
    RuntimeConfigActivationCoordinator.ConsumeResult expiredResult = staleCoordinator.consumeBundledSelfSupplyRequest(
        new ByteArrayInputStream(RuntimeConfigPackageStore.canonicalJsonBytes(request)));
    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, expiredResult.kind);
    assertEquals("runtime_config_freshness_invalid", expiredResult.errorCode);
    assertArrayEquals(previous, Files.readAllBytes(activeFile().toPath()));
    Files.writeString(activeFile().toPath(), "broken");
    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED,
        staleCoordinator.consumeBundledSelfSupplyRequest(new ByteArrayInputStream(
            RuntimeConfigPackageStore.canonicalJsonBytes(request))).kind);
    assertEquals("broken", Files.readString(activeFile().toPath()));
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyMigratesFreshAndExpiredRetiredAlphaOnlineIdentity() throws Exception {
    TestMaterial oldAlpha = TestMaterial.create("nonprod").nextPackage("alpha", "alpha-local");
    TestMaterial offline = offlineMaterial(oldAlpha);
    for (Instant now : List.of(NOW, NOW.plusSeconds(86400 * 2))) {
      // 退役在线包不能通过当前候选入口安装；模拟升级前已持久化的签名字节。
      Files.write(activeFile().toPath(), RuntimeConfigPackageStore.canonicalJsonBytes(oldAlpha.packageDocument));
      RuntimeConfigPackageStore store = createStoreAt(offline, RuntimeConfigPackageStore.durableAtomicWriter(), now);
      RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
      JsonObject request = selfSupplyRequest(offline);
      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, selfSupply(coordinator, request).kind);
      assertEquals(oldAlpha.packageDigest(), readLaunchReceipt().get("previousActiveDigest").getAsString());
      assertCurrentSelfSupply(coordinator, offline, request);
      assertFalse(store.networkAccessAllowed());
    }
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyRepairsMissingMalformedAndDriftedOfflineReceipts() throws Exception {
    TestMaterial offline = offlineMaterial(TestMaterial.create("nonprod"));
    RuntimeConfigPackageStore store = createStore(offline, RuntimeConfigPackageStore.durableAtomicWriter());
    installFirst(store, offline);
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = selfSupplyRequest(offline);
    File receiptFile = activeReceiptFile();
    for (String corruption : List.of("missing", "malformed", "mismatch")) {
      if (corruption.equals("missing")) {
        Files.deleteIfExists(receiptFile.toPath());
      } else if (corruption.equals("malformed")) {
        Files.writeString(receiptFile.toPath(), "not-json");
      } else {
        JsonObject receipt = readLaunchReceipt();
        receipt.addProperty("activePackageDigest", differentDigest());
        Files.write(receiptFile.toPath(), RuntimeConfigPackageStore.canonicalJsonBytes(receipt));
      }
      expectFailure(coordinator::readVerifiedFlutterEnvelope);
      assertEquals(corruption, RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, selfSupply(coordinator, request).kind);
      assertCurrentSelfSupply(coordinator, offline, request);
    }
    // 同一文档但当前 manifest 已改变，也必须写入本次 request 的 receipts。
    request.getAsJsonObject("effectiveLaunchManifest").addProperty("launchProvenance", "workspace_ide_debug");
    refreshEffectiveManifestDigest(request);
    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, selfSupply(coordinator, request).kind);
    assertCurrentSelfSupply(coordinator, offline, request);
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void repeatedSelfSupplyRevalidatesAndKeepsCompleteOfflineState() throws Exception {
    TestMaterial offline = offlineMaterial(TestMaterial.create("nonprod"));
    RuntimeConfigPackageStore store = createStore(offline, RuntimeConfigPackageStore.durableAtomicWriter());
    JsonObject request = selfSupplyRequest(offline);
    for (int launch = 0; launch < 3; launch++) {
      RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, selfSupply(coordinator, request).kind);
      assertCurrentSelfSupply(coordinator, offline, request);
    }
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyPreservesValidBetaGammaAndRejectsExpiredOnes() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    for (String environment : List.of("beta", "gamma")) {
      TestMaterial remote = material.nextPackage(environment, environment + "-local");
      RuntimeConfigPackageStore store = createStore(remote, RuntimeConfigPackageStore.durableAtomicWriter());
      RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
      JsonObject remoteRequest = activationRequest(remote, store.readCurrentActiveDigest());
      remoteRequest.addProperty("environment", environment);
      remoteRequest.addProperty("target", environment + "-local");
      remoteRequest.getAsJsonObject("effectiveLaunchManifest").addProperty("environment", environment);
      remoteRequest.getAsJsonObject("effectiveLaunchManifest").addProperty("target", environment + "-local");
      refreshEffectiveManifestDigest(remoteRequest);
      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
          coordinator.consumePendingRequest(writeActivationRequest(remoteRequest)).kind);
      byte[] before = Files.readAllBytes(activeFile().toPath());
      byte[] receiptBefore = Files.readAllBytes(activeReceiptFile().toPath());
      JsonObject request = selfSupplyRequest(offlineMaterial(remote));
      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.NOT_REQUESTED, selfSupply(coordinator, request).kind);
      assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
      assertArrayEquals(receiptBefore, Files.readAllBytes(activeReceiptFile().toPath()));
      RuntimeConfigActivationCoordinator stale = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(),
          createStoreAt(remote, RuntimeConfigPackageStore.durableAtomicWriter(), NOW.plusSeconds(86400 * 2)));
      assertEquals("runtime_config_freshness_invalid", selfSupply(stale, request).errorCode);
      assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
      assertArrayEquals(receiptBefore, Files.readAllBytes(activeReceiptFile().toPath()));
    }
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyRejectsCorruptAlphaIdentityAndPreservesFirstError() throws Exception {
    TestMaterial oldAlpha = TestMaterial.create("nonprod").nextPackage("alpha", "alpha-local");
    TestMaterial offline = offlineMaterial(oldAlpha);
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(),
        createStoreAt(offline, RuntimeConfigPackageStore.durableAtomicWriter(), NOW.plusSeconds(86400 * 2)));
    for (String corruption : List.of("signature", "structure", "digest")) {
      JsonObject broken = oldAlpha.packageDocument.deepCopy();
      String expected;
      if (corruption.equals("signature")) {
        broken.addProperty("signature", Base64.getEncoder().encodeToString(new byte[64]));
        expected = "runtime_config_signature_invalid";
      } else if (corruption.equals("structure")) {
        broken.addProperty("unknown", "field");
        expected = "runtime_config_schema_mismatch";
      } else {
        broken.addProperty("payloadDigest", differentDigest());
        expected = "runtime_config_payload_digest_mismatch";
      }
      byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(broken);
      Files.write(activeFile().toPath(), before);
      assertEquals(expected, selfSupply(coordinator, selfSupplyRequest(offline)).errorCode);
      assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    }
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyRejectsInvalidNewSignatureBeforeRepairingReceipt() throws Exception {
    TestMaterial offline = offlineMaterial(TestMaterial.create("nonprod"));
    RuntimeConfigPackageStore store = createStore(offline, RuntimeConfigPackageStore.durableAtomicWriter());
    installFirst(store, offline);
    byte[] before = Files.readAllBytes(activeFile().toPath());
    offline.packageDocument.addProperty("signature", Base64.getEncoder().encodeToString(new byte[64]));
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    assertEquals("runtime_config_signature_invalid", selfSupply(coordinator, selfSupplyRequest(offline)).errorCode);
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    assertFalse(activeReceiptFile().exists());
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyReceiptWriteFailureRestoresPreviousOfflinePackageAndReceipt() throws Exception {
    TestMaterial offline = offlineMaterial(TestMaterial.create("nonprod"));
    RuntimeConfigPackageStore store = createStore(offline, RuntimeConfigPackageStore.durableAtomicWriter());
    installFirst(store, offline);
    byte[] before = Files.readAllBytes(activeFile().toPath());
    Files.writeString(activeReceiptFile().toPath(), "old-malformed-receipt");
    TestMaterial next = offline.nextPackage("alpha", "alpha-local");
    boolean[] failed = {false};
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store,
        (destination, payload) -> {
          if (destination.getName().equals(RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME) && !failed[0]) {
            failed[0] = true;
            throw new IOException("injected self-supply receipt failure");
          }
          RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
        }, requestFile -> Files.deleteIfExists(requestFile.toPath()));
    assertEquals("runtime_config_activation_receipt_write_failed", selfSupply(coordinator, selfSupplyRequest(next)).errorCode);
    assertTrue(failed[0]);
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    assertEquals("old-malformed-receipt", Files.readString(activeReceiptFile().toPath()));
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyTrustIoFailureKeepsOldPackageAndOriginalError() throws Exception {
    TestMaterial oldAlpha = TestMaterial.create("nonprod").nextPackage("alpha", "alpha-local");
    byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(oldAlpha.packageDocument);
    Files.write(activeFile().toPath(), before);
    RuntimeConfigPackageStore store = new RuntimeConfigPackageStore(temporaryFolder.getRoot(),
        () -> { throw new IOException("injected trust read failure"); }, () -> NOW,
        RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    RuntimeConfigActivationCoordinator.ConsumeResult result = selfSupply(coordinator, selfSupplyRequest(offlineMaterial(oldAlpha)));
    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_trust_read_failed", result.errorCode);
    assertEquals("runtime_config_trust_read_failed", result.validationIssues.get(0));
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
  @Test
  public void selfSupplyReceiptPathFailureRollsBackWithoutBypassingIoValidation() throws Exception {
    TestMaterial oldAlpha = TestMaterial.create("nonprod").nextPackage("alpha", "alpha-local");
    byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(oldAlpha.packageDocument);
    Files.write(activeFile().toPath(), before);
    Files.createDirectory(activeReceiptFile().toPath());
    RuntimeConfigActivationCoordinator coordinator = new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(),
        createStore(oldAlpha, RuntimeConfigPackageStore.durableAtomicWriter()));
    assertEquals("runtime_config_package_path_invalid", selfSupply(coordinator, selfSupplyRequest(offlineMaterial(oldAlpha))).errorCode);
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    assertTrue(activeReceiptFile().isDirectory());
  }

  private TestMaterial offlineMaterial(TestMaterial material) throws Exception {
    TestMaterial offline = material.nextPackage("alpha", "alpha-local");
    offline.packageDocument.addProperty("schema", "app-offline-bootstrap-document");
    offline.packageDocument.remove("issuedAt");
    offline.packageDocument.remove("expiresAt");
    offline.packageDocument.addProperty("contentSource", "bundled_snapshot");
    offline.packageDocument.addProperty("trustEnvelopeDigest", offline.trustDigest());
    JsonObject runtime = new JsonObject();
    runtime.addProperty("appRuntimeEnv", "alpha");
    offline.packageDocument.add("runtime", runtime);
    offline.resign();
    return offline;
  }

  private JsonObject selfSupplyRequest(TestMaterial offline) throws Exception {
    JsonObject request = activationRequest(offline, "");
    request.addProperty("environment", "alpha");
    request.addProperty("target", "alpha-local");
    JsonObject manifest = request.getAsJsonObject("effectiveLaunchManifest");
    manifest.addProperty("environment", "alpha");
    manifest.addProperty("target", "alpha-local");
    manifest.addProperty("contentSource", "bundled_snapshot");
    manifest.addProperty("requiresLocalTransport", false);
    manifest.addProperty("runtimeConfigSupplyMode", "build_time_self_supply");
    refreshEffectiveManifestDigest(request);
    return request;
  }

  private RuntimeConfigActivationCoordinator.ConsumeResult selfSupply(
      RuntimeConfigActivationCoordinator coordinator, JsonObject request) throws Exception {
    return coordinator.consumeBundledSelfSupplyRequest(
        new ByteArrayInputStream(RuntimeConfigPackageStore.canonicalJsonBytes(request)));
  }

  private File activeReceiptFile() {
    return new File(temporaryFolder.getRoot(), RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME);
  }

  private void assertCurrentSelfSupply(RuntimeConfigActivationCoordinator coordinator,
      TestMaterial offline, JsonObject request) throws Exception {
    Map<String, Object> envelope = coordinator.readVerifiedFlutterEnvelope();
    assertEquals(offline.packageDigest(), envelope.get("runtimeConfigPackageDigest"));
    assertEquals(request.get("effectiveLaunchManifestDigest").getAsString(), envelope.get("effectiveLaunchManifestDigest"));
    assertEquals(sha256(RuntimeConfigPackageStore.canonicalJsonBytes(request)), readLaunchReceipt().get("requestDigest").getAsString());
    assertArrayEquals(RuntimeConfigPackageStore.canonicalJsonBytes(readLaunchReceipt()), Files.readAllBytes(activeReceiptFile().toPath()));
  }

  @Test
  public void canonicalActivationReplacesExactPreviousLayoutOfflinePredecessor() throws Exception {
    TestMaterial historical = TestMaterial.create("nonprod");
    TestMaterial candidate = historical.nextPackage("beta", "beta-local");
    makeOfflineBootstrap(historical, false);
    byte[] previousLayoutBytes = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
    Files.write(activeFile().toPath(), previousLayoutBytes);
    writePreviousLayoutActiveReceipt(historical);

    RuntimeConfigPackageStore store =
        createStore(historical, RuntimeConfigPackageStore.durableAtomicWriter());
    assertEquals("runtime_config_schema_mismatch", store.readState().error.code);

    JsonObject request = activationRequest(candidate, historical.packageDigest());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(writeActivationRequest(request));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    assertEquals(candidate.packageDigest(), store.readCurrentActiveDigest());
    assertFalse(java.util.Arrays.equals(previousLayoutBytes, Files.readAllBytes(activeFile().toPath())));
  }

  @Test
  public void canonicalActivationAcceptsPreviousLayoutSelfSupplyReceiptAndPreservesHistory()
      throws Exception {
    TestMaterial historical = TestMaterial.create("nonprod");
    TestMaterial candidate = historical.nextPackage("beta", "beta-local");
    makeOfflineBootstrap(historical, false);
    byte[] packageBytes = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
    Files.write(activeFile().toPath(), packageBytes);
    byte[] receiptBytes = writePreviousLayoutActiveReceipt(historical, "build_time_self_supply");
    RuntimeConfigPackageStore store =
        createStore(historical, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);

    RuntimeConfigActivationCoordinator.ConsumeResult result = coordinator.consumePendingRequest(
        writeActivationRequest(activationRequest(candidate, historical.packageDigest())));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    File history = previousLayoutHistoryDirectory(historical.packageDigest());
    assertArrayEquals(packageBytes, Files.readAllBytes(
        new File(history, RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_PACKAGE_FILE_NAME).toPath()));
    assertArrayEquals(receiptBytes, Files.readAllBytes(
        new File(history, RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_RECEIPT_FILE_NAME).toPath()));
    JsonObject audit = JsonParser.parseString(Files.readString(
        new File(history, RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_AUDIT_FILE_NAME).toPath()))
        .getAsJsonObject();
    assertEquals(2, audit.size());
    assertEquals(historical.packageDigest(), audit.get("packageDigest").getAsString());
    assertEquals(sha256(receiptBytes), audit.get("receiptDigest").getAsString());
  }

  @Test
  public void previousLayoutPredecessorStillRequiresCanonicalExternalActivationRequest()
      throws Exception {
    TestMaterial historical = TestMaterial.create("nonprod");
    TestMaterial candidate = historical.nextPackage("beta", "beta-local");
    makeOfflineBootstrap(historical, false);
    byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
    Files.write(activeFile().toPath(), before);
    writePreviousLayoutActiveReceipt(historical, "build_time_self_supply");
    RuntimeConfigPackageStore store =
        createStore(historical, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(candidate, historical.packageDigest());
    request.getAsJsonObject("effectiveLaunchManifest")
        .addProperty("runtimeConfigSupplyMode", "build_time_self_supply");
    refreshEffectiveManifestDigest(request);

    RuntimeConfigActivationCoordinator.ConsumeResult result = coordinator.consumePendingRequest(
        writeActivationRequest(request));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_activation_identity_mismatch", result.errorCode);
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    assertFalse(previousLayoutHistoryDirectory(historical.packageDigest()).exists());
  }

  @Test
  public void canonicalActivationReusesExactPreviousLayoutMigrationHistory() throws Exception {
    TestMaterial historical = TestMaterial.create("nonprod");
    TestMaterial candidate = historical.nextPackage("beta", "beta-local");
    makeOfflineBootstrap(historical, false);
    byte[] packageBytes = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
    Files.write(activeFile().toPath(), packageBytes);
    byte[] receiptBytes = writePreviousLayoutActiveReceipt(historical);
    writeExactPreviousLayoutHistory(historical.packageDigest(), packageBytes, receiptBytes);
    RuntimeConfigPackageStore store =
        createStore(historical, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);

    RuntimeConfigActivationCoordinator.ConsumeResult result = coordinator.consumePendingRequest(
        writeActivationRequest(activationRequest(candidate, historical.packageDigest())));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    assertEquals(candidate.packageDigest(), store.readCurrentActiveDigest());
  }

  @Test
  public void previousLayoutHistoryCollisionOrWriteFailureDoesNotReplaceActive() throws Exception {
    for (boolean collision : new boolean[] {true, false}) {
      temporaryFolder.delete();
      temporaryFolder.create();
      TestMaterial historical = TestMaterial.create("nonprod");
      TestMaterial candidate = historical.nextPackage("beta", "beta-local");
      makeOfflineBootstrap(historical, false);
      byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
      Files.write(activeFile().toPath(), before);
      writePreviousLayoutActiveReceipt(historical);
      RuntimeConfigPackageStore.AtomicWriter writer =
          RuntimeConfigPackageStore.durableAtomicWriter();
      if (collision) {
        File history = previousLayoutHistoryDirectory(historical.packageDigest());
        assertTrue(history.mkdirs());
        Files.writeString(
            new File(history, RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_PACKAGE_FILE_NAME).toPath(),
            "collision");
      } else {
        writer = (destination, payload) -> {
          if (destination.getParentFile().getParentFile().getName().equals(
              RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_HISTORY_DIRECTORY)) {
            throw new IOException("injected history write failure");
          }
          RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
        };
      }
      RuntimeConfigPackageStore store = createStore(historical, writer);
      RuntimeConfigActivationCoordinator coordinator =
          new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);

      RuntimeConfigActivationCoordinator.ConsumeResult result = coordinator.consumePendingRequest(
          writeActivationRequest(activationRequest(candidate, historical.packageDigest())));

      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
      assertEquals("runtime_config_activation_write_failed", result.errorCode);
      assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    }
  }

  @Test
  public void canonicalActivationRejectsUnknownOrTamperedPreviousLayoutPredecessor() throws Exception {
    for (boolean unknownShape : new boolean[] {true, false}) {
      temporaryFolder.delete();
      temporaryFolder.create();
      TestMaterial historical = TestMaterial.create("nonprod");
      TestMaterial candidate = historical.nextPackage("beta", "beta-local");
      makeOfflineBootstrap(historical, false);
      if (unknownShape) {
        historical.packageDocument.addProperty("unknownPreviousLayoutField", "forbidden");
        historical.resign();
      } else {
        historical.packageDocument.getAsJsonObject("runtime")
            .addProperty("appRuntimeEnv", "tampered");
      }
      byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
      Files.write(activeFile().toPath(), before);
      writePreviousLayoutActiveReceipt(historical);
      RuntimeConfigPackageStore store =
          createStore(historical, RuntimeConfigPackageStore.durableAtomicWriter());
      RuntimeConfigActivationCoordinator coordinator =
          new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);

      RuntimeConfigActivationCoordinator.ConsumeResult result = coordinator.consumePendingRequest(
          writeActivationRequest(activationRequest(candidate, historical.packageDigest())));

      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
      assertTrue(result.errorCode.equals("runtime_config_schema_mismatch")
          || result.errorCode.equals("runtime_config_runtime_values_invalid")
          || result.errorCode.equals("runtime_config_payload_digest_mismatch"));
      assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
    }
  }

  @Test
  public void canonicalActivationRollbackRestoresPreviousLayoutOfflinePredecessor() throws Exception {
    TestMaterial historical = TestMaterial.create("nonprod");
    TestMaterial candidate = historical.nextPackage("beta", "beta-local");
    makeOfflineBootstrap(historical, false);
    byte[] before = RuntimeConfigPackageStore.canonicalJsonBytes(historical.packageDocument);
    Files.write(activeFile().toPath(), before);
    writePreviousLayoutActiveReceipt(historical);
    boolean[] failed = {false};
    RuntimeConfigPackageStore store =
        createStore(historical, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            (destination, payload) -> {
              if (destination.getName().equals(
                      RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)
                  && !failed[0]) {
                failed[0] = true;
                throw new IOException("injected receipt failure");
              }
              RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
            },
            requestFile -> Files.deleteIfExists(requestFile.toPath()));

    RuntimeConfigActivationCoordinator.ConsumeResult result = coordinator.consumePendingRequest(
        writeActivationRequest(activationRequest(candidate, historical.packageDigest())));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_activation_receipt_write_failed", result.errorCode);
    assertTrue(failed[0]);
    assertArrayEquals(before, Files.readAllBytes(activeFile().toPath()));
  }

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
  public void staleActivePackageKeepsIdentityReadableAndReplaceable() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore installStore =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigPackageStore.ActivationResult first = installFirst(installStore, material);

    // 同一磁盘状态，时钟推进到 active 包 expiresAt 之后。
    Instant afterExpiry = Instant.parse("2026-08-25T00:00:00Z");
    RuntimeConfigPackageStore staleStore =
        createStoreAt(material, RuntimeConfigPackageStore.durableAtomicWriter(), afterExpiry);

    // 消费路径必须继续 fail-closed。
    RuntimeConfigPackageStore.ReadState staleState = staleStore.readState();
    assertEquals(RuntimeConfigPackageStore.ReadKind.FAILURE, staleState.kind);
    assertEquals("runtime_config_freshness_invalid", staleState.error.code);

    // 激活身份读取豁免时间窗：CAS 前值 digest 必须仍可读，不得死锁。
    assertEquals(first.packageDigest, staleStore.readCurrentActiveDigest());

    // 同一 keyring 的新 fresh 包按 expected active digest 替换激活必须成功。
    material.packageDocument.addProperty("issuedAt", "2026-08-24T23:00:00Z");
    material.packageDocument.addProperty("expiresAt", "2026-08-25T23:00:00Z");
    material.resign();
    RuntimeConfigPackageStore.ActivationResult second =
        staleStore.activate(
            material.packageDocument,
            material.packageDigest(),
            material.trustDigest(),
            first.packageDigest);

    assertEquals(first.packageDigest, second.previousActiveDigest);
    assertEquals(material.packageDigest(), second.packageDigest);
    assertEquals(RuntimeConfigPackageStore.ReadKind.PRESENT, staleStore.readState().kind);
  }

  @Test
  public void staleIdentityReadDoesNotRelaxSignatureOrTrustValidation() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore installStore =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    installFirst(installStore, material);

    // 篡改磁盘上的 active 包正文：即使在激活身份读取模式下也必须 fail-closed。
    byte[] stored = Files.readAllBytes(activeFile().toPath());
    JsonObject tampered = JsonParser.parseString(
            new String(stored, StandardCharsets.UTF_8))
        .getAsJsonObject();
    tampered.getAsJsonObject("runtime")
        .addProperty("gatewayBaseUrl", "https://attacker.example.test");
    Files.write(
        activeFile().toPath(),
        RuntimeConfigPackageStore.canonicalJsonBytes(tampered));

    Instant afterExpiry = Instant.parse("2026-08-25T00:00:00Z");
    RuntimeConfigPackageStore staleStore =
        createStoreAt(material, RuntimeConfigPackageStore.durableAtomicWriter(), afterExpiry);

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(staleStore::readCurrentActiveDigest);
    assertEquals("runtime_config_payload_digest_mismatch", error.code);
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
  public void canonicalJsonDoesNotHtmlEscapeSharedDigestAlphabet() throws Exception {
    // 与执行体侧 Python json.dumps 的字节级一致性：base64 padding `=` 与
    // URL 字符 `&<>'` 必须原样输出，HTML-safe 转义会造成激活 digest 漂移。
    JsonObject document = new JsonObject();
    document.addProperty("signature", "AbC+dEf=");
    document.addProperty("url", "https://api.example.test/path?a=1&b=<2>'");

    assertEquals(
        "{\"signature\":\"AbC+dEf=\","
            + "\"url\":\"https://api.example.test/path?a=1&b=<2>'\"}",
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

    JsonObject malformedNestedPackage = activationRequest(material, "");
    malformedNestedPackage.getAsJsonObject("package").remove("launchPolicy");
    RuntimeConfigActivationCoordinator.ConsumeResult nestedResult =
        coordinator.consumePendingRequest(writeActivationRequest(malformedNestedPackage));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, nestedResult.kind);
    assertEquals("runtime_config_activation_request_malformed", nestedResult.errorCode);
  }

  @Test
  public void coordinatorSeparatesRequestMissingReadMalformedAndInternalFailures()
      throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);

    RuntimeConfigActivationCoordinator.ConsumeResult missing =
        coordinator.consumePendingRequest(differentDigest());

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, missing.kind);
    assertEquals("runtime_config_activation_request_missing", missing.errorCode);
    JsonObject missingReceipt = readLaunchReceipt();
    for (String field :
        List.of(
            "environment",
            "buildProfile",
            "target",
            "launchProvenance",
            "runtimeConfigSupplyMode",
            "packageDigest",
            "trustEnvelopeDigest",
            "effectiveLaunchManifestDigest")) {
      assertEquals("", missingReceipt.get(field).getAsString());
    }

    List<String> nativeLogs = new ArrayList<>();
    Files.write(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .toPath(),
        "{}".getBytes(StandardCharsets.UTF_8));
    RuntimeConfigActivationCoordinator readFailureCoordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            RuntimeConfigPackageStore::writeDurablyAndReplace,
            requestFile -> Files.deleteIfExists(requestFile.toPath()),
            (requestFile, malformedCode) -> {
              throw new IOException("injected request read failure");
            },
            (errorCode, error) -> nativeLogs.add(errorCode));

    RuntimeConfigActivationCoordinator.ConsumeResult readFailure =
        readFailureCoordinator.consumePendingRequest(differentDigest());

    assertEquals("runtime_config_activation_request_read_failed", readFailure.errorCode);
    assertTrue(nativeLogs.contains(readFailure.errorCode));

    Files.write(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .toPath(),
        "{".getBytes(StandardCharsets.UTF_8));
    RuntimeConfigActivationCoordinator.ConsumeResult malformed =
        coordinator.consumePendingRequest(differentDigest());

    assertEquals("runtime_config_activation_request_malformed", malformed.errorCode);

    nativeLogs.clear();
    Files.write(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .toPath(),
        "{}".getBytes(StandardCharsets.UTF_8));
    RuntimeConfigActivationCoordinator internalFailureCoordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            RuntimeConfigPackageStore::writeDurablyAndReplace,
            requestFile -> Files.deleteIfExists(requestFile.toPath()),
            (requestFile, malformedCode) -> {
              throw new IllegalStateException("injected unexpected failure");
            },
            (errorCode, error) -> nativeLogs.add(errorCode));

    RuntimeConfigActivationCoordinator.ConsumeResult internalFailure =
        internalFailureCoordinator.consumePendingRequest(differentDigest());

    assertEquals("runtime_config_internal_failure", internalFailure.errorCode);
    assertTrue(nativeLogs.contains(internalFailure.errorCode));
  }

  @Test
  public void coordinatorRejectsEveryInvalidEffectiveManifestTransportShape()
      throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    List<JsonObject> invalidRequests = new ArrayList<>();

    JsonObject wrongTopology = activationRequest(material, "");
    wrongTopology
        .getAsJsonObject("effectiveLaunchManifest")
        .addProperty("requiresLocalTransport", false);
    invalidRequests.add(wrongTopology);

    JsonObject wrongRequiredType = activationRequest(material, "");
    wrongRequiredType
        .getAsJsonObject("effectiveLaunchManifest")
        .getAsJsonObject("transport")
        .addProperty("required", "false");
    invalidRequests.add(wrongRequiredType);

    JsonObject mismatchedPorts = activationRequest(material, "");
    JsonObject transport =
        mismatchedPorts
            .getAsJsonObject("effectiveLaunchManifest")
            .getAsJsonObject("transport");
    transport.addProperty("required", true);
    transport.addProperty("reverseExpectedPorts", "8080,9090");
    transport.addProperty("reverseActualPorts", "8080");
    transport.addProperty("reverseReceiptDigest", differentDigest());
    transport.addProperty("consumerLeaseId", differentDigest());
    invalidRequests.add(mismatchedPorts);

    for (JsonObject request : invalidRequests) {
      refreshEffectiveManifestDigest(request);

      RuntimeConfigActivationCoordinator.ConsumeResult result =
          coordinator.consumePendingRequest(writeActivationRequest(request));

      assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
      assertEquals("runtime_config_effective_manifest_malformed", result.errorCode);
      assertFalse(activeFile().exists());
    }
  }

  @Test
  public void coordinatorAcceptsCompleteBoundLocalTransportManifest() throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(material, "");
    JsonObject transport =
        request
            .getAsJsonObject("effectiveLaunchManifest")
            .getAsJsonObject("transport");
    transport.addProperty("required", true);
    transport.addProperty("reverseExpectedPorts", "9090, 8080,8080");
    transport.addProperty("reverseActualPorts", "8080,9090");
    transport.addProperty("reverseReceiptDigest", differentDigest());
    transport.addProperty("consumerLeaseId", differentDigest());
    refreshEffectiveManifestDigest(request);

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        coordinator.consumePendingRequest(writeActivationRequest(request));

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    assertTrue(activeFile().isFile());
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
    assertEquals("canonical_launcher", envelope.get("launchProvenance"));
    assertEquals("external_runtime_package", envelope.get("runtimeConfigSupplyMode"));
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

    TestMaterial next = current.nextPackage("beta", "beta-local");
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
  public void alreadyActivatedExplicitRequestRepublishesExactCanonicalActiveReceipt()
      throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator coordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(material, "");
    String requestDigest = writeActivationRequest(request);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        coordinator.consumePendingRequest(requestDigest).kind);
    File activeReceipt =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME);
    File launchReceipt =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME);
    byte[] activeReceiptBytes = Files.readAllBytes(activeReceipt.toPath());
    byte[] activePackageBytes = Files.readAllBytes(activeFile().toPath());
    Files.writeString(launchReceipt.toPath(), "stale-launch-receipt");
    writeActivationRequest(request);
    List<String> writtenFiles = new ArrayList<>();
    RuntimeConfigActivationCoordinator retryCoordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            (destination, payload) -> {
              writtenFiles.add(destination.getName());
              assertArrayEquals(activeReceiptBytes, payload);
              RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
            },
            pendingRequest -> Files.deleteIfExists(pendingRequest.toPath()));

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        retryCoordinator.consumePendingRequest(requestDigest);

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED, result.kind);
    assertEquals(List.of(RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME), writtenFiles);
    assertArrayEquals(activeReceiptBytes, Files.readAllBytes(launchReceipt.toPath()));
    assertArrayEquals(activeReceiptBytes, Files.readAllBytes(activeReceipt.toPath()));
    assertArrayEquals(activePackageBytes, Files.readAllBytes(activeFile().toPath()));
    assertFalse(
        new File(
                temporaryFolder.getRoot(),
                RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME)
            .exists());
  }

  @Test
  public void alreadyActivatedExplicitRequestBlocksWhenLaunchReceiptRepublishFails()
      throws Exception {
    TestMaterial material = TestMaterial.create("nonprod");
    RuntimeConfigPackageStore store =
        createStore(material, RuntimeConfigPackageStore.durableAtomicWriter());
    RuntimeConfigActivationCoordinator initialCoordinator =
        new RuntimeConfigActivationCoordinator(temporaryFolder.getRoot(), store);
    JsonObject request = activationRequest(material, "");
    String requestDigest = writeActivationRequest(request);
    assertEquals(
        RuntimeConfigActivationCoordinator.ConsumeKind.ACTIVATED,
        initialCoordinator.consumePendingRequest(requestDigest).kind);
    File activeReceipt =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME);
    byte[] activeReceiptBytes = Files.readAllBytes(activeReceipt.toPath());
    byte[] activePackageBytes = Files.readAllBytes(activeFile().toPath());
    File requestFile =
        new File(
            temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.REQUEST_FILE_NAME);
    writeActivationRequest(request);
    int[] activeReceiptWrites = {0};
    RuntimeConfigActivationCoordinator failingCoordinator =
        new RuntimeConfigActivationCoordinator(
            temporaryFolder.getRoot(),
            store,
            (destination, payload) -> {
              if (destination.getName().equals(
                  RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)) {
                throw new IOException("injected launch receipt republish failure");
              }
              activeReceiptWrites[0]++;
              RuntimeConfigPackageStore.writeDurablyAndReplace(destination, payload);
            },
            pendingRequest -> Files.deleteIfExists(pendingRequest.toPath()));

    RuntimeConfigActivationCoordinator.ConsumeResult result =
        failingCoordinator.consumePendingRequest(requestDigest);

    assertEquals(RuntimeConfigActivationCoordinator.ConsumeKind.FAILED, result.kind);
    assertEquals("runtime_config_activation_receipt_write_failed", result.errorCode);
    assertTrue(result.validationIssues.contains(result.errorCode));
    assertEquals(0, activeReceiptWrites[0]);
    assertArrayEquals(activeReceiptBytes, Files.readAllBytes(activeReceipt.toPath()));
    assertArrayEquals(activePackageBytes, Files.readAllBytes(activeFile().toPath()));
    assertTrue(requestFile.isFile());
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
    assertEquals("beta", receipt.get("environment").getAsString());
    assertEquals("nonprod", receipt.get("buildProfile").getAsString());
    assertEquals("beta-local", receipt.get("target").getAsString());
    assertEquals("canonical_launcher", receipt.get("launchProvenance").getAsString());
    assertEquals(
        "external_runtime_package", receipt.get("runtimeConfigSupplyMode").getAsString());
    assertEquals(material.packageDigest(), receipt.get("packageDigest").getAsString());
    assertEquals(material.trustDigest(), receipt.get("trustEnvelopeDigest").getAsString());
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
  public void coordinatorRejectsUnregisteredLaunchProvenanceInActiveReceipt() throws Exception {
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
    JsonObject receipt =
        JsonParser.parseString(Files.readString(activeReceipt.toPath())).getAsJsonObject();
    receipt.addProperty("launchProvenance", "previousLayout_unknown_launcher");
    Files.write(activeReceipt.toPath(), RuntimeConfigPackageStore.canonicalJsonBytes(receipt));

    RuntimeConfigPackageStore.RuntimeConfigException error =
        expectFailure(coordinator::readVerifiedFlutterEnvelope);

    assertEquals("runtime_config_activation_receipt_mismatch", error.code);
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

  private void makeOfflineBootstrap(TestMaterial material, boolean includeRehearsalSpace)
      throws Exception {
    material.packageDocument.addProperty("schema", "app-offline-bootstrap-document");
    material.packageDocument.addProperty("environment", "alpha");
    material.packageDocument.addProperty("target", "alpha-local");
    material.packageDocument.addProperty("contentSource", "bundled_snapshot");
    material.packageDocument.addProperty("trustEnvelopeDigest", material.trustDigest());
    material.packageDocument.remove("issuedAt");
    material.packageDocument.remove("expiresAt");
    JsonObject runtime = new JsonObject();
    runtime.addProperty("appRuntimeEnv", "alpha");
    material.packageDocument.add("runtime", runtime);
    if (includeRehearsalSpace) {
      material.packageDocument.add("rehearsalSpace", standardRehearsalSpace());
    } else {
      material.packageDocument.remove("rehearsalSpace");
    }
    material.resign();
  }

  private static JsonObject standardRehearsalSpace() {
    JsonObject rehearsalSpace = new JsonObject();
    rehearsalSpace.addProperty("mode", "standard");
    rehearsalSpace.addProperty("snapshotDigest", differentDigest());
    rehearsalSpace.addProperty("instanceId", "default");
    return rehearsalSpace;
  }

  private byte[] writePreviousLayoutActiveReceipt(TestMaterial historical) throws Exception {
    return writePreviousLayoutActiveReceipt(historical, "external_runtime_package");
  }

  private byte[] writePreviousLayoutActiveReceipt(TestMaterial historical, String supplyMode) throws Exception {
    JsonObject receipt = new JsonObject();
    receipt.addProperty("schema", "app-runtime-config-activation-receipt");
    receipt.addProperty("status", "activated");
    receipt.addProperty("requestDigest", differentDigest());
    receipt.addProperty("environment", "alpha");
    receipt.addProperty("buildProfile", "nonprod");
    receipt.addProperty("target", "alpha-local");
    receipt.addProperty("launchProvenance", "canonical_launcher");
    receipt.addProperty("runtimeConfigSupplyMode", supplyMode);
    receipt.addProperty("packageDigest", historical.packageDigest());
    receipt.addProperty("trustEnvelopeDigest", historical.trustDigest());
    receipt.addProperty("effectiveLaunchManifestDigest", differentDigest());
    receipt.addProperty("previousActiveDigest", "");
    receipt.addProperty("activePackageDigest", historical.packageDigest());
    receipt.addProperty("errorCode", "");
    receipt.add("validationIssues", new com.google.gson.JsonArray());
    byte[] receiptBytes = RuntimeConfigPackageStore.canonicalJsonBytes(receipt);
    Files.write(
        new File(temporaryFolder.getRoot(),
            RuntimeConfigActivationCoordinator.ACTIVE_RECEIPT_FILE_NAME).toPath(),
        receiptBytes);
    return receiptBytes;
  }

  private File previousLayoutHistoryDirectory(String packageDigest) {
    return new File(
        new File(temporaryFolder.getRoot(),
            RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_HISTORY_DIRECTORY),
        packageDigest.substring("sha256:".length()));
  }

  private void writeExactPreviousLayoutHistory(
      String packageDigest, byte[] packageBytes, byte[] receiptBytes) throws Exception {
    File history = previousLayoutHistoryDirectory(packageDigest);
    assertTrue(history.mkdirs());
    Files.write(new File(history,
        RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_PACKAGE_FILE_NAME).toPath(), packageBytes);
    Files.write(new File(history,
        RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_RECEIPT_FILE_NAME).toPath(), receiptBytes);
    JsonObject audit = new JsonObject();
    audit.addProperty("packageDigest", packageDigest);
    audit.addProperty("receiptDigest", sha256(receiptBytes));
    Files.write(new File(history,
        RuntimeConfigPackageStore.PREVIOUS_LAYOUT_MIGRATION_AUDIT_FILE_NAME).toPath(),
        RuntimeConfigPackageStore.canonicalJsonBytes(audit));
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
    manifest.addProperty("environment", "beta");
    manifest.addProperty("buildProfile", "nonprod");
    manifest.addProperty("target", "beta-local");
    manifest.addProperty("entrypoint", "lib/main_prod.dart");
    manifest.addProperty("launchProvenance", "canonical_launcher");
    manifest.addProperty("runtimeConfigSupplyMode", "external_runtime_package");
    manifest.addProperty("contentSource", "remote");
    manifest.addProperty("launchPolicy", "test_live");
    manifest.addProperty("runtimeConfigPackageDigest", material.packageDigest());
    manifest.addProperty("runtimeConfigTrustEnvelopeDigest", material.trustDigest());
    manifest.addProperty("requiresLocalTransport", true);
    manifest.add("transport", transport);

    JsonObject request = new JsonObject();
    request.addProperty("schema", "app-runtime-config-activation-request");
    request.addProperty("environment", "beta");
    request.addProperty("buildProfile", "nonprod");
    request.addProperty("target", "beta-local");
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

  private void refreshEffectiveManifestDigest(JsonObject request) throws Exception {
    request.addProperty(
        "effectiveLaunchManifestDigest",
        sha256(
            RuntimeConfigPackageStore.canonicalJsonBytes(
                request.getAsJsonObject("effectiveLaunchManifest"))));
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

  private JsonObject readLaunchReceipt() throws Exception {
    return JsonParser.parseString(
            Files.readString(
                new File(
                        temporaryFolder.getRoot(),
                        RuntimeConfigActivationCoordinator.RECEIPT_FILE_NAME)
                    .toPath()))
        .getAsJsonObject();
  }

  private RuntimeConfigPackageStore createStore(
      TestMaterial material, RuntimeConfigPackageStore.AtomicWriter writer) throws Exception {
    return createStoreAt(material, writer, NOW);
  }

  private RuntimeConfigPackageStore createStoreAt(
      TestMaterial material, RuntimeConfigPackageStore.AtomicWriter writer, Instant now)
      throws Exception {
    File root = temporaryFolder.getRoot();
    byte[] trustBytes = material.trustBytes();
    return new RuntimeConfigPackageStore(
        root,
        () -> new ByteArrayInputStream(trustBytes),
        () -> now,
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
      trust.addProperty("buildProfile", trustProfile);
      trust.addProperty("signatureAlgorithm", "ed25519");
      JsonObject trustKeys = new JsonObject();
      trustKeys.addProperty("primary", publicKey);
      trust.add("trustedPublicKeys", trustKeys);

      JsonObject runtimePackage = new JsonObject();
      runtimePackage.addProperty("schema", "app-runtime-config-package");
      runtimePackage.addProperty("environment", "beta");
      runtimePackage.addProperty("buildProfile", "nonprod");
      runtimePackage.addProperty("target", "beta-local");
      runtimePackage.addProperty("launchPolicy", "test_live");
      runtimePackage.addProperty("issuedAt", "2026-08-22T23:55:00Z");
      runtimePackage.addProperty("expiresAt", "2026-08-23T23:55:00Z");
      runtimePackage.addProperty("sourceGitSha", "a".repeat(40));
      runtimePackage.addProperty("sourceTreeDigest", "sha256:" + "b".repeat(64));
      runtimePackage.add("runtime", runtimeValues("beta"));
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
