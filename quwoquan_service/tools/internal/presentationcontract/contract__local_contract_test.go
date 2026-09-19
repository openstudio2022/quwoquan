package presentationcontract

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
func canonicalSource(t *testing.T) []byte {
	t.Helper()
	data, err := os.ReadFile("../../../contracts/metadata/_shared/types.yaml")
	if err != nil {
		t.Fatal(err)
	}
	return data
}

// testModel 直接读取生产 canonical；不提供替代基线。
func testModel(t *testing.T) Model {
	t.Helper()
	model, err := Load(canonicalSource(t))
	if err != nil {
		t.Fatal(err)
	}
	return model
}

func TestCanonicalAuthoringReady(t *testing.T) {
	// 此门禁不得把描述正文或测试临时子集冒充生产基线。
	if _, err := Load(canonicalSource(t)); err != nil {
		t.Fatal(err)
	}
}

func TestCanonicalCollections(t *testing.T) {
	m := testModel(t)
	original := m.Collections(false)
	expected, err := m.Digest(original)
	if err != nil {
		t.Fatal(err)
	}
	for _, values := range original {
		for i, j := 0, len(values)-1; i < j; i, j = i+1, j-1 {
			values[i], values[j] = values[j], values[i]
		}
	}
	actual, err := m.Digest(original)
	if err != nil || actual != expected {
		t.Fatalf("order changed digest: %s %v", actual, err)
	}
	for _, f := range m.Fields {
		for _, bad := range [][]string{nil, {f.Values[0], f.Values[0]}, {"unknown"}, {" " + f.Values[0]}, {f.Values[0] + " "}, {""}} {
			value := m.Collections(false)
			value[f.Name] = bad
			if _, err := m.Digest(value); err == nil {
				t.Fatalf("accepted invalid %s: %v", f.Name, bad)
			}
		}
	}
	empty := m.Collections(false)
	for key := range empty {
		empty[key] = []string{}
	}
	raw, err := m.Canonical(empty)
	if err != nil || strings.Contains(string(raw), "null") {
		t.Fatalf("empty array changed semantics: %s %v", raw, err)
	}
	missing := m.Collections(false)
	delete(missing, m.Fields[0].Name)
	if _, err := m.Canonical(missing); err == nil {
		t.Fatal("accepted missing collection")
	}
	extra := m.Collections(false)
	extra["unknown"] = []string{}
	if _, err := m.Canonical(extra); err == nil {
		t.Fatal("accepted unknown collection")
	}
	before := m.Collections(true)
	m.Fields[0].Values = append(m.Fields[0].Values, "new_future_wire_value")
	if !reflect.DeepEqual(before, m.Collections(true)) {
		t.Fatal("enum expansion expanded fixed baseline")
	}
}

func TestMetadataRejectsMissingAndInvalidBaseline(t *testing.T) {
	var doc map[string]any
	if err := yaml.Unmarshal(canonicalSource(t), &doc); err != nil {
		t.Fatal(err)
	}
	typ := doc["types"].(map[string]any)[TypeName].(map[string]any)
	delete(typ, "missing_declaration")
	raw, _ := yaml.Marshal(doc)
	if _, err := Load(raw); err == nil {
		t.Fatal("accepted missing structured baseline")
	}
	for _, baseline := range []any{map[string]any{}, map[string]any{"contentTypes": []string{"unknown"}}} {
		typ["missing_declaration"] = baseline
		raw, _ = yaml.Marshal(doc)
		if _, err := Load(raw); err == nil {
			t.Fatal("accepted invalid structured baseline")
		}
	}
}

func scratchDir(t *testing.T) string {
	t.Helper()
	root, err := filepath.Abs("../../../../.qwq_output/env/repo/local/presentationcontract-tests")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(root, 0755); err != nil {
		t.Fatal(err)
	}
	dir, err := os.MkdirTemp(root, "run-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	return dir
}
func writeTestFile(t *testing.T, dir, name string, content []byte) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, name), content, 0644); err != nil {
		t.Fatal(err)
	}
}
func command(t *testing.T, dir, name string, args ...string) {
	t.Helper()
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("%s %v: %v\n%s", name, args, err, output)
	}
}

func TestGeneratedPythonGolden(t *testing.T) {
	m := testModel(t)
	dir := scratchDir(t)
	fixture, err := m.GoldenFixture()
	if err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, dir, "golden.json", fixture)
	pyCode, err := m.RenderPython()
	if err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, dir, "contract.py", []byte(pyCode))
	writeTestFile(t, dir, "test.py", []byte(pythonGoldenRunner))
	command(t, dir, "python3", "test.py")
}

const pythonGoldenRunner = `import json
import contract as c
for case in json.load(open("golden.json")):
    value = case["collections"]
    assert c.canonical_client_content_presentation_contract(value).decode() == case["canonical"]
    assert c.digest_client_content_presentation_contract(value) == case["digest"]
    value["contractDigest"] = case["digest"]
    c.validate_client_content_presentation_contract(value)
    c.decode_client_content_presentation_contract(json.dumps(value).encode())
    value["contractDigest"] = "sha256:forged"
    try:
        c.validate_client_content_presentation_contract(value)
    except ValueError:
        pass
    else:
        raise AssertionError("forged digest accepted")
for bad in (b"null", b"{}", b"[]", b" ", b'{"contentTypes":[],"contentTypes":[]}'):
    try:
        c.decode_client_content_presentation_contract(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid declaration accepted")
assert c.decode_client_content_presentation_contract(None) == c.missing_declaration_content_presentation_contract()
for key, allowed in c.COMPILED_CONTENT_PRESENTATION_COLLECTIONS.items():
    for bad in (None, [allowed[0], allowed[0]], ["unknown"], [" " + allowed[0]], [False], {}):
        value = c.compiled_content_presentation_contract()
        value[key] = bad
        try:
            c.digest_client_content_presentation_contract(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid collection accepted")
`

func TestGoldenFixtureContainsNoImplicitProductionTable(t *testing.T) {
	m := testModel(t)
	raw, err := m.GoldenFixture()
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name        string
		Collections map[string][]string
		Digest      string
	}
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	if len(cases) != 3 {
		t.Fatal("expected compiled, baseline and empty fixtures")
	}
	for _, c := range cases {
		digest, err := m.Digest(c.Collections)
		if err != nil || digest != c.Digest {
			t.Fatal("fixture drift", err)
		}
	}
}
