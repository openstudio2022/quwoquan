package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// enumFieldBinding is one generated Dart field whose owning contract
// declaration carries an `enum_ref`.
//
// The enum typed-binding gate used to rediscover these bindings by matching
// generated field names against every `enum_ref` in the contract tree. A short
// name such as `status` legitimately binds PostStatus in one object and nothing
// at all in another, so that heuristic reported unrelated `final String status`
// declarations as debt while a genuinely drifted field could hide behind a
// stale name. Only the generator knows which contract declaration produced
// which Dart field, so it emits the mapping and the gate reads it.
type enumFieldBinding struct {
	GeneratedPath  string `json:"generatedPath"`
	DartClass      string `json:"dartClass"`
	DartField      string `json:"dartField"`
	DartType       string `json:"dartType"`
	EnumRef        string `json:"enumRef"`
	ContractType   string `json:"contractType"`
	ContractSource string `json:"contractSource"`
	ClientDartType string `json:"clientDartType"`
	Typed          bool   `json:"typed"`
}

type fieldBindingReport struct {
	Generator           string             `json:"generator"`
	ContractGraphSHA256 string             `json:"contractGraphSha256"`
	Bindings            []enumFieldBinding `json:"bindings"`
}

var (
	// pendingEnumFieldBindings holds bindings recorded by a renderer that has
	// not been written to disk yet. Renderers build a string and hand it to
	// writeFile, so attaching on write is what gives every binding its real
	// generated path without threading an output path through every renderer.
	pendingEnumFieldBindings []enumFieldBinding
	enumFieldBindings        []enumFieldBinding
)

func resetEnumFieldBindings() {
	pendingEnumFieldBindings = nil
	enumFieldBindings = nil
}

// recordEnumFieldBinding is called from every renderer that emits a
// `final <type> <field>;` for a contract field. Fields without an `enum_ref`
// carry no typed-binding obligation and are dropped here so the report stays
// the enum inventory rather than a copy of every generated declaration.
func recordEnumFieldBinding(binding enumFieldBinding) {
	binding.EnumRef = strings.TrimSpace(binding.EnumRef)
	if binding.EnumRef == "" {
		return
	}
	binding.DartClass = strings.TrimSpace(binding.DartClass)
	binding.DartField = strings.TrimSpace(binding.DartField)
	binding.DartType = strings.TrimSpace(binding.DartType)
	binding.ContractType = strings.TrimSpace(binding.ContractType)
	binding.ContractSource = filepath.ToSlash(strings.TrimSpace(binding.ContractSource))
	binding.ClientDartType = strings.TrimSpace(binding.ClientDartType)
	binding.Typed = dartTypeBindsEnum(binding.DartType, binding.EnumRef)
	pendingEnumFieldBindings = append(pendingEnumFieldBindings, binding)
}

// dartTypeBindsEnum reports whether the emitted Dart type actually carries the
// canonical enum. `List<Visibility>?` and `Visibility` both count; `String` and
// `List<String>` do not.
func dartTypeBindsEnum(dartType string, enumRef string) bool {
	element := strings.TrimSpace(dartType)
	if element == "" || enumRef == "" {
		return false
	}
	for {
		element = strings.TrimSuffix(strings.TrimSpace(element), "?")
		lowered := ""
		for _, prefix := range []string{"List<", "Set<", "Iterable<"} {
			if strings.HasPrefix(element, prefix) && strings.HasSuffix(element, ">") {
				lowered = strings.TrimSuffix(
					strings.TrimPrefix(element, prefix),
					">",
				)
				break
			}
		}
		if lowered == "" {
			break
		}
		element = lowered
	}
	return strings.TrimSpace(element) == strings.TrimSpace(enumRef)
}

// attachPendingEnumFieldBindings binds everything the renderer collected to the
// file it just produced.
func attachPendingEnumFieldBindings(path string) {
	if len(pendingEnumFieldBindings) == 0 {
		return
	}
	normalized := path
	if generatedManifestAppRoot != "" {
		if absolute, err := filepath.Abs(path); err == nil {
			if relative, err := filepath.Rel(
				generatedManifestAppRoot,
				filepath.Clean(absolute),
			); err == nil {
				normalized = relative
			}
		}
	}
	normalized = filepath.ToSlash(normalized)
	for _, binding := range pendingEnumFieldBindings {
		binding.GeneratedPath = normalized
		enumFieldBindings = append(enumFieldBindings, binding)
	}
	pendingEnumFieldBindings = nil
}

func writeFieldBindingReport(path string) error {
	if strings.TrimSpace(path) == "" {
		return nil
	}
	// A renderer that recorded bindings and then never reached writeFile would
	// otherwise silently drop them into the next file. Surfacing them unbound
	// keeps the report honest instead of misattributing them.
	for _, binding := range pendingEnumFieldBindings {
		enumFieldBindings = append(enumFieldBindings, binding)
	}
	pendingEnumFieldBindings = nil

	bindings := append([]enumFieldBinding(nil), enumFieldBindings...)
	sort.Slice(bindings, func(i, j int) bool {
		if bindings[i].GeneratedPath != bindings[j].GeneratedPath {
			return bindings[i].GeneratedPath < bindings[j].GeneratedPath
		}
		if bindings[i].DartClass != bindings[j].DartClass {
			return bindings[i].DartClass < bindings[j].DartClass
		}
		if bindings[i].DartField != bindings[j].DartField {
			return bindings[i].DartField < bindings[j].DartField
		}
		return bindings[i].EnumRef < bindings[j].EnumRef
	})
	deduplicated := make([]enumFieldBinding, 0, len(bindings))
	for index, binding := range bindings {
		if index > 0 && binding == bindings[index-1] {
			continue
		}
		deduplicated = append(deduplicated, binding)
	}
	report := fieldBindingReport{
		Generator:           appOnlyEmitter,
		ContractGraphSHA256: generatedManifestGraph,
		Bindings:            deduplicated,
	}
	data, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("encode enum field binding report: %w", err)
	}
	data = append(data, '\n')
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return fmt.Errorf("create enum field binding report directory: %w", err)
	}
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("write enum field binding report: %w", err)
	}
	fmt.Printf("field binding report: %s (%d bindings)\n", path, len(deduplicated))
	return nil
}
