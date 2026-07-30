package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestCircleModelCodegen_PreservesObjectBoundaries(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if _, err := os.Stat(metadataDir); err != nil {
		t.Fatalf("metadata dir is required: %v", err)
	}
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile ContractGraph: %v", err)
	}
	out := t.TempDir()
	objects := map[string][]string{
		"Circle":              {"type Circle struct", "SubCategory", "Kind", "DisplaySubjectType", "FollowEnabled", "DefaultPublicGroupID", "LinkedHomepageID", "type CircleJoinPolicy", "CircleJoinPolicyInviteOnly", "[]CircleSectionConfig"},
		"CircleFile":          {"type CircleFile struct", "type CircleFileStatus", "type CircleFileType"},
		"CircleGroup":         {"type CircleGroup struct", "type CircleGroupStatus", "type OrganizationNodeType"},
		"CircleMembership":    {"type CircleMembership struct", "type CircleMemberRole", "type CircleMembershipState"},
		"CirclePostPlacement": {"type CirclePostPlacement struct", "OwnerPersonaID", "PinnedAt"},
	}
	paths := map[string]string{
		"Circle":              filepath.Join("circle", "contract", "model", "circle.go"),
		"CircleFile":          filepath.Join("circle_file", "contract", "model", "circle_file.go"),
		"CircleGroup":         filepath.Join("circle_group", "contract", "model", "circle_group.go"),
		"CircleMembership":    filepath.Join("circle_membership", "contract", "model", "circle_membership.go"),
		"CirclePostPlacement": filepath.Join("circle_post_placement", "contract", "model", "circle_post_placement.go"),
	}
	for object, needles := range objects {
		generator := contractcodegen.NewDomainGenerator(
			source,
			filepath.Join(out, contractcodegen.CamelToSnake(object)),
			contractcodegen.WithTypedEnums(),
			contractcodegen.WithSliceEntityRefs(),
			contractcodegen.WithSkipViewEntities(),
			contractcodegen.WithGoFieldIDSuffix(),
			contractcodegen.WithBusinessObjectEntitiesOnly(),
			contractcodegen.WithObjectFirstRoot(),
		)
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

func TestCircleObjectErrorPathsRequireObjectOwnership(t *testing.T) {
	t.Parallel()

	paths, err := circleObjectErrorPaths([]string{
		"circle/circle_management/circle_membership/errors.yaml",
		"circle/circle_management/circle/errors.yaml",
		"circle/circle_management/circle_group/errors.yaml",
	})
	if err != nil {
		t.Fatalf("circleObjectErrorPaths() error = %v", err)
	}
	want := []string{
		"circle/circle_management/circle/errors.yaml",
		"circle/circle_management/circle_group/errors.yaml",
		"circle/circle_management/circle_membership/errors.yaml",
	}
	if strings.Join(paths, "|") != strings.Join(want, "|") {
		t.Fatalf("circleObjectErrorPaths() = %v, want %v", paths, want)
	}

	invalid := [][]string{
		nil,
		{"circle/circle_management/errors.yaml"},
		{"circle/other/circle/errors.yaml"},
		{"circle/circle_management/circle/internal/errors.yaml"},
	}
	for _, input := range invalid {
		if _, err := circleObjectErrorPaths(input); err == nil {
			t.Fatalf("circleObjectErrorPaths(%v) unexpectedly succeeded", input)
		}
	}
}

func TestCircleErrorsCodegen_PreservesObjectBoundaries(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile ContractGraph: %v", err)
	}
	out := t.TempDir()
	count, err := generateErrors(source, out, false)
	if err != nil {
		t.Fatalf("generateErrors() error = %v", err)
	}
	errorPaths, err := circleObjectErrorPaths(
		source.Paths("circle/circle_management/", "/errors.yaml"),
	)
	if err != nil {
		t.Fatalf("discover Circle error paths: %v", err)
	}
	if count != len(errorPaths) {
		t.Fatalf("generateErrors() count = %d, want %d", count, len(errorPaths))
	}
	for _, sourcePath := range errorPaths {
		parts := strings.Split(sourcePath, "/")
		object := parts[2]
		generated, err := os.ReadFile(filepath.Join(out, object, "errors.go"))
		if err != nil {
			t.Fatalf("read generated %s errors: %v", object, err)
		}
		if !strings.Contains(string(generated), "from "+sourcePath+". DO NOT EDIT.") {
			t.Errorf("generated %s errors lost canonical source %s", object, sourcePath)
		}
	}
	if generated, err := os.ReadFile(filepath.Join(out, "circle", "errors.go")); err != nil {
		t.Fatalf("read generated circle errors: %v", err)
	} else if strings.Contains(string(generated), "ErrGroupNotFound") {
		t.Fatal("Circle errors must not absorb CircleGroup-specific errors")
	}
	if generated, err := os.ReadFile(filepath.Join(out, "circle_group", "errors.go")); err != nil {
		t.Fatalf("read generated CircleGroup errors: %v", err)
	} else if !strings.Contains(string(generated), "ErrGroupNotFound") {
		t.Fatal("CircleGroup errors must remain owned by CircleGroup")
	}
	if _, err := generateErrors(source, out, true); err != nil {
		t.Fatalf("generated Circle errors should be current: %v", err)
	}
	stalePath := filepath.Join(out, "circle_group", "errors.go")
	if err := os.WriteFile(stalePath, []byte("package generated\n"), 0o644); err != nil {
		t.Fatalf("write stale CircleGroup errors: %v", err)
	}
	if _, err := generateErrors(source, out, true); err == nil ||
		!strings.Contains(err.Error(), "generated errors are stale") {
		t.Fatalf("stale generated CircleGroup errors were not rejected: %v", err)
	}
}
