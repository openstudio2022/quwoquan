package main

import (
	"strings"
	"testing"
)

func TestRecommendationPatchEnumRefsUseCanonicalClassNames(t *testing.T) {
	t.Parallel()

	contract := recPatchContract{}
	contract.ClientCodegen.PatchTypeEnum = "FeedRealtimePatchType"
	contract.ClientCodegen.ReasonCodeEnum = "FeedPatchReasonCode"
	contract.ClientCodegen.RemovalDimensionEnum = "FeedPatchRemovalDimension"

	for _, canonical := range []string{
		"FeedRealtimePatchType",
		"FeedPatchReasonCode",
		"FeedPatchRemovalDimension",
	} {
		if actual := contract.enumClassFor(canonical); actual != canonical {
			t.Fatalf("enum ref %q resolved to %q", canonical, actual)
		}
	}
	for _, retiredAlias := range []string{"patch_type", "reason_code", "removal_dimension"} {
		if actual := contract.enumClassFor(retiredAlias); actual != "" {
			t.Fatalf("retired enum alias %q must fail closed, got %q", retiredAlias, actual)
		}
	}
}

func TestRecommendationPatchEnumsAndDigestFailClosed(t *testing.T) {
	t.Parallel()

	contract := recPatchContract{}
	contract.ClientCodegen.PatchTypeEnum = "FeedRealtimePatchType"
	contract.ClientCodegen.ReasonCodeEnum = "FeedPatchReasonCode"
	contract.ClientCodegen.RemovalDimensionEnum = "FeedPatchRemovalDimension"
	contract.ClientCodegen.EnvelopeClass = "FeedRealtimePatch"
	contract.PatchTypes = append(contract.PatchTypes, struct {
		ID          string `yaml:"id"`
		Disruption  string `yaml:"disruption"`
		Description string `yaml:"description"`
	}{ID: "refresh_suggestion"})
	contract.EnvelopeFields = append(contract.EnvelopeFields, recPatchEnvelopeField{
		Name:     "policyDigest",
		Type:     "string",
		DartType: "String",
		Format:   "canonical_sha256",
		Nullable: true,
	})

	output := renderRecommendationFeedPatchesDart("contract.yaml", &contract)
	for _, forbidden := range []string{
		"unknown('')",
		"return FeedRealtimePatchType.unknown",
		"前向兼容",
		"whereType<String>",
		"as num?",
	} {
		if strings.Contains(output, forbidden) {
			t.Fatalf("generated patch parser retained fallback %q", forbidden)
		}
	}
	for _, required := range []string{
		"throw FormatException",
		"_optionalCanonicalSha256",
		"isCanonicalSha256Digest",
		"_requiredNonEmptyString",
	} {
		if !strings.Contains(output, required) {
			t.Fatalf("generated patch parser missing strict contract %q", required)
		}
	}
}
