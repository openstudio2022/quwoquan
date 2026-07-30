package local_contract

import (
	"bufio"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"
)

func TestCircleErrorsHaveExactlyOneObjectOwner(t *testing.T) {
	t.Parallel()

	expected := map[string][]string{
		"circle": {
			"CIRCLE.SYSTEM.circle_storage_write_failed",
			"CIRCLE.SYSTEM.internal_error",
			"CIRCLE.USER.circle_archived",
			"CIRCLE.USER.circle_idempotency_conflict",
			"CIRCLE.USER.circle_version_conflict",
			"CIRCLE.USER.invalid_argument",
			"CIRCLE.USER.not_found",
			"CIRCLE.USER.permission_denied",
		},
		"circle_behavior_fact": {
			"CIRCLE.SYSTEM.behavior_fact_write_failed",
			"CIRCLE.USER.behavior_fact_idempotency_conflict",
		},
		"circle_file": {
			"CIRCLE.SYSTEM.file_storage_write_failed",
			"CIRCLE.USER.file_asset_invalid",
			"CIRCLE.USER.file_idempotency_conflict",
			"CIRCLE.USER.file_not_found",
			"CIRCLE.USER.file_parent_invalid",
			"CIRCLE.USER.file_version_conflict",
			"CIRCLE.USER.storage_quota_exceeded",
		},
		"circle_group": {
			"CIRCLE.SYSTEM.group_storage_write_failed",
			"CIRCLE.USER.group_archived",
			"CIRCLE.USER.group_default_cannot_archive",
			"CIRCLE.USER.group_default_conflict",
			"CIRCLE.USER.group_idempotency_conflict",
			"CIRCLE.USER.group_not_found",
			"CIRCLE.USER.group_parent_invalid",
			"CIRCLE.USER.group_version_conflict",
		},
		"circle_group_membership": {
			"CIRCLE.SYSTEM.group_membership_storage_write_failed",
			"CIRCLE.USER.group_membership_already_active",
			"CIRCLE.USER.group_membership_full",
			"CIRCLE.USER.group_membership_idempotency_conflict",
			"CIRCLE.USER.group_membership_not_found",
			"CIRCLE.USER.group_membership_owner_cannot_leave",
			"CIRCLE.USER.group_membership_owner_cannot_remove",
			"CIRCLE.USER.group_membership_role_invalid",
			"CIRCLE.USER.group_membership_state_conflict",
			"CIRCLE.USER.group_membership_version_conflict",
		},
		"circle_membership": {
			"CIRCLE.SYSTEM.membership_storage_write_failed",
			"CIRCLE.USER.join_approval_required",
			"CIRCLE.USER.membership_already_active",
			"CIRCLE.USER.membership_idempotency_conflict",
			"CIRCLE.USER.membership_not_found",
			"CIRCLE.USER.membership_owner_cannot_leave",
			"CIRCLE.USER.membership_role_invalid",
			"CIRCLE.USER.membership_state_conflict",
			"CIRCLE.USER.membership_version_conflict",
			"CIRCLE.USER.not_member",
		},
		"circle_post_placement": {
			"CIRCLE.SYSTEM.placement_storage_write_failed",
			"CIRCLE.USER.placement_already_exists",
			"CIRCLE.USER.placement_idempotency_conflict",
			"CIRCLE.USER.placement_not_found",
			"CIRCLE.USER.placement_version_conflict",
		},
	}

	serviceRoot := circleErrorsServiceRoot(t)
	actualOwner := make(map[string]string, 52)
	actualCount := 0
	for objectName, expectedCodes := range expected {
		path := filepath.Join(serviceRoot, "contracts", "circle_management", objectName, "errors.yaml")
		actualCodes := circleErrorCodes(t, path)
		sort.Strings(expectedCodes)
		sort.Strings(actualCodes)
		if strings.Join(actualCodes, "\n") != strings.Join(expectedCodes, "\n") {
			t.Fatalf("%s errors.yaml ownership mismatch\nactual:   %v\nexpected: %v", objectName, actualCodes, expectedCodes)
		}
		for _, code := range actualCodes {
			if previous, exists := actualOwner[code]; exists {
				t.Fatalf("error %s has duplicate owners %s and %s", code, previous, objectName)
			}
			actualOwner[code] = objectName
			actualCount++
		}
	}
	expectedCount := 0
	for _, expectedCodes := range expected {
		expectedCount += len(expectedCodes)
	}
	if actualCount != expectedCount {
		t.Fatalf(
			"Circle error inventory changed: got %d codes, want %d",
			actualCount,
			expectedCount,
		)
	}
}

func circleErrorCodes(t *testing.T, path string) []string {
	t.Helper()

	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer file.Close()

	var codes []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "- code: ") {
			codes = append(codes, strings.TrimPrefix(line, "- code: "))
		}
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("scan %s: %v", path, err)
	}
	return codes
}

func circleErrorsServiceRoot(t *testing.T) string {
	t.Helper()

	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve Circle error contract test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "../../../.."))
}
