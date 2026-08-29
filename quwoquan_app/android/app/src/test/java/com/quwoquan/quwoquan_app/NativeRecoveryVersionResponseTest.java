// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
package com.quwoquan.quwoquan_app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import org.junit.Test;

public final class NativeRecoveryVersionResponseTest {
  private static final String TRUSTED_ORIGIN = "https://download.quwoquan.example";
  private static final String UPDATE_URL = TRUSTED_ORIGIN + "/download/android";
  private static final String RECOVERY_URL = TRUSTED_ORIGIN + "/download";

  @Test
  public void androidCanonicalWirePreservesEightFieldsAndDerivedUpdateAction() {
    NativeRecoveryVersionResponse response =
        parseAndroid(androidPayload("available", jsonString(UPDATE_URL), RECOVERY_URL), 18100);

    assertEquals("android", response.platform);
    assertEquals("1.8.2", response.latestVersion);
    assertEquals(18201, response.latestBuild);
    assertEquals("1.8.0", response.minimumSupportedVersion);
    assertEquals(18000, response.minimumSupportedBuild);
    assertEquals(NativeRecoveryVersionResponse.UpdateState.AVAILABLE, response.updateState);
    assertEquals(UPDATE_URL, response.updateUrl);
    assertEquals(RECOVERY_URL, response.recoveryUrl);
    assertTrue(response.offersNativeUpdate());
  }

  @Test
  public void androidRequiredAndNoneStatesRemainBuildDerived() {
    NativeRecoveryVersionResponse required =
        parseAndroid(androidPayload("required", jsonString(UPDATE_URL), RECOVERY_URL), 17999);
    assertEquals(NativeRecoveryVersionResponse.UpdateState.REQUIRED, required.updateState);
    assertTrue(required.offersNativeUpdate());

    NativeRecoveryVersionResponse none =
        parseAndroid(androidPayload("none", jsonString(UPDATE_URL), RECOVERY_URL), 18201);
    assertEquals(NativeRecoveryVersionResponse.UpdateState.NONE, none.updateState);
    assertFalse(none.offersNativeUpdate());
  }

  @Test
  public void iosCanonicalNullNeverCreatesNativeUpdateAction() {
    NativeRecoveryVersionResponse response =
        NativeRecoveryVersionResponse.parse(
            iosPayload("available"), "ios", 18100, this::isTrusted);

    assertEquals(NativeRecoveryVersionResponse.UpdateState.AVAILABLE, response.updateState);
    assertNull(response.updateUrl);
    assertFalse(response.offersNativeUpdate());
  }

  @Test
  public void parserRejectsNonCanonicalFieldsAndPolicyContradictions() {
    String canonical = androidPayload("available", jsonString(UPDATE_URL), RECOVERY_URL);
    expectRejected(canonical.substring(0, canonical.length() - 1) + ",\"extra\":true}", 18100);
    expectRejected(canonical.replace("\"latestVersion\":\"1.8.2\",", ""), 18100);
    expectRejected(canonical.replace("\"platform\":\"android\"", "\"platform\":\"ios\""), 18100);
    expectRejected(canonical.replace("\"latestVersion\":\"1.8.2\"", "\"latestVersion\":\" \""), 18100);
    expectRejected(canonical.replace("\"minimumSupportedBuild\":\"18000\"", "\"minimumSupportedBuild\":\"19000\""), 18100);
    expectRejected(canonical.replace("\"updateState\":\"available\"", "\"updateState\":\"none\""), 18100);
    expectRejected(canonical.replace(jsonString(UPDATE_URL), "null"), 18100);
    expectRejected(canonical.replace(UPDATE_URL, "https://attacker.example/update"), 18100);
    expectRejected(canonical.replace(RECOVERY_URL, "https://attacker.example/recovery"), 18100);
    expectRejected(canonical.replace("\"latestBuild\":\"18201\"", "\"latestBuild\":\"0\""), 18100);
    expectRejected(canonical, 0);
  }

  private NativeRecoveryVersionResponse parseAndroid(String payload, long currentBuild) {
    return NativeRecoveryVersionResponse.parse(
        payload, "android", currentBuild, this::isTrusted);
  }

  private void expectRejected(String payload, long currentBuild) {
    try {
      parseAndroid(payload, currentBuild);
      fail("expected version response rejection: " + payload);
    } catch (IllegalArgumentException expected) {
      // typed fail-closed boundary
    }
  }

  private boolean isTrusted(String rawUrl) {
    return rawUrl != null
        && (rawUrl.equals(TRUSTED_ORIGIN) || rawUrl.startsWith(TRUSTED_ORIGIN + "/"));
  }

  private static String androidPayload(
      String updateState, String updateUrlJSON, String recoveryUrl) {
    return "{"
        + "\"platform\":\"android\","
        + "\"latestVersion\":\"1.8.2\","
        + "\"latestBuild\":\"18201\","
        + "\"minimumSupportedVersion\":\"1.8.0\","
        + "\"minimumSupportedBuild\":\"18000\","
        + "\"updateState\":"
        + jsonString(updateState)
        + ",\"updateUrl\":"
        + updateUrlJSON
        + ",\"recoveryUrl\":"
        + jsonString(recoveryUrl)
        + "}";
  }

  private static String iosPayload(String updateState) {
    return androidPayload(updateState, "null", RECOVERY_URL)
        .replace("\"platform\":\"android\"", "\"platform\":\"ios\"");
  }

  private static String jsonString(String value) {
    return "\"" + value + "\"";
  }
}
