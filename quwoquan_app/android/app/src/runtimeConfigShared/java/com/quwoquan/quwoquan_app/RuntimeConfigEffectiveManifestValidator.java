package com.quwoquan.quwoquan_app;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;

/** Validates the complete generated effective-launch-manifest contract at the native gate. */
final class RuntimeConfigEffectiveManifestValidator {
  private static final Pattern DIGEST_PATTERN = Pattern.compile("^sha256:[0-9a-f]{64}$");
  private static final String SCHEMA = requireGeneratedSchema("app_effective_launch_manifest");

  private RuntimeConfigEffectiveManifestValidator() {}

  static boolean isValid(JsonObject manifest) {
    if (!hasExactFields(
            manifest, AppLaunchContract.APP_EFFECTIVE_LAUNCH_MANIFEST_REQUIRED_FIELDS)
        || !SCHEMA.equals(stringValue(manifest, "schema"))) {
      return false;
    }

    String environment = stringValue(manifest, "environment");
    String buildProfile = stringValue(manifest, "buildProfile");
    String target = stringValue(manifest, "target");
    String launchPolicy = stringValue(manifest, "launchPolicy");
    List<String> profileEnvironments =
        AppLaunchContract.BUILD_PROFILE_ENVIRONMENTS.get(buildProfile);
    if (!AppLaunchContract.ENVIRONMENTS.contains(environment)
        || !environment.equals(AppLaunchContract.TARGET_ENVIRONMENT.get(target))
        || profileEnvironments == null
        || !profileEnvironments.contains(environment)
        || !AppLaunchContract.BUILD_PROFILE_LAUNCH_POLICIES
            .get(buildProfile)
            .equals(launchPolicy)
        || !AppLaunchContract.APP_EFFECTIVE_LAUNCH_MANIFEST_ENTRYPOINT.equals(
            stringValue(manifest, "entrypoint"))
        || !AppLaunchContract.LAUNCH_PROVENANCES.contains(
            stringValue(manifest, "launchProvenance"))
        || !AppLaunchContract.RUNTIME_CONFIG_SUPPLY_MODES.contains(
            stringValue(manifest, "runtimeConfigSupplyMode"))
        || !isDigest(stringValue(manifest, "runtimeConfigPackageDigest"))
        || !isDigest(stringValue(manifest, "runtimeConfigTrustEnvelopeDigest"))) {
      return false;
    }

    Boolean requiresLocalTransport = booleanValue(manifest, "requiresLocalTransport");
    boolean targetRequiresLocalTransport =
        AppLaunchContract.LOCAL_TRANSPORT_TARGETS.contains(target);
    if (requiresLocalTransport == null
        || requiresLocalTransport.booleanValue() != targetRequiresLocalTransport) {
      return false;
    }

    JsonElement rawTransport = manifest.get("transport");
    if (rawTransport == null || !rawTransport.isJsonObject()) {
      return false;
    }
    JsonObject transport = rawTransport.getAsJsonObject();
    if (!hasExactFields(
        transport, AppLaunchContract.APP_EFFECTIVE_LAUNCH_MANIFEST_TRANSPORT_REQUIRED_FIELDS)) {
      return false;
    }
    Boolean required = booleanValue(transport, "required");
    String expectedPorts = stringValue(transport, "reverseExpectedPorts");
    String actualPorts = stringValue(transport, "reverseActualPorts");
    String receiptDigest = stringValue(transport, "reverseReceiptDigest");
    String consumerLeaseId = stringValue(transport, "consumerLeaseId");
    if (required == null
        || expectedPorts == null
        || actualPorts == null
        || receiptDigest == null
        || consumerLeaseId == null) {
      return false;
    }
    if (!required) {
      return expectedPorts.isEmpty()
          && actualPorts.isEmpty()
          && receiptDigest.isEmpty()
          && consumerLeaseId.isEmpty();
    }
    if (!targetRequiresLocalTransport
        || !isDigest(receiptDigest)
        || !isDigest(consumerLeaseId)) {
      return false;
    }
    Set<Integer> canonicalExpectedPorts = parsePorts(expectedPorts);
    Set<Integer> canonicalActualPorts = parsePorts(actualPorts);
    return canonicalExpectedPorts != null
        && canonicalExpectedPorts.equals(canonicalActualPorts);
  }

  private static Set<Integer> parsePorts(String raw) {
    Set<Integer> ports = new TreeSet<>();
    for (String value : raw.split(",", -1)) {
      String normalized = value.trim();
      if (normalized.isEmpty()) {
        continue;
      }
      if (!normalized.chars().allMatch(Character::isDigit)) {
        return null;
      }
      try {
        int port = Integer.parseInt(normalized);
        if (port <= 0 || port > 65535) {
          return null;
        }
        ports.add(port);
      } catch (NumberFormatException error) {
        return null;
      }
    }
    return ports.isEmpty() ? null : ports;
  }

  private static boolean hasExactFields(JsonObject object, List<String> expected) {
    return object.keySet().size() == expected.size() && object.keySet().containsAll(expected);
  }

  private static String stringValue(JsonObject object, String key) {
    JsonElement raw = object.get(key);
    return raw != null && raw.isJsonPrimitive() && raw.getAsJsonPrimitive().isString()
        ? raw.getAsString()
        : null;
  }

  private static Boolean booleanValue(JsonObject object, String key) {
    JsonElement raw = object.get(key);
    if (raw == null || !raw.isJsonPrimitive()) {
      return null;
    }
    JsonPrimitive primitive = raw.getAsJsonPrimitive();
    return primitive.isBoolean() ? primitive.getAsBoolean() : null;
  }

  private static boolean isDigest(String value) {
    return value != null && DIGEST_PATTERN.matcher(value).matches();
  }

  private static String requireGeneratedSchema(String schemaName) {
    String value = AppLaunchContract.SCHEMA_VALUES.get(schemaName);
    if (value == null || value.isEmpty()) {
      throw new IllegalStateException("Generated App launch schema is missing: " + schemaName);
    }
    return value;
  }
}
