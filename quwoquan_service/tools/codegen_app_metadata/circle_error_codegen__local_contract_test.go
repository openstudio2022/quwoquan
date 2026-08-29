package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestCircleErrorGenerationKeepsObjectOwnership(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	circleErrors, err := readErrors(filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"circle",
		"errors.yaml",
	))
	if err != nil {
		t.Fatalf("read Circle errors: %v", err)
	}
	membershipErrors, err := readErrors(filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"circle_membership",
		"errors.yaml",
	))
	if err != nil {
		t.Fatalf("read CircleMembership errors: %v", err)
	}
	gatheringPlanErrors, err := readErrors(filepath.Join(
		metadataDir,
		"circle",
		"circle_management",
		"gathering_plan",
		"errors.yaml",
	))
	if err != nil {
		t.Fatalf("read GatheringPlan errors: %v", err)
	}

	circleOutput := renderSimpleErrorsDart(
		"CircleErrorCode",
		"circle/circle_management/circle/errors.yaml",
		"圈子服务异常，请稍后重试",
		circleErrors,
	)
	membershipOutput := renderSimpleErrorsDart(
		"CircleMembershipErrorCode",
		"circle/circle_management/circle_membership/errors.yaml",
		"圈子成员关系暂时不可用，请稍后重试",
		membershipErrors,
	)
	gatheringPlanOutput := renderSimpleErrorsDart(
		"GatheringPlanErrorCode",
		"circle/circle_management/gathering_plan/errors.yaml",
		"协作计划暂时不可用，请稍后重试",
		gatheringPlanErrors,
	)

	if strings.Contains(circleOutput, "CIRCLE.USER.membership_not_found") {
		t.Fatal("Circle aggregate error enum must not absorb CircleMembership errors")
	}
	for _, expected := range []string{
		"enum CircleMembershipErrorCode",
		"membershipNotFound('CIRCLE.USER.membership_not_found'",
		"CircleMembershipErrorMessages",
	} {
		if !strings.Contains(membershipOutput, expected) {
			t.Fatalf("CircleMembership error output missing %q", expected)
		}
	}
	for _, expected := range []string{
		"enum GatheringPlanErrorCode",
		"gatheringPlanNotFound('CIRCLE.USER.gathering_plan_not_found'",
		"GatheringPlanErrorMessages",
	} {
		if !strings.Contains(gatheringPlanOutput, expected) {
			t.Fatalf("GatheringPlan error output missing %q", expected)
		}
	}
}

func TestGatheringPlanErrorGenerationWritesOwnedArtifact(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-graph")

	if err := writeGatheringPlanErrorsDart(metadataDir, appDir); err != nil {
		t.Fatalf("write GatheringPlan errors: %v", err)
	}

	output := readGeneratedTestFile(t, runtimeErrorOutputPath(
		appDir,
		"circle",
		"gathering_plan_errors.g.dart",
	))
	if !strings.Contains(output, "enum GatheringPlanErrorCode") {
		t.Fatal("GatheringPlan generated error artifact is missing its typed enum")
	}
}
