package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
func TestRehearsalObservationGeneratedDartAndPython(t *testing.T) {
	contract, err := loadAppLaunchContract(appLaunchContractTestMetadataDir)
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	artifacts, err := renderAppLaunchContractArtifacts(contract)
	if err != nil {
		t.Fatal(err)
	}
	for _, a := range artifacts {
		name := ""
		if a.RelativePath == appLaunchContractPythonOutput {
			name = "catalog.py"
		}
		if a.RelativePath == appLaunchContractDartOutput {
			name = "catalog.dart"
		}
		if name != "" {
			if os.Getenv("QWQ_OBSERVATION_FORMAL") == "1" {
				content, err := os.ReadFile(filepath.Join("../../..", a.RelativePath))
				if err != nil {
					t.Fatal(err)
				}
				a.Content = content
			}
			if err := os.WriteFile(filepath.Join(dir, name), a.Content, 0600); err != nil {
				t.Fatal(err)
			}
		}
	}
	fresh := func() map[string]any {
		consumers := map[string]any{}
		for _, name := range []string{"auth", "installId", "pending", "rehearsal"} {
			consumers[name] = map[string]any{"state": "not_observed", "namespaceDigest": "", "successfulOperations": []any{}}
		}
		return map[string]any{"schema": "rehearsal-storage-observation", "status": "unavailable", "configurationState": "not_observed", "startupAttemptId": "", "generation": "", "bindingDigest": "", "consumers": consumers}
	}
	digest := "sha256:" + string(makeHex('a', 64))
	available := func() map[string]any {
		v := fresh()
		v["status"] = "available"
		v["configurationState"] = "verified"
		v["startupAttemptId"] = "actual_attempt"
		v["generation"] = "1"
		v["bindingDigest"] = digest
		return v
	}
	valid := []any{fresh(), available()}
	io := available()
	io["consumers"].(map[string]any)["auth"] = map[string]any{"state": "io_observed", "namespaceDigest": digest, "successfulOperations": []any{"read", "write"}}
	valid = append(valid, io)
	constructed := available()
	constructed["consumers"].(map[string]any)["pending"] = map[string]any{"state": "constructed", "namespaceDigest": digest, "successfulOperations": []any{}}
	valid = append(valid, constructed)
	invalid := []any{nil, map[string]any{}}
	for _, mutate := range []func(map[string]any){
		func(v map[string]any) { v["isolationPassed"] = true },
		func(v map[string]any) { delete(v, "generation") },
		func(v map[string]any) { v["generation"] = 1 },
		func(v map[string]any) { v["startupAttemptId"] = "" },
		func(v map[string]any) { v["generation"] = "01" },
		func(v map[string]any) { v["bindingDigest"] = "sha256:bad" },
		func(v map[string]any) { v["status"] = "unavailable" },
		func(v map[string]any) { v["configurationState"] = "invalidated" },
		func(v map[string]any) { v["consumers"].(map[string]any)["extra"] = nil },
	} {
		v := available()
		mutate(v)
		invalid = append(invalid, v)
	}
	for _, c := range []map[string]any{
		{"state": "constructed", "namespaceDigest": digest, "successfulOperations": []any{"read"}},
		{"state": "io_observed", "namespaceDigest": digest, "successfulOperations": []any{}},
		{"state": "invalidated", "namespaceDigest": digest, "successfulOperations": []any{}},
		{"state": "io_observed", "namespaceDigest": digest, "successfulOperations": []any{"read", "read"}},
		{"state": "io_observed", "namespaceDigest": digest, "successfulOperations": []any{"exists"}},
		{"state": "not_observed", "namespaceDigest": "", "successfulOperations": []any{}, "accountId": "private"},
	} {
		v := available()
		v["consumers"].(map[string]any)["auth"] = c
		invalid = append(invalid, v)
	}
	raw, _ := json.Marshal(map[string]any{"valid": valid, "invalid": invalid})
	os.WriteFile(filepath.Join(dir, "cases.json"), raw, 0600)
	python := `import json
from catalog import validate_rehearsal_storage_observation
cases=json.load(open('cases.json'))
for value in cases['valid']: validate_rehearsal_storage_observation(value)
for value in cases['invalid']:
 try: validate_rehearsal_storage_observation(value)
 except (ValueError,TypeError): continue
 raise AssertionError('invalid observation accepted')
print('Python observation PASS')
`
	dart := `import 'dart:convert';
import 'dart:io';
import 'catalog.dart';
void main() {
 final cases=jsonDecode(File('cases.json').readAsStringSync()) as Map;
 for(final value in cases['valid']) {
  final observation=RehearsalStorageObservation.fromWire(value);
  RehearsalStorageObservation.fromWire(observation.toWire());
 }
 for(final value in cases['invalid']) {
  var rejected=false;
  try {RehearsalStorageObservation.fromWire(value);} catch (_) {rejected=true;}
  if(!rejected) throw StateError('invalid observation accepted');
 }
 print('Dart observation PASS');
}
`
	for _, run := range []struct{ exe, name, body string }{{"python3", "verify.py", python}, {"dart", "verify.dart", dart}} {
		os.WriteFile(filepath.Join(dir, run.name), []byte(run.body), 0600)
		cmd := exec.Command(run.exe, run.name)
		cmd.Dir = dir
		cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
		output, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("%s: %v\n%s", run.exe, err, output)
		}
	}
}
func makeHex(b byte, n int) []byte {
	result := make([]byte, n)
	for i := range result {
		result[i] = b
	}
	return result
}
