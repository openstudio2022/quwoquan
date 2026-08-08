package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestCrossLanguageEventConstantsKeepObjectLocalGoOwners(t *testing.T) {
	t.Parallel()

	serviceRoot := t.TempDir()
	writeDomainOwner(t, serviceRoot, "foo-service", "foo")
	writeDomainOwner(t, serviceRoot, "user-service", "user")
	writeDomainOwner(t, serviceRoot, "content-service", "content")
	contractGraph := eventConstantsFixtureGraph()
	plan, err := buildGenerationPlan(
		contractGraph,
		serviceRoot,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.GoOutputs) != 3 {
		t.Fatalf("Go outputs = %d, want 3", len(plan.GoOutputs))
	}
	if len(plan.PythonEvents) != 3 {
		t.Fatalf("Python events = %d, want 3", len(plan.PythonEvents))
	}
	if len(plan.ExcludedObjects) != 0 {
		t.Fatalf("excluded objects = %#v", plan.ExcludedObjects)
	}

	source := contractcodegen.NewSourceFromGraph("metadata", contractGraph)
	if err := writeGeneration(
		source,
		plan,
		serviceRoot,
		"services/recommendation-service/generated/event_constants.py",
		"generated/event_constants_manifest.json",
	); err != nil {
		t.Fatal(err)
	}

	domainGo := readTestFile(t, filepath.Join(
		serviceRoot,
		"services/foo-service/generated/catalog/item/contract/event/events.go",
	))
	if !strings.Contains(domainGo, `ItemCreated = "foo.item.created"`) ||
		!strings.Contains(domainGo, "ClientRealtimeWireTypes") {
		t.Fatalf("domain-owner Go output:\n%s", domainGo)
	}
	storageGo := readTestFile(t, filepath.Join(
		serviceRoot,
		"services/user-service/generated/account/user_account/contract/user/event/events.g.go",
	))
	if !strings.Contains(storageGo, `UserClosed = "UserClosed"`) ||
		strings.Contains(storageGo, "ClientRealtimeWireTypes") {
		t.Fatalf("storage-owner Go output:\n%s", storageGo)
	}
	python := readTestFile(t, filepath.Join(
		serviceRoot,
		"services/recommendation-service/generated/event_constants.py",
	))
	for _, expected := range []string{
		`FOO_ITEM_ITEM_CREATED = "foo.item.created"`,
		`USER_USER_ACCOUNT_USER_CLOSED = "UserClosed"`,
		`"foo.item.ItemCreated": FOO_ITEM_ITEM_CREATED`,
	} {
		if !strings.Contains(python, expected) {
			t.Fatalf("Python output missing %q:\n%s", expected, python)
		}
	}

	var manifest ownershipManifest
	manifestRaw := readTestFile(t, filepath.Join(
		serviceRoot,
		"generated/event_constants_manifest.json",
	))
	if err := json.Unmarshal([]byte(manifestRaw), &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.Generator != generatorIdentity || len(manifest.Outputs) != 4 {
		t.Fatalf("manifest = %#v", manifest)
	}
	if manifest.SchemaVersion != manifestVersion ||
		manifest.SourceDigest != plan.SourceDigest ||
		len(manifest.ExcludedObjects) != 0 {
		t.Fatalf("manifest provenance = %#v", manifest)
	}
	owners := map[string]string{}
	for _, output := range manifest.Outputs {
		owners[output.Path] = output.Owner
		content, err := os.ReadFile(filepath.Join(serviceRoot, output.Path))
		if err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(content)
		if got := hex.EncodeToString(digest[:]); got != output.SHA256 {
			t.Fatalf("%s digest = %s, manifest = %s", output.Path, got, output.SHA256)
		}
		if len(content) != output.Bytes {
			t.Fatalf("%s bytes = %d, manifest = %d", output.Path, len(content), output.Bytes)
		}
	}
	if got := owners["services/foo-service/generated/catalog/item/contract/event/events.go"]; got != "foo.item" {
		t.Fatalf("domain Go owner = %q", got)
	}
	if got := owners["services/user-service/generated/account/user_account/contract/user/event/events.g.go"]; got != "user.user_account" {
		t.Fatalf("storage Go owner = %q", got)
	}
}

func TestEventConstantsDryRunRosterIsCompleteAndReadOnly(t *testing.T) {
	t.Parallel()

	serviceRoot := t.TempDir()
	writeDomainOwner(t, serviceRoot, "foo-service", "foo")
	writeDomainOwner(t, serviceRoot, "user-service", "user")
	writeDomainOwner(t, serviceRoot, "content-service", "content")
	contractGraph := eventConstantsFixtureGraph()
	contractGraph.Governance.Objects[2].Events[0].WireEventType = ""

	plan, err := buildGenerationPlan(
		contractGraph,
		serviceRoot,
		[]string{"content.media_asset"},
	)
	if err != nil {
		t.Fatal(err)
	}
	rendered, err := renderGenerationPlan(
		plan,
		serviceRoot,
		"services/recommendation-service/generated/event_constants.py",
		"generated/event_constants_manifest.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Generator       string           `json:"generator"`
		SourceDigest    string           `json:"sourceDigest"`
		GoObjects       int              `json:"goObjects"`
		PythonEvents    int              `json:"pythonEvents"`
		ExcludedObjects []excludedObject `json:"excludedObjects"`
		Manifest        string           `json:"manifest"`
		Outputs         []struct {
			Path    string `json:"path"`
			Owner   string `json:"owner"`
			Emitter string `json:"emitter"`
		} `json:"outputs"`
	}
	if err := json.Unmarshal(rendered, &document); err != nil {
		t.Fatal(err)
	}
	if document.Generator != generatorIdentity ||
		document.SourceDigest != plan.SourceDigest ||
		document.GoObjects != 2 || document.PythonEvents != 2 ||
		document.Manifest != "generated/event_constants_manifest.json" {
		t.Fatalf("dry-run plan = %#v", document)
	}
	if !reflect.DeepEqual(document.ExcludedObjects, []excludedObject{{
		ObjectID:  "content.media_asset",
		EventRefs: []string{"content.media_asset.MediaAssetCreated"},
	}}) {
		t.Fatalf("excluded objects = %#v", document.ExcludedObjects)
	}
	wantOutputs := map[string]string{
		"services/foo-service/generated/catalog/item/contract/event/events.go":                 "foo.item",
		"services/user-service/generated/account/user_account/contract/user/event/events.g.go": "user.user_account",
		"services/recommendation-service/generated/event_constants.py":                         "cross-service.event-wire-identity",
	}
	if len(document.Outputs) != len(wantOutputs) {
		t.Fatalf("outputs = %#v", document.Outputs)
	}
	for _, output := range document.Outputs {
		if wantOutputs[output.Path] != output.Owner || output.Emitter == "" {
			t.Fatalf("unexpected dry-run output = %#v", output)
		}
	}
	for _, relative := range append(
		[]string{document.Manifest},
		mapKeys(wantOutputs)...,
	) {
		if _, statErr := os.Stat(filepath.Join(serviceRoot, relative)); !os.IsNotExist(statErr) {
			t.Fatalf("dry-run wrote %s: %v", relative, statErr)
		}
	}
}

func TestEventConstantsRetirementRequiresManifestBoundBytes(t *testing.T) {
	t.Parallel()

	serviceRoot := t.TempDir()
	writeDomainOwner(t, serviceRoot, "foo-service", "foo")
	writeDomainOwner(t, serviceRoot, "user-service", "user")
	writeDomainOwner(t, serviceRoot, "content-service", "content")
	fullGraph := eventConstantsFixtureGraph()
	fullPlan, err := buildGenerationPlan(fullGraph, serviceRoot, nil)
	if err != nil {
		t.Fatal(err)
	}
	pythonOutput := "services/recommendation-service/generated/event_constants.py"
	manifestOutput := "generated/event_constants_manifest.json"
	if err := writeGeneration(
		contractcodegen.NewSourceFromGraph("metadata", fullGraph),
		fullPlan,
		serviceRoot,
		pythonOutput,
		manifestOutput,
	); err != nil {
		t.Fatal(err)
	}
	stalePath := filepath.Join(
		serviceRoot,
		"services/content-service/generated/media/media_asset/contract/event/events.go",
	)
	original, err := os.ReadFile(stalePath)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(stalePath, append(original, []byte("// drift\n")...), 0o644); err != nil {
		t.Fatal(err)
	}

	reducedGraph := eventConstantsFixtureGraph()
	reducedGraph.Objects = reducedGraph.Objects[:2]
	reducedGraph.Governance.Objects = reducedGraph.Governance.Objects[:2]
	reducedGraph.Documents = reducedGraph.Documents[:5]
	reducedPlan, err := buildGenerationPlan(reducedGraph, serviceRoot, nil)
	if err != nil {
		t.Fatal(err)
	}
	err = writeGeneration(
		contractcodegen.NewSourceFromGraph("metadata", reducedGraph),
		reducedPlan,
		serviceRoot,
		pythonOutput,
		manifestOutput,
	)
	if err == nil || !strings.Contains(err.Error(), "drifted from prior manifest") {
		t.Fatalf("tampered retirement error = %v", err)
	}
	if _, statErr := os.Stat(stalePath); statErr != nil {
		t.Fatalf("tampered stale output was removed: %v", statErr)
	}

	if err := os.WriteFile(stalePath, original, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := writeGeneration(
		contractcodegen.NewSourceFromGraph("metadata", reducedGraph),
		reducedPlan,
		serviceRoot,
		pythonOutput,
		manifestOutput,
	); err != nil {
		t.Fatal(err)
	}
	if _, statErr := os.Stat(stalePath); !os.IsNotExist(statErr) {
		t.Fatalf("manifest-owned stale output was not retired: %v", statErr)
	}
	var manifest ownershipManifest
	if err := json.Unmarshal(
		[]byte(readTestFile(t, filepath.Join(serviceRoot, manifestOutput))),
		&manifest,
	); err != nil {
		t.Fatal(err)
	}
	if len(manifest.Outputs) != 3 {
		t.Fatalf("retired manifest outputs = %#v", manifest.Outputs)
	}
}

func TestEventConstantsGenerationIsByteDeterministic(t *testing.T) {
	t.Parallel()

	first := generateFixtureArtifacts(t)
	second := generateFixtureArtifacts(t)
	if !reflect.DeepEqual(first, second) {
		t.Fatalf("event constants generation drifted\nfirst=%#v\nsecond=%#v", first, second)
	}
}

func TestEventConstantsExclusionIsOnlyForMissingWireIdentities(t *testing.T) {
	t.Parallel()

	serviceRoot := t.TempDir()
	writeDomainOwner(t, serviceRoot, "foo-service", "foo")
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "foo.item", Domain: "foo", Name: "Item",
			SourcePath: "foo/catalog/item/object.yaml",
		}},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "foo.item",
			Events: []ast.EventDefinition{{
				ObjectID: "foo.item", Name: "ItemCreated",
				DeliverySemantics: "transactional_outbox",
				WireEventType:     "ItemCreated", SourcePath: "foo/catalog/item/events.yaml",
			}},
		}}},
	}
	if _, err := buildGenerationPlan(
		contractGraph,
		serviceRoot,
		[]string{"foo.item"},
	); err == nil || !strings.Contains(err.Error(), "remove the exclusion") {
		t.Fatalf("authored object exclusion error = %v", err)
	}
	contractGraph.Governance.Objects[0].Events[0].WireEventType = ""
	if _, err := buildGenerationPlan(contractGraph, serviceRoot, nil); err == nil ||
		!strings.Contains(err.Error(), "requires wire_event_type") {
		t.Fatalf("unexcluded missing wire error = %v", err)
	}
}

func TestEventConstantsGenerationRejectsEveryExclusion(t *testing.T) {
	t.Parallel()

	serviceRoot := t.TempDir()
	err := run(
		filepath.Join(t.TempDir(), "missing-metadata"),
		serviceRoot,
		"services/recommendation-service/generated/event_constants.py",
		"generated/event_constants_manifest.json",
		[]string{"content.media_asset"},
		false,
	)
	if err == nil || !strings.Contains(
		err.Error(),
		"--exclude-object is permitted only with --check-plan",
	) {
		t.Fatalf("generation exclusion error = %v", err)
	}
	if _, statErr := os.Stat(filepath.Join(serviceRoot, "generated")); !os.IsNotExist(statErr) {
		t.Fatalf("rejected generation wrote output: %v", statErr)
	}
}

func eventConstantsFixtureGraph() *graph.ContractGraph {
	objects := []ast.Object{
		{ID: "foo.item", Domain: "foo", Name: "Item", SourcePath: "foo/catalog/item/object.yaml"},
		{ID: "user.user_account", Domain: "user", Name: "UserAccount", SourcePath: "user/account/user_account/object.yaml"},
		{ID: "content.media_asset", Domain: "content", Name: "MediaAsset", SourcePath: "content/media/media_asset/object.yaml"},
	}
	packets := []ast.ObjectGovernance{
		{ObjectID: "foo.item", Events: []ast.EventDefinition{{
			ObjectID: "foo.item", Name: "ItemCreated",
			DeliverySemantics: "transactional_outbox",
			WireEventType:     "foo.item.created", ClientWSType: "ItemChanged",
			SourcePath: "foo/catalog/item/events.yaml",
		}}},
		{ObjectID: "user.user_account", Events: []ast.EventDefinition{{
			ObjectID: "user.user_account", Name: "UserClosed",
			DeliverySemantics: "transactional_outbox",
			WireEventType:     "UserClosed", SourcePath: "user/account/user_account/events.yaml",
		}}},
		{ObjectID: "content.media_asset", Events: []ast.EventDefinition{{
			ObjectID: "content.media_asset", Name: "MediaAssetCreated",
			DeliverySemantics: "transactional_outbox",
			WireEventType:     "MediaAssetCreated",
			SourcePath:        "content/media/media_asset/events.yaml",
		}}},
	}
	documents := []ast.SourceDocument{
		jsonDocument("foo/catalog/item/fields.yaml", `{
			"entity":"Item","fields":[{"name":"itemId","type":"string"}]
		}`),
		jsonDocument("foo/catalog/item/events.yaml", `{"events":[{
			"name":"ItemCreated","delivery_semantics":"transactional_outbox",
			"wire_event_type":"foo.item.created","client_ws_type":"ItemChanged"
		}]}`),
		jsonDocument("user/account/user_account/fields.yaml", `{
			"entity":"UserAccount","fields":[{"name":"userId","type":"string"}]
		}`),
		jsonDocument("user/account/user_account/events.yaml", `{"events":[{
			"name":"UserClosed","delivery_semantics":"transactional_outbox",
			"wire_event_type":"UserClosed"
		}]}`),
		jsonDocument("user/account/user_account/storage.yaml", `{"codegen":{
			"enabled":true,"package":"user"
		}}`),
		jsonDocument("content/media/media_asset/fields.yaml", `{
			"entity":"MediaAsset","fields":[{"name":"mediaAssetId","type":"string"}]
		}`),
		jsonDocument("content/media/media_asset/events.yaml", `{"events":[{
			"name":"MediaAssetCreated","delivery_semantics":"transactional_outbox",
			"wire_event_type":"MediaAssetCreated"
		}]}`),
	}
	return &graph.ContractGraph{
		Objects:    objects,
		Governance: ast.MetadataGovernance{Objects: packets},
		Documents:  documents,
	}
}

func generateFixtureArtifacts(t *testing.T) map[string]string {
	t.Helper()
	serviceRoot := t.TempDir()
	writeDomainOwner(t, serviceRoot, "foo-service", "foo")
	writeDomainOwner(t, serviceRoot, "user-service", "user")
	writeDomainOwner(t, serviceRoot, "content-service", "content")
	contractGraph := eventConstantsFixtureGraph()
	plan, err := buildGenerationPlan(
		contractGraph,
		serviceRoot,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := writeGeneration(
		contractcodegen.NewSourceFromGraph("metadata", contractGraph),
		plan,
		serviceRoot,
		"services/recommendation-service/generated/event_constants.py",
		"generated/event_constants_manifest.json",
	); err != nil {
		t.Fatal(err)
	}
	result := map[string]string{}
	for _, relative := range []string{
		"services/foo-service/generated/catalog/item/contract/event/events.go",
		"services/user-service/generated/account/user_account/contract/user/event/events.g.go",
		"services/content-service/generated/media/media_asset/contract/event/events.go",
		"services/recommendation-service/generated/event_constants.py",
		"generated/event_constants_manifest.json",
	} {
		result[relative] = readTestFile(t, filepath.Join(serviceRoot, relative))
	}
	return result
}

func jsonDocument(path, content string) ast.SourceDocument {
	return ast.SourceDocument{Path: path, Content: json.RawMessage(content)}
}

func writeDomainOwner(t *testing.T, root, service, domain string) {
	t.Helper()
	path := filepath.Join(root, "services", service, "contracts", "domain.yaml")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("domain: "+domain+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func readTestFile(t *testing.T, path string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func mapKeys(values map[string]string) []string {
	result := make([]string, 0, len(values))
	for key := range values {
		result = append(result, key)
	}
	return result
}
