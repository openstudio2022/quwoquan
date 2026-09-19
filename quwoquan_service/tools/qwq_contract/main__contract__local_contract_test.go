package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

func TestGenerateAndCheckAreIdempotent(t *testing.T) {
	metadataDir := t.TempDir()
	repoRoot := t.TempDir()
	writeOpenAPICLIFixture(t, metadataDir)
	if err := run([]string{
		"generate-openapi",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
	}, &bytes.Buffer{}); err != nil {
		t.Fatalf("generate OpenAPI fixture: %v", err)
	}
	output := filepath.Join(t.TempDir(), "contract_graph.json")
	generatedRoot := t.TempDir()
	securityOutput := filepath.Join(
		generatedRoot,
		"operationsecurity",
		"descriptors.g.go",
	)
	manifestOutput := filepath.Join(generatedRoot, "contract_graph_manifest.json")

	args := []string{
		"generate",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
		"--profile", "baseline",
		"--output", output,
		"--go-security-output", securityOutput,
		"--generated-manifest", manifestOutput,
	}
	if err := run(args, &bytes.Buffer{}); err != nil {
		t.Fatalf("first generate: %v", err)
	}
	first, err := os.ReadFile(output)
	if err != nil {
		t.Fatalf("read first graph: %v", err)
	}

	if err := run(args, &bytes.Buffer{}); err != nil {
		t.Fatalf("second generate: %v", err)
	}
	second, err := os.ReadFile(output)
	if err != nil {
		t.Fatalf("read second graph: %v", err)
	}
	if !bytes.Equal(first, second) {
		t.Fatal("generate produced a diff without metadata changes")
	}
	securityFiles, err := filepath.Glob(strings.TrimSuffix(securityOutput, ".g.go") + "*.g.go")
	if err != nil {
		t.Fatalf("glob generated operation security: %v", err)
	}
	if len(securityFiles) < 2 {
		t.Fatalf("operation security bundle files = %v, want main and chunks", securityFiles)
	}
	securityBodies := map[string][]byte{}
	var securitySource []byte
	for _, path := range securityFiles {
		body, readErr := os.ReadFile(path)
		if readErr != nil {
			t.Fatalf("read generated operation security %s: %v", path, readErr)
		}
		securityBodies[filepath.ToSlash(path)] = body
		securitySource = append(securitySource, body...)
	}
	for _, token := range []string{
		"ContractGraphSHA256",
		`CanonicalOperationID: "content.post.GetPost"`,
		"ContractGraphSHA256:",
		"Transport:",
		"CommercialStatus:",
		`"blocked"`,
	} {
		if !bytes.Contains(securitySource, []byte(token)) {
			t.Fatalf("generated operation security misses %q", token)
		}
	}

	manifestBytes, err := os.ReadFile(manifestOutput)
	if err != nil {
		t.Fatalf("read generated provenance manifest: %v", err)
	}
	var manifest generatedManifestDocument
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		t.Fatalf("decode generated provenance manifest: %v", err)
	}
	if manifest.Generator != "tools/qwq_contract" || len(manifest.Outputs) != 1+len(securityFiles) {
		t.Fatalf("unexpected generated provenance manifest: %+v", manifest)
	}
	wantBodies := map[string][]byte{filepath.ToSlash(output): first}
	for path, body := range securityBodies {
		wantBodies[path] = body
	}
	for _, current := range manifest.Outputs {
		body, ok := wantBodies[current.Path]
		if !ok {
			t.Fatalf("manifest registered unexpected output %q", current.Path)
		}
		wantDigest := fmt.Sprintf("%x", sha256.Sum256(body))
		if current.SHA256 != wantDigest || current.Bytes != len(body) {
			t.Fatalf("manifest output %q does not bind exact bytes: %+v", current.Path, current)
		}
	}

	var stdout bytes.Buffer
	if err := run([]string{
		"check",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
		"--profile", "baseline",
		"--input", output,
	}, &stdout); err != nil {
		t.Fatalf("check generated graph: %v", err)
	}
	if !bytes.Contains(stdout.Bytes(), []byte("ContractGraph is current")) {
		t.Fatalf("unexpected check output: %s", stdout.String())
	}
}

func TestGenerateOpenAPIAndCheckOpenAPIUseTemporaryMetadata(t *testing.T) {
	metadataDir := t.TempDir()
	repoRoot := t.TempDir()
	writeOpenAPICLIFixture(t, metadataDir)

	var generateOutput bytes.Buffer
	if err := run([]string{
		"generate-openapi",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
	}, &generateOutput); err != nil {
		t.Fatalf("generate-openapi: %v", err)
	}
	if !strings.Contains(
		generateOutput.String(),
		"covering 2 operation(s)",
	) {
		t.Fatalf("unexpected generate-openapi output: %s", generateOutput.String())
	}
	snapshotPath := filepath.Join(metadataDir, "content", "openapi.yaml")
	first, err := os.ReadFile(snapshotPath)
	if err != nil {
		t.Fatalf("read generated OpenAPI: %v", err)
	}
	if !bytes.Contains(first, []byte("operationId: GetPost")) ||
		!bytes.Contains(first, []byte("operationId: PublishPost")) {
		t.Fatalf("generated OpenAPI misses fixture operations:\n%s", first)
	}

	if err := run([]string{
		"generate-openapi",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
	}, &bytes.Buffer{}); err != nil {
		t.Fatalf("second generate-openapi: %v", err)
	}
	second, err := os.ReadFile(snapshotPath)
	if err != nil {
		t.Fatalf("read second OpenAPI: %v", err)
	}
	if !bytes.Equal(first, second) {
		t.Fatal("generate-openapi produced non-deterministic output")
	}

	var checkOutput bytes.Buffer
	if err := run([]string{
		"check-openapi",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
	}, &checkOutput); err != nil {
		t.Fatalf("check-openapi current snapshot: %v", err)
	}
	if !strings.Contains(checkOutput.String(), "OpenAPI snapshots are current") {
		t.Fatalf("unexpected check-openapi output: %s", checkOutput.String())
	}

	if err := os.WriteFile(
		snapshotPath,
		append(second, []byte("# manual drift\n")...),
		0o644,
	); err != nil {
		t.Fatalf("make OpenAPI stale: %v", err)
	}
	err = run([]string{
		"check-openapi",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
	}, &bytes.Buffer{})
	if err == nil || !strings.Contains(err.Error(), "stale: content/openapi.yaml") {
		t.Fatalf("check-openapi must reject stale artifact, got %v", err)
	}
}

// 缺 --repo-root 必须 fail-closed：metadata-dir 是只含 YAML 的一次性契约视图，读不到
// internal/**、tests/** 与端侧目录。静默接受空 repo-root 会让全仓 readinessEvidence 恒为
// 0 条、readiness 恒停在 contract-ready，看上去只是「运行证据还没接入」。
func TestLoadBearingSubcommandsRejectMissingRepoRoot(t *testing.T) {
	metadataDir := t.TempDir()
	writeOpenAPICLIFixture(t, metadataDir)

	for _, subcommand := range []string{
		"validate",
		"generate",
		"check",
		"generate-openapi",
		"check-openapi",
		"coverage",
	} {
		t.Run(subcommand, func(t *testing.T) {
			args := []string{
				subcommand,
				"--metadata-dir", metadataDir,
				"--profile", "baseline",
			}
			switch subcommand {
			case "generate-openapi", "check-openapi", "coverage":
				args = args[:len(args)-2]
			case "check":
				args = append(args, "--input", filepath.Join(t.TempDir(), "graph.json"))
			}
			err := run(args, &bytes.Buffer{})
			if err == nil {
				t.Fatal("missing --repo-root must fail, got success")
			}
			if !strings.Contains(err.Error(), "--repo-root is required") {
				t.Fatalf("error must name the missing repo root, got %v", err)
			}
		})
	}
}

func TestRepoRootMustBeADirectory(t *testing.T) {
	metadataDir := t.TempDir()
	writeOpenAPICLIFixture(t, metadataDir)
	notADirectory := filepath.Join(t.TempDir(), "repo-root")
	if err := os.WriteFile(notADirectory, []byte("x"), 0o644); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	err := run([]string{
		"coverage",
		"--metadata-dir", metadataDir,
		"--repo-root", notADirectory,
	}, &bytes.Buffer{})
	if err == nil || !strings.Contains(err.Error(), "is not a directory") {
		t.Fatalf("repo root must be a directory, got %v", err)
	}
}

func writeOpenAPICLIFixture(t *testing.T, metadataDir string) {
	t.Helper()
	schemaSource := filepath.Join(
		"..",
		"..",
		"contracts",
		"metadata",
		"_schemas",
		"contract_graph.schema.json",
	)
	schema, err := os.ReadFile(schemaSource)
	if err != nil {
		t.Fatalf("read ContractGraph schema: %v", err)
	}
	writeFixtureFile(
		t,
		filepath.Join(
			metadataDir,
			"_schemas",
			"contract_graph.schema.json",
		),
		string(schema),
	)
	writeFixtureFile(
		t,
		filepath.Join(metadataDir, "content", "content", "context.yaml"),
		`
role: core
access:
  commands: aggregate_facade_only
  queries: named_reader_slice_only
  child_objects: aggregate_root_only
  cross_context: public_contract_only
`,
	)
	writeFixtureFile(
		t,
		filepath.Join(metadataDir, "content", "content", "post", "object.yaml"),
		`
kind: aggregate_root
description: CLI fixture
identity:
  fields: [id]
  version_source: immutable
access:
  commands: aggregate_facade
  queries: named_reader
  cross_context: public_contract_only
relationships: []
`,
	)
	writeFixtureFile(
		t,
		filepath.Join(metadataDir, "content", "content", "post", "fields.yaml"),
		`
description: CLI fixture fields
fields:
  - name: id
    type: string
    constraints: [PK, NOT_NULL]
    classification: PUBLIC
    log_policy: allow
    api_exposure: read
    ops_exposure: read
    role: authoritative_state
types:
  PostView:
    fields:
      - name: id
        type: string
  PublishPostRequest:
    fields:
      - name: id
        type: string
  PublishPostResult:
    fields:
      - name: id
        type: string
`,
	)
	writeFixtureFile(
		t,
		filepath.Join(metadataDir, "content", "content", "post", "storage.yaml"),
		`
backend: mongodb
collections:
  posts:
    entity: Post
`,
	)
	writeFixtureFile(
		t,
		filepath.Join(metadataDir, "content", "content", "post", "operations.yaml"),
		`
api_routes:
  - method: GET
    path: /content/posts/{postId}
    operation: GetPost
    actor: persona_or_device
    response_entity: PostView
    application:
      kind: query
      facet: PostQueryFacade
      method: getPost
      reader: PostReader
      slice: PostSlice
  - method: POST
    path: /content/posts/{postId}:publish
    operation: PublishPost
    actor: persona
    request_entity: PublishPostRequest
    response_entity: PublishPostResult
    application:
      kind: command
      facet: PostCommandFacade
      method: publishPost
      aggregate_owner: Post
`,
	)
	writeFixtureFile(
		t,
		filepath.Join(
			metadataDir,
			"content",
			"post",
			"projections",
			"post_view.yaml",
		),
		`
read_model: PostSlice
client_projection:
  dart_class: PostView
`,
	)
}

func writeFixtureFile(t *testing.T, path string, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir fixture: %v", err)
	}
	if err := os.WriteFile(
		path,
		[]byte(strings.TrimSpace(content)+"\n"),
		0o644,
	); err != nil {
		t.Fatalf("write fixture %s: %v", path, err)
	}
}

func TestWriteOperationSecurityBundleRemovesOnlyOwnedStaleChunks(t *testing.T) {
	root := t.TempDir()
	mainPath := filepath.Join(root, "descriptors.g.go")
	large, err := contractcodegen.RenderOperationSecurityGoFiles(operationSecurityCLIFixture(40), "digest")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := writeOperationSecurityBundle(mainPath, large); err != nil {
		t.Fatalf("write large bundle: %v", err)
	}
	stalePath := strings.TrimSuffix(mainPath, ".g.go") + ".chunk002.g.go"
	if _, err := os.Stat(stalePath); err != nil {
		t.Fatalf("expected third chunk: %v", err)
	}

	small, err := contractcodegen.RenderOperationSecurityGoFiles(operationSecurityCLIFixture(5), "digest")
	if err != nil {
		t.Fatal(err)
	}
	written, err := writeOperationSecurityBundle(mainPath, small)
	if err != nil {
		t.Fatalf("write small bundle: %v", err)
	}
	if len(written) != 2 {
		t.Fatalf("small closed output set = %d files, want 2", len(written))
	}
	if _, err := os.Stat(stalePath); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("owned stale chunk was not removed: %v", err)
	}

	foreignPath := strings.TrimSuffix(mainPath, ".g.go") + ".chunk099.g.go"
	if err := os.WriteFile(foreignPath, []byte("package foreign\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := writeOperationSecurityBundle(mainPath, small); err == nil || !strings.Contains(err.Error(), "not owned") {
		t.Fatalf("foreign stale chunk must fail closed, got %v", err)
	}
	if _, err := os.Stat(foreignPath); err != nil {
		t.Fatalf("foreign file was removed: %v", err)
	}
}

func operationSecurityCLIFixture(count int) *graph.ContractGraph {
	operations := make([]ast.Operation, 0, count)
	for index := 0; index < count; index++ {
		operations = append(operations, ast.Operation{
			ID:     fmt.Sprintf("content.post.Operation%04d", index),
			Domain: "content", Transport: "http", Method: "GET",
			Kind: ast.OperationKind("query"), PathTemplate: fmt.Sprintf("/posts/%d", index),
			AuthMode: "required", Commercial: ast.CommercialBinding{Status: "ready"},
		})
	}
	return &graph.ContractGraph{Operations: operations}
}
