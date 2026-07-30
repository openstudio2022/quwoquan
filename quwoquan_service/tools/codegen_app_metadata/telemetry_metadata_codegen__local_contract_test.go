package main

import (
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-001
func TestTelemetryEnumValuesAreGeneratedAndValidatedInAppCatalog(t *testing.T) {
	catalog := telemetryCatalogForEnumTest()
	if err := validateTelemetryMetadata(
		catalog,
		&appPagesFile{Pages: []appPageDef{{PageName: "home", RouteID: "home"}}},
		&appRoutesFile{Routes: []appRouteDef{{ID: "home"}}},
	); err != nil {
		t.Fatalf("validate telemetry enum catalog: %v", err)
	}

	rendered := renderAppTelemetryCatalogDart(catalog)
	for _, want := range []string{
		"abstract final class AppTelemetryValueSeekEvidenceSource",
		"sourceSwitchNativeSettled = \"source_switch_native_settled\"",
		"sourceSwitchPositionReadbackNativeUnsupported = \"source_switch_position_readback_native_unsupported\"",
		"sourceSwitchNativeSettleTimeout = \"source_switch_native_settle_timeout\"",
		"sourceSwitchSettleUnsupported = \"source_switch_settle_unsupported\"",
		"sourceSwitchCommandFailed = \"source_switch_command_failed\"",
		"sourceSwitchSuperseded = \"source_switch_superseded\"",
		"return 'invalid_extension_value'",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("generated App telemetry catalog missing %q:\n%s", want, rendered)
		}
	}
}

func TestTelemetryEnumRejectsNonStringAndDartNameCollisions(t *testing.T) {
	tests := []struct {
		name   string
		values []string
		kind   string
	}{
		{name: "non string", values: []string{"one"}, kind: "int"},
		{name: "duplicate", values: []string{"one", "one"}, kind: "string"},
		{name: "Dart collision", values: []string{"source-switch", "source_switch"}, kind: "string"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			catalog := telemetryCatalogForEnumTest()
			catalog.ExtensionFields["seekEvidenceSource"] = telemetryExtensionDef{
				Type: test.kind,
				Enum: test.values,
			}
			err := validateTelemetryMetadata(
				catalog,
				&appPagesFile{Pages: []appPageDef{{PageName: "home", RouteID: "home"}}},
				&appRoutesFile{Routes: []appRouteDef{{ID: "home"}}},
			)
			if err == nil {
				t.Fatal("invalid telemetry enum must fail closed")
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002
func TestContentFeatureFlagNamesAreGeneratedFromUIConfig(t *testing.T) {
	rendered := renderContentUIConfigDart(&uiConfigFile{
		FeatureFlags: []featureFlagDef{{
			Flag:    "enable_hls_cmaf_abr",
			Default: false,
		}},
	})
	if !strings.Contains(
		rendered,
		"static const String enableHlsCmafAbr = \"enable_hls_cmaf_abr\";",
	) {
		t.Fatalf("generated Content feature flag name missing:\n%s", rendered)
	}
}

func telemetryCatalogForEnumTest() *telemetryEventCatalogFile {
	return &telemetryEventCatalogFile{
		LogTypes:          []string{"event", "error"},
		NetworkClasses:    []string{"wifi", "ethernet", "5g", "4g", "mobile", "other", "none"},
		CommonFields:      append([]string(nil), telemetryCommonFields...),
		ContextExtensions: []string{"devicePlatform"},
		ExtensionFields: map[string]telemetryExtensionDef{
			"devicePlatform": {Type: "string"},
			"seekEvidenceSource": {
				Type: "string",
				Enum: []string{
					"controller_command_completion",
					"native_settled",
					"source_switch_native_settled",
					"source_switch_position_readback_native_unsupported",
					"source_switch_native_settle_timeout",
					"source_switch_settle_unsupported",
					"source_switch_command_failed",
					"source_switch_superseded",
				},
			},
		},
		Events: []telemetryEventDef{{
			EventType:          "video_playback_qoe",
			LogType:            "event",
			RequiredExtensions: []string{"seekEvidenceSource"},
			NormalSampleRate:   1,
		}},
	}
}
