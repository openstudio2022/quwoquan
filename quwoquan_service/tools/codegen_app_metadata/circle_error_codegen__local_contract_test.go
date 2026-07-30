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
}
