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
	writeOpenAPICLIFixture(t, metadataDir)
	if err := run([]string{
		"generate-openapi",
		"--metadata-dir", metadataDir,
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
	writeOpenAPICLIFixture(t, metadataDir)

	var generateOutput bytes.Buffer
	if err := run([]string{
		"generate-openapi",
		"--metadata-dir", metadataDir,
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
	}, &bytes.Buffer{})
	if err == nil || !strings.Contains(err.Error(), "stale: content/openapi.yaml") {
		t.Fatalf("check-openapi must reject stale artifact, got %v", err)
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
		filepath.Join(metadataDir, "content", "post", "aggregate.yaml"),
		`
version: 1
domain: content
aggregate_root: Post
object_kind: aggregate_root
description: CLI fixture
storage_backend: mongodb
members: []
`,
	)
	writeFixtureFile(
		t,
		filepath.Join(metadataDir, "content", "post", "service.yaml"),
		`
version: 1
service:
  name: content-service
  domain: content
api_routes:
  - method: GET
    path: /v1/content/posts/{postId}
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
    path: /v1/content/posts/{postId}:publish
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
version: 1
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
