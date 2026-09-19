package main

// spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-005.t1
import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"quwoquan_service/internal/testsupport/contractsview"
	"strings"
	"testing"
)

func TestReadinessGeneratedInputsReachFixedPointWithoutGraphHashCycle(t *testing.T) {
	serviceRoot, e := filepath.Abs("../..")
	if e != nil {
		t.Fatal(e)
	}
	repo := filepath.Dir(serviceRoot)
	app := filepath.Join(t.TempDir(), "app")
	if e = os.MkdirAll(app, 0700); e != nil {
		t.Fatal(e)
	}
	// Formatter 与生产 App 使用相同语言版本/配置；不以临时目录默认版本冒充。
	for _, name := range []string{"pubspec.yaml", "analysis_options.yaml"} {
		raw, e := os.ReadFile(filepath.Join(repo, "quwoquan_app", name))
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(filepath.Join(app, name), raw, 0600); e != nil {
			t.Fatal(e)
		}
	}
	originalPackage := filepath.Join(repo, "quwoquan_app/packages/quwoquan_cloud_contracts")
	if e = filepath.WalkDir(originalPackage, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		relative, e := filepath.Rel(originalPackage, path)
		if e != nil {
			return e
		}
		target := filepath.Join(app, "packages/quwoquan_cloud_contracts", relative)
		if entry.IsDir() {
			return os.MkdirAll(target, 0700)
		}
		raw, e := os.ReadFile(path)
		if e != nil {
			return e
		}
		return os.WriteFile(target, raw, 0600)
	}); e != nil {
		t.Fatal(e)
	}
	graphRaw, e := os.ReadFile(filepath.Join(serviceRoot, "generated/contract_graph.json"))
	if e != nil {
		t.Fatal(e)
	}
	var graph map[string]any
	if json.Unmarshal(graphRaw, &graph) != nil {
		t.Fatal("graph decode")
	}
	acceptedPath := filepath.Join(repo, "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json")
	accepted, e := os.ReadFile(acceptedPath)
	if e != nil {
		t.Fatal(e)
	}
	var lock map[string]any
	if json.Unmarshal(accepted, &lock) != nil {
		t.Fatal("lock decode")
	}
	paths := map[string]string{}
	var walk func(any)
	walk = func(value any) {
		switch v := value.(type) {
		case map[string]any:
			if path, ok := v["path"].(string); ok {
				if digest, ok := v["sha256"].(string); ok && strings.HasPrefix(path, "quwoquan_app/lib/service/") && strings.Contains(path, "/generated/") {
					paths[strings.TrimPrefix(path, "quwoquan_app/")] = digest
				}
			}
			for _, child := range v {
				walk(child)
			}
		case []any:
			for _, child := range v {
				walk(child)
			}
		}
	}
	walk(graph["readinessEvidence"])
	if len(paths) == 0 {
		t.Fatal("no bound generated inputs")
	}
	view := contractsview.Build(t)
	first := map[string][]byte{}
	for iteration := 0; iteration < 2; iteration++ {
		// 相同语义、不同Graph字节hash，验证绑定文件不把Graph摘要反馈回自身。
		current := append(bytes.Clone(graphRaw), bytes.Repeat([]byte("\n"), iteration+1)...)
		privateGraph := filepath.Join(app, fmt.Sprintf("private-graph-%d.json", iteration))
		if e = os.WriteFile(privateGraph, current, 0600); e != nil {
			t.Fatal(e)
		}
		lock["contractGraph"].(map[string]any)["sha256"] = fmt.Sprintf("%x", sha256.Sum256(current))
		privateLock := filepath.Join(app, "private-lock.json")
		encoded, _ := json.Marshal(lock)
		if e = os.WriteFile(privateLock, encoded, 0600); e != nil {
			t.Fatal(e)
		}
		cmd := exec.Command("go", "run", "./tools/codegen_app_metadata", "--metadata-dir", view, "--contract-graph", privateGraph, "--contract-graph-lock", privateLock, "--app-dir", app, "--generated-manifest", filepath.Join(app, "manifest.json"))
		cmd.Dir = serviceRoot
		output, e := cmd.CombinedOutput()
		if e != nil {
			t.Fatalf("private generation %d: %v\n%s", iteration, e, output)
		}
		for relative := range paths {
			raw, e := os.ReadFile(filepath.Join(app, relative))
			if e != nil {
				t.Fatal(e)
			}
			if iteration == 0 {
				first[relative] = raw
			} else if !bytes.Equal(raw, first[relative]) {
				t.Fatalf("graph hash cycle/nondeterminism: %s", relative)
			}
			production, e := os.ReadFile(filepath.Join(repo, "quwoquan_app", relative))
			if e != nil || !bytes.Equal(raw, production) {
				t.Fatalf("production not at completed formatter fixed point: %s", relative)
			}
		}
	}
	after, e := os.ReadFile(acceptedPath)
	if e != nil || !bytes.Equal(after, accepted) {
		t.Fatal("private generation changed accepted lock")
	}
	t.Logf("two private generations preserve %d bound generated files exactly, despite different Graph hashes", len(paths))
}
