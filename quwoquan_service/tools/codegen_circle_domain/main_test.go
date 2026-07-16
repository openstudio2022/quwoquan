package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func TestCircleModelCodegen_PreservesObjectBoundaries(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	if _, err := os.Stat(metadataDir); err != nil {
		t.Fatalf("metadata dir is required: %v", err)
	}
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile ContractGraph: %v", err)
	}
	out := t.TempDir()
	generator := contractcodegen.NewDomainGenerator(
		source,
		out,
		contractcodegen.WithTypedEnums(),
		contractcodegen.WithSliceEntityRefs(),
		contractcodegen.WithSkipViewEntities(),
		contractcodegen.WithGoFieldIDSuffix(),
		contractcodegen.WithBusinessObjectEntitiesOnly(),
	)
	objects := map[string][]string{
		"Circle":              {"type Circle struct", "SubCategory", "Kind", "DisplaySubjectType", "FollowEnabled", "DefaultPublicGroupID", "LinkedHomepageID", "type CircleJoinPolicy", "CircleJoinPolicyInviteOnly", "[]CircleSectionConfig"},
		"CircleFile":          {"type CircleFile struct", "type CircleFileStatus", "type CircleFileType"},
		"CircleGroup":         {"type CircleGroup struct", "type CircleGroupStatus", "type OrganizationNodeType"},
		"CircleMembership":    {"type CircleMembership struct", "type CircleMemberRole", "type CircleMembershipState"},
		"CirclePostPlacement": {"type CirclePostPlacement struct", "OwnerPersonaID", "PinnedAt"},
	}
	paths := map[string]string{
		"Circle":              filepath.Join("domain", "circle", "model", "circle.go"),
		"CircleFile":          filepath.Join("domain", "circle", "circle_file", "model", "circle_file.go"),
		"CircleGroup":         filepath.Join("domain", "circle", "circle_group", "model", "circle_group.go"),
		"CircleMembership":    filepath.Join("domain", "circle", "circle_membership", "model", "circle_membership.go"),
		"CirclePostPlacement": filepath.Join("domain", "circle", "circle_post_placement", "model", "circle_post_placement.go"),
	}
	for object, needles := range objects {
		if err := generator.GenerateDomainModel(object); err != nil {
			t.Fatalf("GenerateDomainModel(%s): %v", object, err)
		}
		b, err := os.ReadFile(filepath.Join(out, paths[object]))
		if err != nil {
			t.Fatalf("read %s model: %v", object, err)
		}
		s := string(b)
		for _, needle := range needles {
			if !strings.Contains(s, needle) {
				t.Errorf("generated %s model missing %q", object, needle)
			}
		}
		if object == "Circle" && strings.Contains(s, "type CircleGroup struct") {
			t.Fatal("Circle aggregate must not absorb CircleGroup")
		}
		if object == "CircleMembership" && strings.Contains(s, "type CircleMember struct") {
			t.Fatal("CircleMembership aggregate must not restore retired CircleMember type")
		}
		if strings.Contains(s, "CommandReceipt struct") || strings.Contains(s, "Request struct") ||
			strings.Contains(s, "Outbox struct") || strings.Contains(s, "ProjectionCheckpoint struct") ||
			strings.Contains(s, "Inbox struct") {
			t.Fatalf("generated %s domain model contains infrastructure or transport entity", object)
		}
	}
}
