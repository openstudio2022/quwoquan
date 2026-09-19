// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-004
package semantic_document_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"

	"gopkg.in/yaml.v3"
)

type semanticContract struct {
	Schema                  string `yaml:"schema"`
	SchemaVersion           string `yaml:"schemaVersion"`
	Dialect                 string `yaml:"dialect"`
	DialectVersion          string `yaml:"dialectVersion"`
	CanonicalizationVersion string `yaml:"canonicalizationVersion"`
	OffsetEncoding          string `yaml:"offsetEncoding"`
	RawHTMLPolicy           string `yaml:"rawHtmlPolicy"`
	UnknownValuePolicy      string `yaml:"unknownValuePolicy"`
	ImplementationStatus    struct {
		Role                 string `yaml:"role"`
		CrossLanguageCodegen string `yaml:"crossLanguageCodegen"`
		CodegenGap           string `yaml:"codegenGap"`
	} `yaml:"implementationStatus"`
	ClosedSets struct {
		ProcessingDispositions []string `yaml:"processingDispositions"`
		PublicationDecisions   []string `yaml:"publicationDecisions"`
		CompatibilityDecisions []string `yaml:"compatibilityDecisions"`
		NodeStatuses           []string `yaml:"nodeStatuses"`
		DiagnosticCodes        []string `yaml:"diagnosticCodes"`
	} `yaml:"closedSets"`
	IdentityAndCanonicalization map[string]any `yaml:"identityAndCanonicalization"`
	Model                       struct {
		DocumentEnvelope struct{ Required []string } `yaml:"documentEnvelope"`
	} `yaml:"model"`
	CapabilityCatalog map[string]any `yaml:"capabilityCatalog"`
	NodeRegistry      map[string]struct {
		Status               string
		RequiredCapabilities []string `yaml:"requiredCapabilities"`
		PublicationDecision  string   `yaml:"publicationDecision"`
	} `yaml:"nodeRegistry"`
	InlineRegistry     map[string]any `yaml:"inlineRegistry"`
	MarkdownToSemantic map[string]any `yaml:"markdownToSemantic"`
	HTMLToSemantic     map[string]any `yaml:"htmlToSemantic"`
	SemanticToSafeHTML map[string]any `yaml:"semanticToSafeHtml"`
	StructureContracts map[string]any `yaml:"structureContracts"`
	Compatibility      map[string]any `yaml:"compatibility"`
	Diagnostics        map[string]any `yaml:"diagnostics"`
}

type fixtureContract struct {
	SchemaVersion           string `json:"schemaVersion"`
	DialectVersion          string `json:"dialectVersion"`
	CanonicalizationVersion string `json:"canonicalizationVersion"`
	OffsetEncoding          string `json:"offsetEncoding"`
	ConformanceCases        []struct {
		Name                string   `json:"name"`
		Covers              []string `json:"covers"`
		ExpectedDecision    string   `json:"expectedDecision"`
		ExpectedDisposition string   `json:"expectedDisposition"`
		ExpectedDiagnostics []struct {
			Code string `json:"code"`
		} `json:"expectedDiagnostics"`
		ExpectedDocument map[string]any `json:"expectedDocument"`
	}
}

type dedicatedFixtures struct {
	Cases []struct {
		Name                  string         `json:"name"`
		InputKind             string         `json:"inputKind"`
		ExpectedDisposition   string         `json:"expectedDisposition"`
		PublicationDecision   string         `json:"publicationDecision"`
		CompatibilityDecision string         `json:"compatibilityDecision"`
		Diagnostic            string         `json:"diagnostic"`
		Input                 any            `json:"input"`
		ExpectedNode          map[string]any `json:"expectedNode"`
		RoundTrip             map[string]any `json:"roundTrip"`
	}
}

func TestSemanticDocumentContractDefinesEnvelopeIdentityAndSeparateOutcomes(t *testing.T) {
	contract := loadContract(t)
	if contract.Schema != "semantic_document.authoring" || contract.SchemaVersion == "" || contract.DialectVersion == "" || contract.CanonicalizationVersion == "" {
		t.Fatalf("version envelope incomplete: %+v", contract)
	}
	if contract.RawHTMLPolicy != "forbidden" || contract.UnknownValuePolicy != "reject" || contract.OffsetEncoding != "unicode_scalar_value" {
		t.Fatalf("contract is not fail closed")
	}
	assertExactSet(t, "processingDispositions", contract.ClosedSets.ProcessingDispositions, []string{"preserved", "normalized", "degraded", "metadata_only", "dropped_noise", "unsupported_opaque", "blocked_unsafe"})
	assertExactSet(t, "publicationDecisions", contract.ClosedSets.PublicationDecisions, []string{"publish", "publish_with_losses", "block"})
	assertExactSet(t, "compatibilityDecisions", contract.ClosedSets.CompatibilityDecisions, []string{"compatible", "migrate_explicitly", "incompatible"})
	assertExactSet(t, "envelope", contract.Model.DocumentEnvelope.Required, []string{"schemaVersion", "dialectVersion", "canonicalizationVersion", "offsetEncoding", "nodes", "requiredCapabilities", "assets", "sourceMap", "policyVersion", "losses", "semanticFingerprint", "canonicalDigest"})
	for _, key := range []string{"nodeId", "sourceAnchor", "policyVersion", "losses", "semanticFingerprint", "canonicalDigest", "rawSliceFingerprint"} {
		if _, ok := contract.IdentityAndCanonicalization[key]; !ok {
			t.Errorf("identity contract missing %s", key)
		}
	}
}

func TestSemanticDocumentHasIndependentHTMLInputAndSafeHTMLOutputMappings(t *testing.T) {
	contract := loadContract(t)
	for name, section := range map[string]map[string]any{"markdownToSemantic": contract.MarkdownToSemantic, "htmlToSemantic": contract.HTMLToSemantic, "semanticToSafeHtml": contract.SemanticToSafeHTML} {
		if len(section) == 0 {
			t.Fatalf("%s missing", name)
		}
	}
	if contract.HTMLToSemantic["inputMediaType"] != "text/html" || contract.HTMLToSemantic["rawHtmlTrust"] != "never" {
		t.Fatal("HTML input mapping lacks explicit trust boundary")
	}
	if _, ok := contract.HTMLToSemantic["tagMappings"]; !ok {
		t.Fatal("HTML input tagMappings missing")
	}
	if _, ok := contract.HTMLToSemantic["unknownVisibleNode"]; !ok {
		t.Fatal("unknown visible HTML preservation missing")
	}
	if _, ok := contract.SemanticToSafeHTML["nodeMappings"]; !ok {
		t.Fatal("safe HTML output nodeMappings missing")
	}
}

func TestFormalAndExperimentalNodeRegistryIsCapabilityClosed(t *testing.T) {
	contract := loadContract(t)
	required := []string{"documentTitle", "section", "definitionList", "epigraph", "preformatted", "verse", "details", "factBox", "factRow", "table", "tableCaption", "tableRow", "tableCell", "footnoteReference", "footnoteDefinition", "footnoteList", "bibliography", "externalLinks", "seeAlso", "hatnote", "relatedResources", "figure", "gallery"}
	for _, kind := range required {
		node, ok := contract.NodeRegistry[kind]
		if !ok || node.Status != "formal" || len(node.RequiredCapabilities) == 0 {
			t.Errorf("formal node %s missing or capability-open: %+v", kind, node)
		}
	}
	for kind, node := range contract.NodeRegistry {
		if node.Status == "experimental" && node.PublicationDecision != "block" {
			t.Errorf("experimental node %s is publishable", kind)
		}
	}
	for _, key := range []string{"dimensions", "ids", "capabilityRequiredFields", "allowedOrigins", "fallbackPolicies", "formalNodeRule", "opaqueMutationRule"} {
		if _, ok := contract.CapabilityCatalog[key]; !ok {
			t.Errorf("capability catalog missing %s", key)
		}
	}
}

func TestSharedAndDedicatedFixturesCoverRequiredConformance(t *testing.T) {
	root, contract := serviceRoot(t), loadContract(t)
	var shared fixtureContract
	decodeJSON(t, filepath.Join(root, "services/content-service/contracts/content/post/markdown_block_sequence_cases.json"), &shared)
	if shared.SchemaVersion != contract.SchemaVersion || shared.DialectVersion != contract.DialectVersion || shared.CanonicalizationVersion != contract.CanonicalizationVersion {
		t.Fatal("shared fixture versions drift")
	}
	publication := stringSet(contract.ClosedSets.PublicationDecisions)
	dispositions := stringSet(contract.ClosedSets.ProcessingDispositions)
	diagnostics := stringSet(contract.ClosedSets.DiagnosticCodes)
	covered := map[string]bool{}
	for _, c := range shared.ConformanceCases {
		if !publication[c.ExpectedDecision] || !dispositions[c.ExpectedDisposition] {
			t.Errorf("shared case %s uses noncanonical outcome", c.Name)
		}
		for _, v := range c.Covers {
			covered[v] = true
		}
		for _, d := range c.ExpectedDiagnostics {
			if !diagnostics[d.Code] {
				t.Errorf("unknown diagnostic %s", d.Code)
			}
		}
	}
	var dedicated dedicatedFixtures
	decodeJSON(t, filepath.Join(root, "services/content-service/tests/local_contract/content/post/semantic_document/semantic_document_conformance_cases.json"), &dedicated)
	for _, c := range dedicated.Cases {
		covered[c.Name] = true
		covered[c.ExpectedDisposition] = true
		if !dispositions[c.ExpectedDisposition] {
			t.Errorf("case %s invalid disposition", c.Name)
		}
		if !publication[c.PublicationDecision] {
			t.Errorf("case %s invalid publication decision", c.Name)
		}
		if c.Diagnostic != "" && !diagnostics[c.Diagnostic] {
			t.Errorf("case %s invalid diagnostic", c.Name)
		}
	}
	for _, key := range []string{"preserved", "normalized", "degraded", "metadata_only", "dropped_noise", "unsupported_opaque", "blocked_unsafe", "envelope_complete", "html_data_mw_factbox", "html_span_table", "missing_formal_node_capability", "unknown_schema_major", "canonicalization_mismatch", "raw_html_markdown_blocked", "unknown_visible_html_opaque_roundtrip"} {
		if !covered[key] {
			t.Errorf("fixtures missing %s", key)
		}
	}
}

func TestSemanticDocumentAuthoringContractDeclaresCodegenGap(t *testing.T) {
	c := loadContract(t)
	if c.ImplementationStatus.Role != "authoring_contract" || c.ImplementationStatus.CrossLanguageCodegen != "available" || c.ImplementationStatus.CodegenGap == "" {
		t.Fatalf("codegen status is not honest: %+v", c.ImplementationStatus)
	}
}

func TestPostMarkdownDialectUsesClosedEnum(t *testing.T) {
	var d map[string]any
	decodeYAML(t, filepath.Join(serviceRoot(t), "services/content-service/contracts/content/post/fields.yaml"), &d)
	refs := []map[string]any{}
	collectNamedMappings(d, "markdownDialect", &refs)
	// Post、PostArticleAssetManifest、SubmitContentPostPublicationCommand 各声明一次；
	// 已退役发布载荷不再拥有第四份 dialect。
	if len(refs) != 3 {
		t.Fatalf("markdownDialect declarations=%d", len(refs))
	}
	for _, f := range refs {
		if f["type"] != "enum" || f["enum_ref"] != "SemanticDocumentMarkdownDialect" {
			t.Fatalf("open dialect: %#v", f)
		}
	}
}

func loadContract(t *testing.T) semanticContract {
	var c semanticContract
	decodeYAML(t, filepath.Join(serviceRoot(t), "contracts/metadata/_shared/semantic_document.yaml"), &c)
	return c
}
func decodeYAML(t *testing.T, path string, target any) {
	t.Helper()
	raw, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	if e = yaml.Unmarshal(raw, target); e != nil {
		t.Fatalf("decode %s: %v", path, e)
	}
}
func decodeJSON(t *testing.T, path string, target any) {
	t.Helper()
	raw, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	if e = json.Unmarshal(raw, target); e != nil {
		t.Fatalf("decode %s: %v", path, e)
	}
}
func collectNamedMappings(v any, name string, out *[]map[string]any) {
	switch x := v.(type) {
	case map[string]any:
		if x["name"] == name {
			*out = append(*out, x)
		}
		for _, c := range x {
			collectNamedMappings(c, name, out)
		}
	case []any:
		for _, c := range x {
			collectNamedMappings(c, name, out)
		}
	}
}
func stringSet(v []string) map[string]bool {
	r := map[string]bool{}
	for _, x := range v {
		r[x] = true
	}
	return r
}
func assertExactSet(t *testing.T, n string, g, w []string) {
	t.Helper()
	g = append([]string(nil), g...)
	w = append([]string(nil), w...)
	sort.Strings(g)
	sort.Strings(w)
	if len(g) != len(w) {
		t.Fatalf("%s=%v want=%v", n, g, w)
	}
	for i := range g {
		if g[i] != w[i] {
			t.Fatalf("%s=%v want=%v", n, g, w)
		}
	}
}
func serviceRoot(t *testing.T) string {
	t.Helper()
	_, f, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("caller")
	}
	d := filepath.Dir(f)
	for filepath.Base(d) != "quwoquan_service" {
		p := filepath.Dir(d)
		if p == d {
			t.Fatal("root")
		}
		d = p
	}
	return d
}
