package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestCircleProductionCompositionUsesCanonicalHostAuthorityOwners(t *testing.T) {
	root := gatheringCircleServiceRoot(t)
	mainSource := readGatheringCompositionFile(
		t,
		filepath.Join(root, "cmd", "api", "main.go"),
	)
	for _, required := range []string{
		"application.NewHostAuthorityEvaluator(",
		"gatheringexternal.NewPersonaHostAuthorityHTTPClient(",
		"gatheringexternal.NewEntityHomepageHostAuthorityHTTPClient(",
		"gatheringexternal.NewLocalCircleHostAuthorityClient(",
		`"user.persona.gathering_host_authority.evaluate"`,
		`"entity.homepage.gathering_host_authority.evaluate"`,
		"gatheringexternal.NewHostAuthorityReader(",
		"WithHostAuthorityEvaluator(circleHostAuthorityEvaluator)",
	} {
		if !strings.Contains(mainSource, required) {
			t.Fatalf("production Host authority composition missing %q", required)
		}
	}
	allComposition := mainSource + readGatheringCompositionFile(
		t,
		filepath.Join(root, "cmd", "api", "gathering_composition.go"),
	)
	for _, forbidden := range []string{
		"gatheringHostAuthorityUnavailable",
		"Host authority endpoint is unavailable",
	} {
		if strings.Contains(allComposition, forbidden) {
			t.Fatalf("production Host authority composition retains %q", forbidden)
		}
	}
}

func TestGatheringOwnerClientsUseOnlyPublicGeneratedDTOs(t *testing.T) {
	root := gatheringCircleServiceRoot(t)
	source := readGatheringCompositionFile(
		t,
		filepath.Join(
			root,
			"internal",
			"circle_management",
			"gathering",
			"infrastructure",
			"external",
			"host_authority_clients.go",
		),
	)
	if !strings.Contains(
		source,
		`"quwoquan_service/generated/serviceclients/hostauthority"`,
	) {
		t.Fatal("Gathering owner clients must consume the public generated serviceclient")
	}
	for _, forbidden := range []string{
		"services/user-service/internal/",
		"services/user-service/generated/",
		"services/entity-service/internal/",
		"services/entity-service/generated/",
	} {
		if strings.Contains(source, forbidden) {
			t.Fatalf("Gathering owner client crosses service boundary through %q", forbidden)
		}
	}
}

func gatheringCircleServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(file, "..", "..", "..", "..", ".."))
}

func readGatheringCompositionFile(t *testing.T, path string) string {
	t.Helper()
	value, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(value)
}
