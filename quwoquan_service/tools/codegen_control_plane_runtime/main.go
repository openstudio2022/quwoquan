package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	metacontrolplane "quwoquan_service/internal/metadata/controlplane"
	"quwoquan_service/internal/metadata/validate"
)

type artifact struct {
	fileName  string
	constName string
	data      any
}

var compileContractSource = contractcodegen.NewSource

func main() {
	var metadataDir string
	var goOutDir string
	var pythonOutDir string

	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&goOutDir, "go-out-dir", "generated/control_plane", "Go output directory")
	flag.StringVar(&pythonOutDir, "python-out-dir", "services/rec-model-service/generated/control_plane", "Python output directory")
	flag.Parse()

	source, err := compileContractSource(metadataDir, validate.ProfileBaseline)
	must(err)
	artifacts := collectArtifacts(source)

	must(os.MkdirAll(goOutDir, 0o755))
	must(os.MkdirAll(pythonOutDir, 0o755))

	for _, item := range artifacts {
		writeGoArtifact(filepath.Join(goOutDir, item.fileName+".go"), item.constName, item.data)
		writePythonArtifact(filepath.Join(pythonOutDir, item.fileName+".py"), strings.ToUpper(item.fileName), item.data)
	}
	writePythonIndex(filepath.Join(pythonOutDir, "__init__.py"), artifacts)
}

func collectArtifacts(source *contractcodegen.Source) []artifact {
	const sharedRoot = "_shared"
	const controlRoot = "_control_plane"

	items := []artifact{
		{
			fileName:  "shared_control_plane",
			constName: "SharedControlPlane",
			data:      readYAMLAny(source, filepath.Join(sharedRoot, "control_plane.yaml")),
		},
		{
			fileName:  "portal_shell",
			constName: "PortalShell",
			data:      readYAMLAny(source, filepath.Join(controlRoot, "portal_shell.yaml")),
		},
		{
			fileName:  "portal_menu",
			constName: "PortalMenu",
			data:      readYAMLAny(source, filepath.Join(controlRoot, "portal_menu.yaml")),
		},
	}
	if source.Has(filepath.Join(controlRoot, "domain_onboarding_schema.yaml")) {
		items = append(items, artifact{
			fileName:  "domain_onboarding_schema",
			constName: "DomainOnboardingSchema",
			data:      readYAMLAny(source, filepath.Join(controlRoot, "domain_onboarding_schema.yaml")),
		})
	}
	if len(source.Paths(filepath.Join(controlRoot, "domains"), ".yaml")) > 0 {
		items = append(items, artifact{
			fileName:  "domain_onboarding_domains",
			constName: "DomainOnboardingDomains",
			data:      readOnboardingDomains(source, filepath.Join(controlRoot, "domains")),
		})
	}

	for _, domain := range []string{"platform", "product"} {
		baseDir := filepath.Join(controlRoot, domain)
		if len(source.Paths(baseDir, ".yaml")) == 0 {
			continue
		}

		for _, def := range []struct {
			fileName  string
			constName string
			path      string
		}{
			{fileName: domain + "_control_plane", constName: toPascalCase(domain) + "ControlPlane", path: filepath.Join(baseDir, "control_plane.yaml")},
			{fileName: domain + "_config_schema", constName: toPascalCase(domain) + "ConfigSchema", path: filepath.Join(baseDir, "config_schema.yaml")},
			{fileName: domain + "_workflow", constName: toPascalCase(domain) + "Workflow", path: filepath.Join(baseDir, "workflow.yaml")},
			{fileName: domain + "_audit_schema", constName: toPascalCase(domain) + "AuditSchema", path: filepath.Join(baseDir, "audit_schema.yaml")},
		} {
			if !source.Has(def.path) {
				continue
			}
			data := readYAMLAny(source, def.path)
			if strings.HasSuffix(def.path, "control_plane.yaml") {
				document, ok := data.(map[string]any)
				if !ok {
					must(fmt.Errorf("%s must decode to an object", def.path))
				}
				must(metacontrolplane.HydrateOperationReferences(document, source.Graph()))
				data = document
			}
			items = append(items, artifact{
				fileName:  def.fileName,
				constName: def.constName,
				data:      data,
			})
		}
	}

	sort.Slice(items, func(i, j int) bool {
		return items[i].fileName < items[j].fileName
	})
	return items
}

func readOnboardingDomains(source *contractcodegen.Source, dir string) any {
	out := map[string]any{}
	for _, path := range source.Paths(dir, ".yaml") {
		data := readYAMLAny(source, path)
		doc, ok := data.(map[string]any)
		if !ok {
			continue
		}
		domain := fmt.Sprint(doc["domain"])
		if strings.TrimSpace(domain) == "" {
			name := filepath.Base(path)
			domain = strings.TrimSuffix(name, filepath.Ext(name))
		}
		out[domain] = doc
	}
	return out
}

func readYAMLAny(source *contractcodegen.Source, path string) any {
	var out any
	must(source.Decode(path, &out))
	return normalizeYAML(out)
}

func normalizeYAML(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		normalized := make(map[string]any, len(typed))
		for key, inner := range typed {
			normalized[key] = normalizeYAML(inner)
		}
		return normalized
	case map[any]any:
		normalized := make(map[string]any, len(typed))
		for key, inner := range typed {
			normalized[fmt.Sprint(key)] = normalizeYAML(inner)
		}
		return normalized
	case []any:
		normalized := make([]any, 0, len(typed))
		for _, inner := range typed {
			normalized = append(normalized, normalizeYAML(inner))
		}
		return normalized
	default:
		return typed
	}
}

func writeGoArtifact(path, constName string, data any) {
	payload, err := json.MarshalIndent(data, "", "  ")
	must(err)

	content := fmt.Sprintf(`// Code generated by codegen_control_plane_runtime. DO NOT EDIT.

package control_plane

import "encoding/json"

var %sRaw = []byte(%q)

func MustLoad%s() map[string]any {
	var out map[string]any
	if err := json.Unmarshal(%sRaw, &out); err != nil {
		panic(err)
	}
	return out
}
`, constName, string(payload), constName, constName)
	writeFile(path, content)
}

func writePythonArtifact(path, constName string, data any) {
	payload, err := json.MarshalIndent(data, "", "  ")
	must(err)

	content := fmt.Sprintf(`# Code generated by codegen_control_plane_runtime. DO NOT EDIT.

import json

_%s_JSON = r'''%s'''
%s = json.loads(_%s_JSON)
`, constName, string(payload), constName, constName)
	writeFile(path, content)
}

func writePythonIndex(path string, items []artifact) {
	lines := []string{"# Code generated by codegen_control_plane_runtime. DO NOT EDIT.", ""}
	for _, item := range items {
		lines = append(lines, fmt.Sprintf("from .%s import %s", item.fileName, strings.ToUpper(item.fileName)))
	}
	lines = append(lines, "")
	writeFile(path, strings.Join(lines, "\n"))
}

func writeFile(path, content string) {
	must(os.MkdirAll(filepath.Dir(path), 0o755))
	must(os.WriteFile(path, []byte(content), 0o644))
	fmt.Printf("generated: %s\n", path)
}

func toPascalCase(s string) string {
	parts := strings.FieldsFunc(s, func(r rune) bool {
		return r == '-' || r == '_' || r == '.'
	})
	if len(parts) == 0 {
		parts = []string{s}
	}
	var out strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		out.WriteString(strings.ToUpper(part[:1]))
		if len(part) > 1 {
			out.WriteString(part[1:])
		}
	}
	return out.String()
}

func must(err error) {
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
