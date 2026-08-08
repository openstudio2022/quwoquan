package load

import (
	"bufio"
	"errors"
	"fmt"
	goast "go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"

	"quwoquan_service/internal/metadata/ast"
)

type lifecycleMethodDefinition struct {
	receiver string
	method   string
	path     string
}

type lifecycleFacetDefinition struct {
	isInterface bool
	methods     map[string]struct{}
	bases       []string
	path        string
}

type lifecycleSourceIndex struct {
	facets  map[string][]lifecycleFacetDefinition
	methods []lifecycleMethodDefinition
}

// bindLifecycleImplementations derives the production source identity for each
// authored lifecycle consumer. It is intentionally kept separate from YAML
// decoding: metadata authors own facet+method, while the compiler owns the
// repository path and exact bytes. The caller activates this only with a real
// repository root, never for metadata-only decoding.
func bindLifecycleImplementations(
	catalog *ast.Catalog,
	repoRoot string,
	errs *[]error,
) {
	serviceRoots, err := resolveServiceRootsByDomain(repoRoot)
	if err != nil {
		*errs = append(*errs, err)
		return
	}
	for objectIndex := range catalog.Objects {
		object := &catalog.Objects[objectIndex]
		if object.Lifecycle == nil || len(object.Lifecycle.EventConsumers) == 0 {
			continue
		}
		contextName, objectSegment, ok := objectPathSegments(*object)
		if !ok {
			*errs = append(*errs, fmt.Errorf(
				"%s: lifecycle implementation owner path is not canonical",
				object.ID,
			))
			continue
		}
		_, objectRoot, resolveErr := resolveObjectImplementationRoot(
			repoRoot,
			serviceRoots[object.Domain],
			object.Domain,
			contextName,
			objectSegment,
		)
		if resolveErr != nil {
			*errs = append(*errs, resolveErr)
			continue
		}
		if objectRoot == "" {
			*errs = append(*errs, fmt.Errorf(
				"%s: lifecycle implementation object root is missing",
				object.ID,
			))
			continue
		}
		index, indexErr := buildLifecycleSourceIndex(objectRoot)
		if indexErr != nil {
			*errs = append(*errs, fmt.Errorf("%s: %w", object.ID, indexErr))
			continue
		}
		for consumerIndex := range object.Lifecycle.EventConsumers {
			consumer := &object.Lifecycle.EventConsumers[consumerIndex]
			artifact, artifactErr := resolveLifecycleImplementation(
				repoRoot,
				*object,
				*consumer,
				index,
			)
			if artifactErr != nil {
				*errs = append(*errs, artifactErr)
				continue
			}
			consumer.Implementation = artifact
		}
	}
}

func buildLifecycleSourceIndex(objectRoot string) (lifecycleSourceIndex, error) {
	index := lifecycleSourceIndex{
		facets: map[string][]lifecycleFacetDefinition{},
	}
	for _, layer := range []string{cloudLayerApplication, cloudLayerAdapters} {
		layerRoot := filepath.Join(objectRoot, layer)
		err := filepath.WalkDir(layerRoot, func(
			path string,
			entry fs.DirEntry,
			walkErr error,
		) error {
			if walkErr != nil {
				if errors.Is(walkErr, fs.ErrNotExist) {
					return nil
				}
				return walkErr
			}
			if entry.IsDir() {
				if _, excluded := nonProductionSegments[entry.Name()]; excluded {
					return filepath.SkipDir
				}
				return nil
			}
			if isTestSourceName(entry.Name()) {
				return nil
			}
			switch strings.ToLower(filepath.Ext(entry.Name())) {
			case ".go":
				return indexGoLifecycleSource(path, &index)
			case ".py":
				return indexPythonLifecycleSource(path, &index)
			default:
				return nil
			}
		})
		if err != nil && !errors.Is(err, fs.ErrNotExist) {
			return lifecycleSourceIndex{}, err
		}
	}
	return index, nil
}

func indexGoLifecycleSource(path string, index *lifecycleSourceIndex) error {
	file, err := parser.ParseFile(token.NewFileSet(), path, nil, 0)
	if err != nil {
		return fmt.Errorf("parse lifecycle Go source %s: %w", path, err)
	}
	for _, declaration := range file.Decls {
		switch typed := declaration.(type) {
		case *goast.GenDecl:
			if typed.Tok != token.TYPE {
				continue
			}
			for _, specification := range typed.Specs {
				typeSpec, ok := specification.(*goast.TypeSpec)
				if !ok || typeSpec.Name == nil {
					continue
				}
				definition := lifecycleFacetDefinition{
					methods: map[string]struct{}{},
					path:    path,
				}
				if interfaceType, ok := typeSpec.Type.(*goast.InterfaceType); ok {
					definition.isInterface = true
					for _, field := range interfaceType.Methods.List {
						for _, name := range field.Names {
							definition.methods[name.Name] = struct{}{}
						}
					}
				}
				index.facets[typeSpec.Name.Name] = append(
					index.facets[typeSpec.Name.Name],
					definition,
				)
			}
		case *goast.FuncDecl:
			if typed.Recv == nil || typed.Name == nil || len(typed.Recv.List) != 1 {
				continue
			}
			// A declaration or comment-only/empty method is not a production
			// handler. Keep it out of the implementation index so authored
			// lifecycle consumers fail closed instead of binding to a marker.
			if typed.Body == nil || len(typed.Body.List) == 0 {
				continue
			}
			receiver := goReceiverName(typed.Recv.List[0].Type)
			if receiver == "" {
				continue
			}
			index.methods = append(index.methods, lifecycleMethodDefinition{
				receiver: receiver,
				method:   typed.Name.Name,
				path:     path,
			})
		}
	}
	return nil
}

func goReceiverName(expression goast.Expr) string {
	switch typed := expression.(type) {
	case *goast.Ident:
		return typed.Name
	case *goast.StarExpr:
		return goReceiverName(typed.X)
	case *goast.IndexExpr:
		return goReceiverName(typed.X)
	case *goast.IndexListExpr:
		return goReceiverName(typed.X)
	default:
		return ""
	}
}

var pythonClassPattern = regexp.MustCompile(
	`^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s*:`,
)

var pythonMethodPattern = regexp.MustCompile(
	`^(\s*)(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(`,
)

func indexPythonLifecycleSource(path string, index *lifecycleSourceIndex) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	type pythonClass struct {
		name         string
		indent       int
		isInterface  bool
		methods      map[string]struct{}
		methodBodies map[string][]string
		method       string
		methodIndent int
		bases        []string
	}
	var current *pythonClass
	flush := func() {
		if current == nil {
			return
		}
		index.facets[current.name] = append(
			index.facets[current.name],
			lifecycleFacetDefinition{
				isInterface: current.isInterface,
				methods:     current.methods,
				bases:       current.bases,
				path:        path,
			},
		)
		for method, body := range current.methodBodies {
			if current.isInterface || !pythonLifecycleMethodBodySubstantive(body) {
				continue
			}
			index.methods = append(index.methods, lifecycleMethodDefinition{
				receiver: current.name,
				method:   method,
				path:     path,
			})
		}
		current = nil
	}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		if match := pythonClassPattern.FindStringSubmatch(line); match != nil {
			flush()
			bases := pythonBaseNames(match[3])
			lowerBases := strings.ToLower(match[3])
			current = &pythonClass{
				name:         match[2],
				indent:       len(match[1]),
				isInterface:  strings.Contains(lowerBases, "protocol") || strings.Contains(lowerBases, "abc"),
				methods:      map[string]struct{}{},
				methodBodies: map[string][]string{},
				methodIndent: -1,
				bases:        bases,
			}
			continue
		}
		if current == nil || strings.TrimSpace(line) == "" ||
			strings.HasPrefix(strings.TrimSpace(line), "#") {
			continue
		}
		indent := len(line) - len(strings.TrimLeft(line, " \t"))
		if indent <= current.indent {
			flush()
			continue
		}
		methodMatch := pythonMethodPattern.FindStringSubmatch(line)
		if methodMatch != nil {
			method := methodMatch[2]
			current.methods[method] = struct{}{}
			current.methodBodies[method] = nil
			current.method = method
			current.methodIndent = indent
			continue
		}
		if current.method != "" && indent > current.methodIndent {
			current.methodBodies[current.method] = append(
				current.methodBodies[current.method],
				strings.TrimSpace(line),
			)
		} else if indent <= current.methodIndent {
			current.method = ""
			current.methodIndent = -1
		}
	}
	flush()
	if err := scanner.Err(); err != nil {
		return err
	}
	return nil
}

func pythonLifecycleMethodBodySubstantive(lines []string) bool {
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") || line == "pass" ||
			line == "..." || line == "return None" ||
			line == "raise NotImplementedError" ||
			line == "raise NotImplementedError()" {
			continue
		}
		// A one-line docstring is descriptive metadata, not an executable
		// handler body. Multi-line docstrings still require executable code
		// after the closing delimiter to become substantive.
		if (strings.HasPrefix(line, `"""`) && strings.HasSuffix(line, `"""`)) ||
			(strings.HasPrefix(line, `'''`) && strings.HasSuffix(line, `'''`)) {
			continue
		}
		return true
	}
	return false
}

func pythonBaseNames(raw string) []string {
	parts := strings.Split(raw, ",")
	bases := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if index := strings.Index(part, "["); index >= 0 {
			part = part[:index]
		}
		if index := strings.LastIndex(part, "."); index >= 0 {
			part = part[index+1:]
		}
		part = strings.TrimSpace(part)
		if part != "" {
			bases = append(bases, part)
		}
	}
	return bases
}

func resolveLifecycleImplementation(
	repoRoot string,
	object ast.Object,
	consumer ast.LifecycleEventConsumer,
	index lifecycleSourceIndex,
) (*ast.EvidenceArtifact, error) {
	methodNames := map[string]struct{}{
		exportedLifecycleMethod(consumer.Method): {},
		consumer.Method:                          {},
		lowerCamelToSnake(consumer.Method):       {},
	}
	facets := index.facets[consumer.Facet]
	if len(facets) != 1 {
		return nil, fmt.Errorf(
			"%s lifecycle consumer %s requires one concrete or interface facet %s in its owning application/adapters, found %d",
			object.ID,
			consumer.Name,
			consumer.Facet,
			len(facets),
		)
	}
	definition := facets[0]
	var candidates []lifecycleMethodDefinition
	if !definition.isInterface {
		candidates = concreteLifecycleMethods(
			consumer.Facet,
			methodNames,
			index,
			map[string]struct{}{},
		)
	} else {
		interfaceMethod := ""
		for methodName := range methodNames {
			if _, ok := definition.methods[methodName]; ok {
				interfaceMethod = methodName
				break
			}
		}
		if interfaceMethod == "" {
			return nil, fmt.Errorf(
				"%s lifecycle consumer %s facet %s does not declare method %s",
				object.ID,
				consumer.Name,
				consumer.Facet,
				consumer.Method,
			)
		}
		receiverMethods := map[string]map[string]lifecycleMethodDefinition{}
		for _, method := range index.methods {
			if receiverMethods[method.receiver] == nil {
				receiverMethods[method.receiver] = map[string]lifecycleMethodDefinition{}
			}
			receiverMethods[method.receiver][method.method] = method
		}
		for receiver, methods := range receiverMethods {
			if receiver == consumer.Facet {
				continue
			}
			implements := true
			for required := range definition.methods {
				if _, ok := methods[required]; !ok {
					implements = false
					break
				}
			}
			if implements {
				candidates = append(candidates, methods[interfaceMethod])
			}
		}
	}
	paths := map[string]struct{}{}
	for _, candidate := range candidates {
		paths[candidate.path] = struct{}{}
	}
	if len(paths) != 1 {
		return nil, fmt.Errorf(
			"%s lifecycle consumer %s must resolve %s.%s to exactly one owning production source, found %d",
			object.ID,
			consumer.Name,
			consumer.Facet,
			consumer.Method,
			len(paths),
		)
	}
	var path string
	for candidate := range paths {
		path = candidate
	}
	digest, err := fileDigest(path)
	if err != nil {
		return nil, err
	}
	return &ast.EvidenceArtifact{
		Path:   relativePath(repoRoot, path),
		SHA256: digest,
	}, nil
}

func concreteLifecycleMethods(
	facet string,
	methodNames map[string]struct{},
	index lifecycleSourceIndex,
	visited map[string]struct{},
) []lifecycleMethodDefinition {
	if _, seen := visited[facet]; seen {
		return nil
	}
	visited[facet] = struct{}{}
	var direct []lifecycleMethodDefinition
	for _, method := range index.methods {
		if method.receiver != facet {
			continue
		}
		if _, ok := methodNames[method.method]; ok {
			direct = append(direct, method)
		}
	}
	if len(direct) != 0 {
		return direct
	}
	definitions := index.facets[facet]
	if len(definitions) != 1 {
		return nil
	}
	definition := definitions[0]
	var inherited []lifecycleMethodDefinition
	for _, base := range definition.bases {
		inherited = append(
			inherited,
			concreteLifecycleMethods(base, methodNames, index, visited)...,
		)
	}
	paths := map[string]struct{}{}
	for _, method := range inherited {
		paths[method.path] = struct{}{}
	}
	if len(paths) != 1 || strings.TrimSpace(definition.path) == "" {
		return inherited
	}
	// The business-specific subclass is the effective production identity even
	// when the durable scan loop is inherited from a shared base. The inherited
	// method is still required above, so a marker-only subclass cannot resolve.
	return []lifecycleMethodDefinition{{
		receiver: facet,
		method:   inherited[0].method,
		path:     definition.path,
	}}
}

func exportedLifecycleMethod(value string) string {
	runes := []rune(strings.TrimSpace(value))
	if len(runes) == 0 {
		return ""
	}
	runes[0] = unicode.ToUpper(runes[0])
	return string(runes)
}

func lowerCamelToSnake(value string) string {
	var result strings.Builder
	for index, current := range strings.TrimSpace(value) {
		if unicode.IsUpper(current) {
			if index > 0 {
				result.WriteRune('_')
			}
			result.WriteRune(unicode.ToLower(current))
			continue
		}
		result.WriteRune(current)
	}
	return result.String()
}

func sortedLifecycleImplementationPaths(index lifecycleSourceIndex) []string {
	paths := map[string]struct{}{}
	for _, method := range index.methods {
		paths[method.path] = struct{}{}
	}
	result := make([]string, 0, len(paths))
	for path := range paths {
		result = append(result, path)
	}
	sort.Strings(result)
	return result
}
