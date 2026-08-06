package main

import (
	"os"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestLegacyAPIMetadataEmittersAreRetired(t *testing.T) {
	t.Parallel()

	checks := map[string][]string{
		"main.go": {
			"_api_" + "metadata.g.dart",
			"auth_" + "policy.g.dart",
			"integration_" + "location_metadata.g.dart",
			"renderDomain" + "APIMetadataDart",
			"renderCanonical" + "AuthPolicyDart",
			"renderIntegration" + "LocationMetadataDart",
		},
		"api_metadata_codegen.go": {
			"renderDomain" + "APIMetadataDart",
			"renderAuth" + "PolicyDart",
			"renderCanonical" + "AuthPolicyDart",
			"class Auth" + "ApiPolicy",
		},
		"metadata_readers.go": {
			"readIntegration" + "LocationService",
			"collectProjection" + "ReadModelDartClass",
		},
		"metadata_types.go": {
			"integrationLocation" + "ServiceFile",
			"route" + "Security",
			"resolveAuth" + "Mode",
		},
		"metadata_helpers.go": {
			"collectRoute" + "Prefixes",
		},
	}
	for path, forbidden := range checks {
		source, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		for _, value := range forbidden {
			if strings.Contains(string(source), value) {
				t.Errorf("%s retains legacy API metadata emitter %q", path, value)
			}
		}
	}

	if _, err := os.Stat("integration_location_metadata_codegen.go"); !os.IsNotExist(err) {
		t.Errorf("retired integration location metadata generator still exists: %v", err)
	}

	apiSource, err := os.ReadFile("api_metadata_codegen.go")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(apiSource), "renderDomainRequestPageIDsDart") {
		t.Fatal("domain request-page ID emitter was retired with legacy API metadata")
	}

	registrySource, err := os.ReadFile("operation_contract_codegen.go")
	if err != nil {
		t.Fatal(err)
	}
	for _, canonicalOwner := range []string{
		"AppCloudOperationIds",
		"appCloudOperationContracts",
		"GeneratedCloudOperationClient",
	} {
		if !strings.Contains(string(registrySource), canonicalOwner) {
			t.Errorf("canonical operation registry lost %s", canonicalOwner)
		}
	}
}
