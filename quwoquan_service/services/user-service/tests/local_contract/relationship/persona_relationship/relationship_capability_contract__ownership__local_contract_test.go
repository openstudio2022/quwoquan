package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestRelationshipCapabilityContractHasSinglePersonaRelationshipOwner(t *testing.T) {
	t.Parallel()

	serviceRoot := userServiceRoot(t)
	canonicalPath := filepath.Join(
		serviceRoot,
		"contracts", "relationship", "persona_relationship", "fields.yaml",
	)
	canonical := readContract(t, canonicalPath)
	for _, want := range []string{
		"RelationshipCapabilityView:",
		"description: 主页按钮矩阵与聊天/通话门禁统一消费的关系能力视图",
		"name: canCreateDirectConversation",
	} {
		if !strings.Contains(canonical, want) {
			t.Fatalf("canonical RelationshipCapability contract missing %q", want)
		}
	}

	for _, duplicate := range []string{
		"relationship_capability_wire.yaml",
		"social_relationship_capability_wire.yaml",
	} {
		path := filepath.Join(
			serviceRoot,
			"contracts", "account", "user_account", "projections", duplicate,
		)
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("relationship capability duplicate must not exist at %s: %v", path, err)
		}
	}

	userAccountFields := readContract(t, filepath.Join(
		serviceRoot,
		"contracts", "account", "user_account", "fields.yaml",
	))
	if strings.Contains(userAccountFields, "SocialRelationshipCapabilityView") {
		t.Fatal("user_account retains the six-field relationship capability subset")
	}
	if !strings.Contains(userAccountFields, "object_ref: RelationshipCapabilityView") {
		t.Fatal("social relation search item does not reference the canonical relationship capability view")
	}

	if err := filepath.Walk(filepath.Join(serviceRoot, "contracts"), func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".yaml") {
			return err
		}
		raw, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		if strings.Contains(string(raw), "RelationshipCapabilityWire") {
			t.Fatalf("retired relationship capability wire remains in %s", path)
		}
		return nil
	}); err != nil {
		t.Fatalf("scan relationship capability owners: %v", err)
	}
}

func TestFollowingSubjectProjectionSubscribesToProducedVisitEvent(t *testing.T) {
	t.Parallel()

	serviceRoot := userServiceRoot(t)
	consumer := readContract(t, filepath.Join(
		serviceRoot,
		"contracts", "profile_projection", "following_subject", "events.yaml",
	))
	producer := readContract(t, filepath.Join(
		serviceRoot,
		"contracts", "relationship", "followed_subject_visit_state", "events.yaml",
	))
	if !strings.Contains(producer, "name: FollowedSubjectVisited") {
		t.Fatal("FollowedSubjectVisited producer contract is missing")
	}
	if !strings.Contains(consumer, "- FollowedSubjectVisited") {
		t.Fatal("following-subject projection does not subscribe to FollowedSubjectVisited")
	}
	if strings.Contains(consumer, "FollowingSubjectVisited") {
		t.Fatal("following-subject projection retains the non-produced FollowingSubjectVisited alias")
	}
}

func userServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func readContract(t *testing.T, path string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(raw)
}
