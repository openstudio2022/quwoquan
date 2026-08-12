package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
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
	securityOutput := filepath.Join(
		t.TempDir(),
		"operationsecurity",
		"descriptors.g.go",
	)

	args := []string{
		"generate",
		"--metadata-dir", metadataDir,
		"--repo-root", repoRoot,
		"--profile", "baseline",
		"--output", output,
		"--go-security-output", securityOutput,
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
	securitySource, err := os.ReadFile(securityOutput)
	if err != nil {
		t.Fatalf("read generated operation security: %v", err)
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
