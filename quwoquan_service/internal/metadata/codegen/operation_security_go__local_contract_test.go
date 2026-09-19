package codegen

import (
	"bytes"
	"fmt"
	"go/parser"
	"go/token"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/spec.md
func TestRenderOperationSecurityGoFilesChunksLargeInputWithinHardBounds(t *testing.T) {
	files, err := RenderOperationSecurityGoFiles(operationSecurityFixture(257), "digest")
	if err != nil {
		t.Fatal(err)
	}
	if len(files) < 3 {
		t.Fatalf("large input produced %d files, want main plus multiple chunks", len(files))
	}
	for _, file := range files {
		if got := bytes.Count(file.Source, []byte("\n")); got > OperationSecurityMaxGeneratedFileLines {
			t.Fatalf("%s has %d lines, hard limit %d", file.Suffix, got, OperationSecurityMaxGeneratedFileLines)
		}
		if got := len(file.Source); got > OperationSecurityMaxGeneratedFileBytes {
			t.Fatalf("%s has %d bytes, hard limit %d", file.Suffix, got, OperationSecurityMaxGeneratedFileBytes)
		}
		if _, err := parser.ParseFile(token.NewFileSet(), file.Suffix, file.Source, parser.AllErrors); err != nil {
			t.Fatalf("parse %s: %v", file.Suffix, err)
		}
	}
}

func TestRenderOperationSecurityGoFilesIsDeterministicAndPreservesDomainOrder(t *testing.T) {
	fixture := operationSecurityFixture(65)
	reverse := append([]ast.Operation(nil), fixture.Operations...)
	sort.Slice(reverse, func(i, j int) bool { return reverse[i].ID > reverse[j].ID })

	first, err := RenderOperationSecurityGoFiles(fixture, "digest")
	if err != nil {
		t.Fatal(err)
	}
	second, err := RenderOperationSecurityGoFiles(&graph.ContractGraph{Operations: reverse}, "digest")
	if err != nil {
		t.Fatal(err)
	}
	if fmt.Sprint(first) != fmt.Sprint(second) {
		t.Fatal("rendering depends on ContractGraph operation order")
	}

	joined := joinOperationSecuritySources(first)
	previous := -1
	for index := 0; index < 65; index += 2 {
		token := fmt.Sprintf(`CanonicalOperationID: "alpha.object.Operation%04d"`, index)
		current := strings.Index(joined, token)
		if current < 0 || current <= previous {
			t.Fatalf("alpha operation %d missing or unstable in generated order", index)
		}
		previous = current
	}
	for _, token := range []string{
		"func ForDomain(domain string) []auth.OperationSecurityDescriptor",
		"source = appendOperationSecurityChunk000(source, domain)",
		"return source",
		`case "alpha":`,
		`case "beta":`,
	} {
		if !strings.Contains(joined, token) {
			t.Fatalf("generated bundle misses %q", token)
		}
	}
}

func TestRenderOperationSecurityGoFilesForDomainSemanticsCompileAndRun(t *testing.T) {
	files, err := RenderOperationSecurityGoFiles(operationSecurityFixture(65), "digest")
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	moduleRoot := filepath.Join(root, "quwoquan_service")
	packageDir := filepath.Join(moduleRoot, "generated", "operationsecurity")
	authDir := filepath.Join(moduleRoot, "runtime", "auth")
	if err := os.MkdirAll(packageDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(authDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(moduleRoot, "go.mod"), []byte("module quwoquan_service\n\ngo 1.22\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	authSource := `package auth

type OperationSecurityDescriptor struct {
	CanonicalOperationID string
	ContractGraphSHA256 string
	Transport string
	Method string
	OperationKind string
	MutationTarget string
	InvariantTarget string
	PathTemplate string
	AuthMode string
	ActorRequirement string
	Principal string
	Scopes []string
	Permissions []string
	OwnershipPolicy string
	TimeoutMilliseconds int
	StreamBudget *OperationStreamBudget
	Idempotency string
	VersionPrecondition string
	CommercialStatus string
}
type OperationStreamBudget struct { HandshakeMilliseconds, IdleMilliseconds, MaxDurationMilliseconds int }
`
	if err := os.WriteFile(filepath.Join(authDir, "auth.go"), []byte(authSource), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, file := range files {
		name := "descriptors" + file.Suffix + ".g.go"
		if err := os.WriteFile(filepath.Join(packageDir, name), file.Source, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	testSource := `package operationsecurity
import "testing"
func TestGeneratedForDomain(t *testing.T) {
	alpha := ForDomain("alpha")
	if len(alpha) != 33 { t.Fatalf("alpha len = %d", len(alpha)) }
	for index, descriptor := range alpha {
		if index > 0 && alpha[index-1].CanonicalOperationID >= descriptor.CanonicalOperationID { t.Fatal("unstable order") }
	}
	alpha[0].CanonicalOperationID = "mutated"
	if ForDomain("alpha")[0].CanonicalOperationID == "mutated" { t.Fatal("ForDomain leaked mutable backing storage") }
	if got := ForDomain("missing"); got != nil { t.Fatalf("missing = %#v, want nil", got) }
}
`
	if err := os.WriteFile(filepath.Join(packageDir, "generated_test.go"), []byte(testSource), 0o644); err != nil {
		t.Fatal(err)
	}
	command := exec.Command("go", "test", "./generated/operationsecurity")
	command.Dir = moduleRoot
	command.Env = append(os.Environ(), "GOWORK=off", "GOCACHE="+filepath.Join(root, "go-cache"))
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("compiled generated bundle: %v\n%s", err, output)
	}
}

func TestRenderOperationSecurityGoFilesRejectsUnboundedInput(t *testing.T) {
	operationCount := OperationSecurityOperationsPerChunk*OperationSecurityMaxChunks + 1
	_, err := RenderOperationSecurityGoFiles(operationSecurityFixture(operationCount), "digest")
	if err == nil || !strings.Contains(err.Error(), "exceeds hard limit") {
		t.Fatalf("unbounded input error = %v", err)
	}
}

func operationSecurityFixture(count int) *graph.ContractGraph {
	operations := make([]ast.Operation, 0, count)
	for index := count - 1; index >= 0; index-- {
		domain := "alpha"
		if index%2 == 1 {
			domain = "beta"
		}
		operations = append(operations, ast.Operation{
			ID:               fmt.Sprintf("%s.object.Operation%04d", domain, index),
			Domain:           domain,
			Transport:        "http",
			Method:           "GET",
			Kind:             ast.OperationKind("query"),
			PathTemplate:     fmt.Sprintf("/%s/%d", domain, index),
			AuthMode:         "required",
			ActorRequirement: "persona",
			Principal:        "persona",
			Scopes:           []string{"read"},
			Permissions:      []string{"object.read"},
			OwnershipPolicy:  "owner",
			Commercial:       ast.CommercialBinding{Status: "ready"},
		})
	}
	return &graph.ContractGraph{Operations: operations}
}

func joinOperationSecuritySources(files []OperationSecurityGoFile) string {
	var output strings.Builder
	for _, file := range files {
		output.Write(file.Source)
	}
	return output.String()
}
