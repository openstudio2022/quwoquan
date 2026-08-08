package load

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"

	"gopkg.in/yaml.v3"
)

var objectTopLevelKeys = stringSet(
	"kind", "description", "identity", "access", "relationships", "members",
	"search_policy", "assistant_access",
	"counter_strategy", "relation_signal", "business_rules", "lifecycle",
	"local_identity_reasons", "external_authority",
)

var operationsTopLevelKeys = stringSet(
	"api_routes", "runtime_entrypoints", "commercial_defaults", "consumers", "contract_test",
	"delivery_slo", "description", "incoming_call_slo", "privacy_contract",
	"readiness_cases", "response_list_key", "upstreams", "externalDependencies",
)

// Option 配置 loader 的仓库级输入。metadata-dir 是 PPID 作用域的契约拷贝视图
// （见 `quwoquan_service/Makefile` 的 CONTRACT_VIEW），从它读不到仓库源码树，因此
// 需要物理树输入的派生必须由调用方显式传入仓库根。
type Option func(*settings)

type settings struct {
	repoRoot     string
	contractView *contractViewProvenance
}

// WithRepoRoot 打开派生式 readiness evidence：loader 会从 repoRoot 之下的云侧、端侧
// 与 Ops 物理树反推每个对象的 evidence packet。不传该 option 时 catalog 不携带任何
// evidence，因为 metadata 本身不允许声明 evidence。
func WithRepoRoot(repoRoot string) Option {
	return func(target *settings) { target.repoRoot = strings.TrimSpace(repoRoot) }
}

// Load 将 metadata 规范化为单一 AST。它只读取业务对象目录，不把控制面域清单计入业务对象。
func Load(metadataDir string, options ...Option) (*ast.Catalog, error) {
	resolved := settings{}
	for _, option := range options {
		option(&resolved)
	}
	contractView, provenanceErr := loadContractViewProvenance(metadataDir)
	if provenanceErr != nil {
		return nil, provenanceErr
	}
	resolved.contractView = contractView
	catalog := &ast.Catalog{}
	var loadErrors []error

	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			name := entry.Name()
			if name == ".git" || name == "test_fixtures" {
				return filepath.SkipDir
			}
			if path != metadataDir && strings.HasPrefix(name, "_") {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.Name() != "object.yaml" {
			return nil
		}

		object, objectErr := loadObject(metadataDir, path)
		if objectErr != nil {
			loadErrors = append(loadErrors, objectErr)
			return nil
		}
		catalog.Objects = append(catalog.Objects, object)

		objectDir := filepath.Dir(path)
		operationsPath := filepath.Join(objectDir, "operations.yaml")
		if _, statErr := os.Stat(operationsPath); statErr == nil {
			operations, runtimeEntrypoints, serviceErr := loadService(
				metadataDir,
				operationsPath,
				object,
			)
			if serviceErr != nil {
				loadErrors = append(loadErrors, serviceErr)
			} else {
				catalog.Operations = append(catalog.Operations, operations...)
				catalog.RuntimeEntrypoints = append(
					catalog.RuntimeEntrypoints,
					runtimeEntrypoints...,
				)
				readinessCases, readinessErr := loadReadinessCases(
					metadataDir,
					operationsPath,
					object,
					operations,
					runtimeEntrypoints,
					resolved.repoRoot,
					resolved.contractView,
				)
				if readinessErr != nil {
					loadErrors = append(loadErrors, readinessErr)
				} else {
					catalog.ReadinessCases = append(
						catalog.ReadinessCases,
						readinessCases...,
					)
				}
			}
		}
		projections, _, projectionErr := loadProjections(metadataDir, objectDir, object)
		if projectionErr != nil {
			loadErrors = append(loadErrors, projectionErr)
		} else {
			catalog.Projections = append(catalog.Projections, projections...)
		}
		return nil
	})
	if err != nil {
		loadErrors = append(loadErrors, err)
	}
	collectSourceDigests(catalog, metadataDir, &loadErrors)
	deriveBusinessObjectMaps(catalog, &loadErrors)
	if governanceErr := loadMetadataGovernance(metadataDir, catalog); governanceErr != nil {
		loadErrors = append(loadErrors, governanceErr)
	}
	if lifecycleRepoRoot := lifecycleImplementationRepoRoot(resolved); lifecycleRepoRoot != "" {
		bindLifecycleEntrypointImplementations(catalog, lifecycleRepoRoot, &loadErrors)
	}
	if resolved.repoRoot != "" {
		deriveReadinessEvidence(catalog, resolved.repoRoot, &loadErrors)
	}
	if len(loadErrors) > 0 {
		return nil, errors.Join(loadErrors...)
	}
	return catalog, nil
}

// lifecycleImplementationRepoRoot returns the canonical physical source root
// used to bind authored lifecycle consumers. A validated contract-view
// provenance manifest already identifies that root, so repository-backed
// compiler/tests must not silently emit a graph without implementation
// evidence merely because they omitted WithRepoRoot. Readiness evidence stays
// explicitly opt-in through settings.repoRoot; this fallback only closes the
// required lifecycle implementation field.
func lifecycleImplementationRepoRoot(resolved settings) string {
	if resolved.repoRoot != "" {
		return resolved.repoRoot
	}
	if resolved.contractView != nil {
		return resolved.contractView.repositoryRoot
	}
	return ""
}

// bindLifecycleEntrypointImplementations binds every authored lifecycle
// consumer to one object-local production implementation. The graph remains
// responsible for deciding whether that implementation is the sole ingress of
// a non-HTTP projection; having an HTTP/runtime entrypoint must not weaken the
// authored lifecycle edge itself into an unchecked facet+method string.
func bindLifecycleEntrypointImplementations(
	catalog *ast.Catalog,
	repoRoot string,
	errs *[]error,
) {
	bindLifecycleImplementations(catalog, repoRoot, errs)
}

func collectSourceDigests(catalog *ast.Catalog, metadataDir string, errs *[]error) {
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if entry.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		switch strings.ToLower(filepath.Ext(entry.Name())) {
		case ".yaml", ".yml", ".json":
			addSourceDocument(catalog, metadataDir, path, errs)
		}
		return nil
	})
	if err != nil {
		*errs = append(*errs, err)
	}
}

func loadObject(metadataDir, path string) (ast.Object, error) {
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return ast.Object{}, err
	}
	if err := rejectUnknownTopLevel(path, top, objectTopLevelKeys); err != nil {
		return ast.Object{}, err
	}

	relative := relativePath(metadataDir, path)
	segments := strings.Split(relative, "/")
	if len(segments) != 4 || segments[3] != "object.yaml" {
		return ast.Object{}, fmt.Errorf(
			"%s: object metadata path must be <domain>/<context>/<object>/object.yaml",
			path,
		)
	}
	domain := segments[0]
	objectSegment := strings.ReplaceAll(segments[2], "-", "_")
	name := pascalCaseIdentifier(objectSegment)
	id := domain + "." + objectSegment

	kind, explicit, err := resolveObjectKind(top)
	if err != nil {
		return ast.Object{}, fmt.Errorf("%s: %w", path, err)
	}
	object := ast.Object{
		ID:             id,
		Domain:         domain,
		Name:           name,
		Kind:           kind,
		KindExplicit:   explicit,
		AggregateOwner: "",
		SourcePath:     relativePath(metadataDir, path),
	}
	if lifecycle := top["lifecycle"]; lifecycle != nil {
		object.Lifecycle, err = decodeLifecycle(lifecycle, object.SourcePath)
		if err != nil {
			return ast.Object{}, fmt.Errorf("%s: lifecycle: %w", path, err)
		}
	}
	if storage, storageErr := storagecontract.LoadOptional(filepath.Join(filepath.Dir(path), "storage.yaml")); storageErr != nil {
		return ast.Object{}, storageErr
	} else if storage != nil {
		object.StorageBackend = strings.TrimSpace(storage.Backend)
	}
	if members := top["members"]; members != nil {
		if object.Kind != ast.ObjectKindAggregateRoot {
			return ast.Object{}, fmt.Errorf(
				"%s: members are only allowed on aggregate_root, got %q",
				path,
				object.Kind,
			)
		}
		object.Members, err = decodeMembers(members)
		if err != nil {
			return ast.Object{}, fmt.Errorf("%s: members: %w", path, err)
		}
		for index := range object.Members {
			object.Members[index].AggregateOwner = object.Name
		}
	}
	return object, nil
}

func resolveObjectKind(top map[string]*yaml.Node) (ast.ObjectKind, bool, error) {
	if raw := scalarString(top["kind"]); raw != "" {
		kind := ast.ObjectKind(raw)
		if !validObjectKind(kind) {
			return "", true, fmt.Errorf("invalid object_kind %q", raw)
		}
		return kind, true, nil
	}
	return "", false, fmt.Errorf("kind is required")
}

func validObjectKind(kind ast.ObjectKind) bool {
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindProcessManager,
		ast.ObjectKindProjection,
		ast.ObjectKindExternalReference,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindRuntimeSession:
		return true
	default:
		return false
	}
}

func decodeMembers(node *yaml.Node) ([]ast.Member, error) {
	if node.Kind == yaml.ScalarNode && node.Tag == "!!null" {
		return nil, nil
	}
	if node.Kind != yaml.MappingNode {
		return nil, fmt.Errorf("must be a mapping keyed by member name")
	}
	members := make([]ast.Member, 0, len(node.Content)/2)
	seenNames := make(map[string]struct{}, len(node.Content)/2)
	for index := 0; index < len(node.Content); index += 2 {
		name := strings.TrimSpace(node.Content[index].Value)
		if !memberTypeNamePattern.MatchString(name) {
			return nil, fmt.Errorf("member name %q must be canonical PascalCase", name)
		}
		if _, duplicate := seenNames[name]; duplicate {
			return nil, fmt.Errorf("duplicate member name %q", name)
		}
		seenNames[name] = struct{}{}
		mapping, err := mappingFromNode(node.Content[index+1])
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownMemberFields(name, mapping); err != nil {
			return nil, err
		}
		identity, err := decodeMemberIdentity(name, mapping["identity"])
		if err != nil {
			return nil, err
		}
		member := ast.Member{
			Name:        name,
			Identity:    identity,
			Cardinality: scalarString(mapping["cardinality"]),
			Ownership:   scalarString(mapping["ownership"]),
			WriteAccess: scalarString(mapping["write_access"]),
			Description: scalarString(mapping["description"]),
		}
		rawKind := scalarString(mapping["kind"])
		member.Kind = ast.ObjectKind(rawKind)
		if member.Kind != ast.ObjectKindOwnedEntity && member.Kind != ast.ObjectKindValueObject {
			return nil, fmt.Errorf("member %q has invalid object_kind %q", member.Name, rawKind)
		}
		rawMaximum := scalarString(mapping["max_cardinality"])
		value, parseErr := strconv.Atoi(rawMaximum)
		if parseErr != nil {
			return nil, fmt.Errorf("member %q max_cardinality: %w", member.Name, parseErr)
		}
		member.MaxCardinality = value
		if member.Description == "" {
			return nil, fmt.Errorf("member %q description is required", member.Name)
		}
		if !validMemberCardinality(member.Cardinality) {
			return nil, fmt.Errorf("member %q has invalid cardinality %q", member.Name, member.Cardinality)
		}
		if member.Ownership != "aggregate" {
			return nil, fmt.Errorf("member %q ownership must be aggregate, got %q", member.Name, member.Ownership)
		}
		if member.MaxCardinality <= 0 ||
			(member.Cardinality == "many" && member.MaxCardinality < 2) ||
			((member.Cardinality == "one" || member.Cardinality == "zero_or_one") && member.MaxCardinality != 1) {
			requiredMaximum := "at least 2"
			if member.Cardinality == "one" || member.Cardinality == "zero_or_one" {
				requiredMaximum = "1"
			}
			return nil, fmt.Errorf(
				"member %q cardinality %q requires canonical max_cardinality %s",
				member.Name,
				member.Cardinality,
				requiredMaximum,
			)
		}
		_, identityDeclared := mapping["identity"]
		_, writeAccessDeclared := mapping["write_access"]
		appendOnlyNode, appendOnlyDeclared := mapping["append_only"]
		if member.Kind == ast.ObjectKindOwnedEntity {
			if len(member.Identity) == 0 {
				return nil, fmt.Errorf("owned member %q must declare identity", member.Name)
			}
			if member.WriteAccess != "aggregate_facade_only" {
				return nil, fmt.Errorf("owned member %q write_access must be aggregate_facade_only", member.Name)
			}
			if appendOnlyDeclared {
				return nil, fmt.Errorf("owned member %q cannot declare append_only", member.Name)
			}
		} else {
			if identityDeclared || writeAccessDeclared {
				return nil, fmt.Errorf("value member %q cannot declare identity or write_access", member.Name)
			}
			if appendOnlyDeclared {
				if appendOnlyNode.Kind != yaml.ScalarNode || appendOnlyNode.Tag != "!!bool" ||
					strings.TrimSpace(appendOnlyNode.Value) != "true" {
					return nil, fmt.Errorf("value member %q append_only, when declared, must be true", member.Name)
				}
				member.AppendOnly = true
			}
		}
		members = append(members, member)
	}
	return members, nil
}

var (
	memberTypeNamePattern  = regexp.MustCompile(`^[A-Z][A-Za-z0-9]*$`)
	memberFieldNamePattern = regexp.MustCompile(`^[a-z][A-Za-z0-9]*$`)
)

func decodeMemberIdentity(memberName string, node *yaml.Node) ([]string, error) {
	if node == nil {
		return nil, nil
	}
	if node.Kind != yaml.SequenceNode || len(node.Content) == 0 {
		return nil, fmt.Errorf("member %q identity must be a non-empty sequence", memberName)
	}
	seen := make(map[string]struct{}, len(node.Content))
	identity := make([]string, 0, len(node.Content))
	for _, item := range node.Content {
		name := strings.TrimSpace(item.Value)
		if item.Kind != yaml.ScalarNode || !memberFieldNamePattern.MatchString(name) {
			return nil, fmt.Errorf("member %q identity field %q must be canonical lowerCamelCase", memberName, name)
		}
		if _, duplicate := seen[name]; duplicate {
			return nil, fmt.Errorf("member %q has duplicate identity field %q", memberName, name)
		}
		seen[name] = struct{}{}
		identity = append(identity, name)
	}
	return identity, nil
}

var memberDeclarationKeys = stringSet(
	"kind", "identity", "cardinality", "max_cardinality", "ownership",
	"write_access", "append_only", "description",
)

func rejectUnknownMemberFields(name string, mapping map[string]*yaml.Node) error {
	unknown := make([]string, 0)
	for key := range mapping {
		if _, ok := memberDeclarationKeys[key]; !ok {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) == 0 {
		return nil
	}
	sort.Strings(unknown)
	return fmt.Errorf("member %q has unknown fields: %s", name, strings.Join(unknown, ", "))
}

func validMemberCardinality(cardinality string) bool {
	switch cardinality {
	case "one", "zero_or_one", "many":
		return true
	default:
		return false
	}
}

func loadProjections(metadataDir, objectDir string, object ast.Object) ([]ast.Projection, []string, error) {
	projectionDir := filepath.Join(objectDir, "projections")
	info, err := os.Stat(projectionDir)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil, nil
	}
	if err != nil {
		return nil, nil, err
	}
	if !info.IsDir() {
		return nil, nil, fmt.Errorf("%s: projections must be a directory", projectionDir)
	}

	var projections []ast.Projection
	var projectionPaths []string
	err = filepath.WalkDir(projectionDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
			return nil
		}
		top, loadErr := loadTopLevelMapping(path)
		if loadErr != nil {
			return loadErr
		}
		readModel := scalarString(top["read_model"])
		readModelExplicit := strings.TrimSpace(readModel) != ""
		dartClass := scalarString(top["dart_class"])
		outputPath := scalarString(top["output_path"])
		var clientProjection struct {
			DartClass        string `yaml:"dart_class"`
			OutputPath       string `yaml:"output_path"`
			ExternalDartPath string `yaml:"external_dart_path"`
			Fields           []struct {
				Name string `yaml:"name"`
			} `yaml:"fields"`
		}
		if node := top["client_projection"]; node != nil {
			if decodeErr := node.Decode(&clientProjection); decodeErr != nil {
				return fmt.Errorf("%s: client_projection: %w", path, decodeErr)
			}
			if dartClass == "" {
				dartClass = strings.TrimSpace(clientProjection.DartClass)
			}
			if outputPath == "" {
				outputPath = strings.TrimSpace(clientProjection.OutputPath)
			}
		}
		projectionName := scalarString(top["projection"])
		if readModel == "" {
			readModel = dartClass
		}
		if readModel == "" {
			readModel = projectionName
		}
		if readModel == "" {
			// projections/ 也承载紧邻对象的客户端配置文档；没有任何投影身份时不进入图。
			return nil
		}
		fieldNames := projectionFieldNames(top["fields"])
		if len(fieldNames) == 0 {
			for _, field := range clientProjection.Fields {
				if name := strings.TrimSpace(field.Name); name != "" {
					fieldNames = append(fieldNames, name)
				}
			}
		}
		projections = append(projections, ast.Projection{
			ID:                object.ID + "." + readModel,
			Domain:            object.Domain,
			ObjectID:          object.ID,
			ReadModel:         readModel,
			ReadModelExplicit: readModelExplicit,
			DartClass:         dartClass,
			OutputPath:        outputPath,
			ExternalDartPath:  strings.TrimSpace(clientProjection.ExternalDartPath),
			FieldNames:        fieldNames,
			SourceEntities:    stringSequence(top["source_entities"]),
			SourceEvents:      stringSequence(top["source_events"]),
			SourcePath:        relativePath(metadataDir, path),
		})
		projectionPaths = append(projectionPaths, path)
		return nil
	})
	return projections, projectionPaths, err
}

func projectionFieldNames(node *yaml.Node) []string {
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil
	}
	result := make([]string, 0, len(node.Content))
	for _, item := range node.Content {
		if item.Kind == yaml.ScalarNode {
			if name := strings.TrimSpace(item.Value); name != "" {
				result = append(result, name)
			}
			continue
		}
		mapping, err := mappingFromNode(item)
		if err != nil {
			continue
		}
		if name := strings.TrimSpace(scalarString(mapping["name"])); name != "" {
			result = append(result, name)
		}
	}
	return result
}

func stringSequence(node *yaml.Node) []string {
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil
	}
	result := make([]string, 0, len(node.Content))
	for _, item := range node.Content {
		if value := strings.TrimSpace(item.Value); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func loadTopLevelMapping(path string) (map[string]*yaml.Node, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var document yaml.Node
	if err := yaml.Unmarshal(data, &document); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if len(document.Content) != 1 {
		return nil, fmt.Errorf("%s: expected one YAML document", path)
	}
	return mappingFromNode(document.Content[0])
}

func loadOptionalTopLevelMapping(path string) (map[string]*yaml.Node, error) {
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	return loadTopLevelMapping(path)
}

func mappingFromNode(node *yaml.Node) (map[string]*yaml.Node, error) {
	if node.Kind != yaml.MappingNode {
		return nil, fmt.Errorf("expected mapping")
	}
	result := make(map[string]*yaml.Node, len(node.Content)/2)
	for index := 0; index < len(node.Content); index += 2 {
		key := node.Content[index].Value
		if _, exists := result[key]; exists {
			return nil, fmt.Errorf("duplicate key %q", key)
		}
		result[key] = node.Content[index+1]
	}
	return result, nil
}

func rejectUnknownTopLevel(path string, mapping map[string]*yaml.Node, allowed map[string]struct{}) error {
	var unknown []string
	for key := range mapping {
		if _, ok := allowed[key]; !ok {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) == 0 {
		return nil
	}
	sort.Strings(unknown)
	return fmt.Errorf("%s: unknown top-level fields: %s", path, strings.Join(unknown, ", "))
}

func scalarString(node *yaml.Node) string {
	if node == nil || node.Kind != yaml.ScalarNode || node.Tag == "!!null" {
		return ""
	}
	return strings.TrimSpace(node.Value)
}

func scalarBool(node *yaml.Node) bool {
	if node == nil || node.Kind != yaml.ScalarNode {
		return false
	}
	value, err := strconv.ParseBool(strings.TrimSpace(node.Value))
	return err == nil && value
}

func stringSet(values ...string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		result[value] = struct{}{}
	}
	return result
}

func relativePath(root, path string) string {
	rel, err := filepath.Rel(root, path)
	if err != nil {
		return filepath.ToSlash(path)
	}
	return filepath.ToSlash(rel)
}

func pascalCaseIdentifier(value string) string {
	var result strings.Builder
	upperNext := true
	for _, current := range value {
		if current == '_' || current == '-' {
			upperNext = true
			continue
		}
		if upperNext && current >= 'a' && current <= 'z' {
			current -= 'a' - 'A'
		}
		result.WriteRune(current)
		upperNext = false
	}
	return result.String()
}

// SourceDocuments loads an explicit set of canonical metadata documents with
// the same normalization used by the full ContractGraph compiler. It does not
// scan sibling contracts, so metadata-only generators are not coupled to
// unrelated object validation or App operation handoff state.
func SourceDocuments(
	root string,
	relativePaths []string,
) ([]ast.SourceDocument, error) {
	if _, err := loadContractViewProvenance(root); err != nil {
		return nil, err
	}
	catalog := &ast.Catalog{}
	var errs []error
	for _, relative := range relativePaths {
		normalized := filepath.ToSlash(filepath.Clean(relative))
		if normalized == "." ||
			filepath.IsAbs(relative) ||
			normalized == ".." ||
			strings.HasPrefix(normalized, "../") {
			errs = append(
				errs,
				fmt.Errorf("metadata document path escapes root: %s", relative),
			)
			continue
		}
		addSourceDocument(
			catalog,
			root,
			filepath.Join(root, filepath.FromSlash(normalized)),
			&errs,
		)
	}
	if len(errs) > 0 {
		return nil, errors.Join(errs...)
	}
	sort.Slice(catalog.Documents, func(i, j int) bool {
		return catalog.Documents[i].Path < catalog.Documents[j].Path
	})
	return append([]ast.SourceDocument(nil), catalog.Documents...), nil
}

func addSourceDocument(catalog *ast.Catalog, root, path string, errs *[]error) {
	data, err := os.ReadFile(path)
	if err != nil {
		*errs = append(*errs, err)
		return
	}
	sum := sha256.Sum256(data)
	relative := relativePath(root, path)
	digest := hex.EncodeToString(sum[:])
	catalog.Sources = append(catalog.Sources, ast.SourceDigest{
		Path: relative, SHA256: digest,
	})
	if strings.HasPrefix(relative, "_schemas/") ||
		strings.Contains("/"+relative+"/", "/test_fixtures/") {
		return
	}
	var value any
	if err := yaml.Unmarshal(data, &value); err != nil {
		*errs = append(*errs, fmt.Errorf("%s: parse source document: %w", path, err))
		return
	}
	content, err := json.Marshal(value)
	if err != nil {
		*errs = append(*errs, fmt.Errorf("%s: normalize source document: %w", path, err))
		return
	}
	mediaType := "application/yaml"
	if strings.EqualFold(filepath.Ext(path), ".json") {
		mediaType = "application/json"
	}
	catalog.Documents = append(catalog.Documents, ast.SourceDocument{
		Path: relative, SHA256: digest, MediaType: mediaType, Content: content,
	})
}
