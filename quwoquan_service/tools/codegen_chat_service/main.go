// Command codegen_chat_service generates chat-service HTTP route plumbing from
// object-owned messages/*/service.yaml contracts declared in its manifest.
//
// It emits internal/adapters/http/generated_routes.go: a method+template route
// table plus a catch-all dispatcher that forwards each (non-manual) operation to
// the conventionally named ChatHandler.handle<Operation>(w, r). Operations listed
// under manual_operations in the codegen manifest are excluded (they are either
// registered explicitly in ChatHandler.Routes()/media/internal handlers, or are
// declared in service.yaml but not yet implemented). Duplicate operation or
// method/path ownership is a generator error rather than a last-wins rule.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"text/template"

	"gopkg.in/yaml.v3"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var outputDir string
	var manifestPath string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/chat-service/internal", "chat-service internal output directory")
	flag.StringVar(&manifestPath, "manifest", "services/chat-service/codegen_chat_service_manifest.yaml", "chat-service codegen manifest path")
	flag.Parse()

	manifest, err := loadManifest(manifestPath)
	if err != nil {
		exitErr(fmt.Errorf("load manifest %s: %w", manifestPath, err))
	}
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}

	manual := map[string]bool{}
	for _, op := range manifest.ManualOperations {
		manual[op] = true
	}

	routes, err := collectRoutes(source, manifest.ServiceYAMLs, manual)
	if err != nil {
		exitErr(err)
	}

	rendered, err := render(routeFileData{
		ServiceYAMLsRel: manifest.ServiceYAMLs,
		Routes:          routes,
	})
	if err != nil {
		exitErr(fmt.Errorf("render generated_routes.go: %w", err))
	}

	outPath := filepath.Join(outputDir, filepath.FromSlash(manifest.RoutesOutput))
	if err := os.WriteFile(outPath, rendered, 0o644); err != nil {
		exitErr(fmt.Errorf("write %s: %w", outPath, err))
	}
	fmt.Printf("generated chat-service routes (%d operations) at %s\n", len(routes), outPath)

	errorsFile, err := loadErrorsYAML(source, manifest.ErrorsYAML)
	if err != nil {
		exitErr(fmt.Errorf("load errors.yaml %s: %w", manifest.ErrorsYAML, err))
	}
	errorsRendered := contractcodegen.RenderGoErrorsFile(errorsFile, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_chat_service",
		SourcePath:   filepath.ToSlash(manifest.ErrorsYAML),
		CommentLines: []string{"Chat error sentinels and helpers. user_message from errors.yaml user_message.zh."},
	})
	formattedErrors, err := format.Source([]byte(errorsRendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated errors: %w", err))
	}
	errorsOutPath := filepath.Join(outputDir, filepath.FromSlash(manifest.ErrorsOutput))
	if err := os.WriteFile(errorsOutPath, formattedErrors, 0o644); err != nil {
		exitErr(fmt.Errorf("write %s: %w", errorsOutPath, err))
	}
	fmt.Printf("generated chat-service errors (%d codes) at %s\n", len(errorsFile.Errors), errorsOutPath)
}

type manifestYAML struct {
	ServiceYAMLs     []string `yaml:"service_yamls"`
	RoutesOutput     string   `yaml:"routes_output"`
	ErrorsYAML       string   `yaml:"errors_yaml"`
	ErrorsOutput     string   `yaml:"errors_output"`
	ManualOperations []string `yaml:"manual_operations"`
}

func loadManifest(path string) (manifestYAML, error) {
	var m manifestYAML
	raw, err := os.ReadFile(path)
	if err != nil {
		return m, err
	}
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return m, err
	}
	if len(m.ServiceYAMLs) == 0 {
		return m, fmt.Errorf("manifest missing service_yamls")
	}
	for _, serviceYAML := range m.ServiceYAMLs {
		if serviceYAML == "" {
			return m, fmt.Errorf("manifest service_yamls contains an empty path")
		}
	}
	if m.RoutesOutput == "" {
		return m, fmt.Errorf("manifest missing routes_output")
	}
	if m.ErrorsYAML == "" {
		return m, fmt.Errorf("manifest missing errors_yaml")
	}
	if m.ErrorsOutput == "" {
		return m, fmt.Errorf("manifest missing errors_output")
	}
	return m, nil
}

func loadErrorsYAML(
	source *contractcodegen.Source,
	path string,
) (*contractcodegen.ErrorsFile, error) {
	var file contractcodegen.ErrorsFile
	if err := source.Decode(path, &file); err != nil {
		return nil, err
	}
	return &file, nil
}

type serviceYAML struct {
	APIRoutes []serviceRouteYAML `yaml:"api_routes"`
}

type serviceRouteYAML struct {
	Method    string `yaml:"method"`
	Path      string `yaml:"path"`
	Operation string `yaml:"operation"`
}

func loadServiceYAML(
	source *contractcodegen.Source,
	path string,
) (serviceYAML, error) {
	var s serviceYAML
	if err := source.Decode(path, &s); err != nil {
		return s, err
	}
	return s, nil
}

func collectRoutes(
	source *contractcodegen.Source,
	serviceYAMLs []string,
	manual map[string]bool,
) ([]routeData, error) {
	routes := make([]routeData, 0)
	operationOwners := make(map[string]string)
	pathOwners := make(map[string]string)
	for _, serviceYAML := range serviceYAMLs {
		svc, err := loadServiceYAML(source, serviceYAML)
		if err != nil {
			return nil, fmt.Errorf("load service.yaml %s: %w", serviceYAML, err)
		}
		for _, route := range svc.APIRoutes {
			if route.Operation == "" || manual[route.Operation] {
				continue
			}
			if owner, exists := operationOwners[route.Operation]; exists {
				return nil, fmt.Errorf("duplicate chat operation %q in %s and %s", route.Operation, owner, serviceYAML)
			}
			pathKey := route.Method + " " + route.Path
			if owner, exists := pathOwners[pathKey]; exists {
				return nil, fmt.Errorf("duplicate chat route %q in %s and %s", pathKey, owner, serviceYAML)
			}
			operationOwners[route.Operation] = serviceYAML
			pathOwners[pathKey] = serviceYAML
			routes = append(routes, routeData{
				Method:    route.Method,
				Template:  route.Path,
				Operation: route.Operation,
			})
		}
	}
	return routes, nil
}

type routeData struct {
	Method    string
	Template  string
	Operation string
}

type routeFileData struct {
	ServiceYAMLsRel []string
	Routes          []routeData
}

const routeTemplate = `// Code generated by tools/codegen_chat_service from:
{{- range .ServiceYAMLsRel}}
//   - contracts/metadata/{{.}}
{{- end}}
// DO NOT EDIT.
package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

type routeEntry struct {
	Method    string
	Template  string
	Operation string
}

var generatedRouteTable = []routeEntry{
{{- range .Routes}}
	{"{{.Method}}", "{{.Template}}", "{{.Operation}}"},
{{- end}}
}

func RegisterGeneratedRoutes(mux *http.ServeMux, h *ChatHandler) {
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		op, ok := resolveGeneratedOperation(r.Method, r.URL.Path)
		if !ok {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "接口不存在", "route not found"))
			return
		}
		dispatchGeneratedOperation(h, op, w, r)
	})
}

func dispatchGeneratedOperation(h *ChatHandler, operation string, w http.ResponseWriter, r *http.Request) {
	switch operation {
{{- range .Routes}}
	case "{{.Operation}}":
		h.handle{{.Operation}}(w, r)
{{- end}}
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "接口不存在", "operation not found"))
	}
}

func resolveGeneratedOperation(method, path string) (string, bool) {
	for _, r := range generatedRouteTable {
		if r.Method != method {
			continue
		}
		if matchTemplate(r.Template, path) {
			return r.Operation, true
		}
	}
	return "", false
}

func matchTemplate(template, path string) bool {
	tParts := strings.Split(strings.Trim(template, "/"), "/")
	pParts := strings.Split(strings.Trim(path, "/"), "/")
	if len(tParts) != len(pParts) {
		return false
	}
	for i, tp := range tParts {
		if strings.HasPrefix(tp, "{") && strings.HasSuffix(tp, "}") {
			continue
		}
		if tp != pParts[i] {
			return false
		}
	}
	return true
}

func extractPathParam(path, template, paramName string) string {
	tParts := strings.Split(strings.Trim(template, "/"), "/")
	pParts := strings.Split(strings.Trim(path, "/"), "/")
	target := "{" + paramName + "}"
	for i, tp := range tParts {
		if tp == target && i < len(pParts) {
			return pParts[i]
		}
	}
	return ""
}
`

func render(data routeFileData) ([]byte, error) {
	tmpl, err := template.New("routes").Parse(routeTemplate)
	if err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		return nil, err
	}
	formatted, err := format.Source(buf.Bytes())
	if err != nil {
		return nil, fmt.Errorf("gofmt: %w\n--- source ---\n%s", err, buf.String())
	}
	return formatted, nil
}

func exitErr(err error) {
	fmt.Fprintln(os.Stderr, "codegen_chat_service:", err)
	os.Exit(1)
}
