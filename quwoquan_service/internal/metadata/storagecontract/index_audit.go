package storagecontract

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

type IndexDeclaration struct {
	SourcePath       string   `json:"sourcePath"`
	Service          string   `json:"service"`
	Context          string   `json:"context"`
	Object           string   `json:"object"`
	StoreKind        string   `json:"storeKind"`
	StoreName        string   `json:"storeName"`
	IndexName        string   `json:"indexName"`
	Keys             []string `json:"keys"`
	KeyOrderAuthored bool     `json:"keyOrderAuthored"`
	Unique           bool     `json:"unique"`
	Lifecycle        bool     `json:"lifecycle"`
	// GeneratedCreation records that the canonical storage generator can emit
	// this exact index shape. It is not sufficient on its own: the audit also
	// requires an object-owned generated store binding and a production
	// composition scope which constructs that store and invokes EnsureIndexes.
	GeneratedCreation bool `json:"generatedCreation,omitempty"`
}

type IndexAuditIssue struct {
	Code        string   `json:"code"`
	SourcePath  string   `json:"sourcePath"`
	StoreName   string   `json:"storeName"`
	IndexName   string   `json:"indexName"`
	Keys        []string `json:"keys"`
	Explanation string   `json:"explanation"`
}

type IndexAuditReport struct {
	Declarations int               `json:"declarations"`
	Created      int               `json:"created"`
	Used         int               `json:"used"`
	Issues       []IndexAuditIssue `json:"issues"`
}

type sourceFile struct {
	path   string
	text   string
	tokens map[string]struct{}
	scopes []sourceScope
}

type sourceScope struct {
	name          string
	text          string
	tokens        map[string]struct{}
	references    map[string]struct{}
	storeBindings map[string]map[string]struct{}
	indexKeySets  [][]string
	createsIndex  bool
	queriesStore  bool
	ensureIndexes bool
}

var sourceTokenPattern = regexp.MustCompile(`[A-Za-z_][A-Za-z0-9_.]*`)

var alterTableRenameColumnPattern = regexp.MustCompile(
	`(?is)alter\s+table(?:\s+if\s+exists)?\s+([a-zA-Z0-9_."]+)\s+rename\s+column\s+([a-zA-Z0-9_"]+)\s+to\s+([a-zA-Z0-9_"]+)`,
)

var sqlCreateIndexPattern = regexp.MustCompile(
	`(?is)create\s+(?:unique\s+)?index(?:\s+if\s+not\s+exists)?\s+[a-zA-Z0-9_."]+\s+on\s+[a-zA-Z0-9_."]+(?:\s+using\s+[a-zA-Z0-9_]+)?\s*\(([^)]*)\)`,
)

var sqlUniqueKeyPattern = regexp.MustCompile(
	`(?is)(?:constraint\s+[a-zA-Z0-9_."]+\s+)?unique\s*\(([^)]*)\)`,
)

var sqlPrimaryKeyPattern = regexp.MustCompile(
	`(?is)(?:constraint\s+[a-zA-Z0-9_."]+\s+)?primary\s+key\s*\(([^)]*)\)`,
)

var pythonCreateIndexPattern = regexp.MustCompile(`(?is)create_index\s*\(\s*\[([^]]+)\]`)
var pythonIndexKeyPattern = regexp.MustCompile(`\(\s*["']([^"']+)["']\s*,`)

var indexCreationMarkers = []string{
	"create index", "create unique index", "create_index(", "create_indexes(",
	"indexes().createone", "indexes().createmany", "setkeys(", "mongo.indexmodel",
}

var indexUsageMarkers = []string{
	".find(", ".find_one(", ".findone(", ".aggregate(", ".sort(", "findoptions", "setfilter(",
	"setprojection(", "sethint(", "select ", " where ", " order by ", " group by ",
}

func AuditIndexes(repoRoot string) (IndexAuditReport, error) {
	declarations, err := discoverIndexDeclarations(repoRoot)
	if err != nil {
		return IndexAuditReport{}, err
	}
	filesByService, err := loadProductionSources(repoRoot)
	if err != nil {
		return IndexAuditReport{}, err
	}
	expandedByService := make(map[string][]expandedSourceScope, len(filesByService))
	for service, files := range filesByService {
		expandedByService[service] = expandedSourceScopes(files)
	}
	report := IndexAuditReport{Declarations: len(declarations)}
	for _, declaration := range declarations {
		files := append([]sourceFile(nil), filesByService[declaration.Service]...)
		files = append(files, filesByService[sharedProductionSourceKey]...)
		keyAliases := storageKeyAliases(files, declaration.StoreName)
		objectPrefix := filepath.ToSlash(filepath.Join(
			"internal", declaration.Context, declaration.Object,
		)) + "/"
		created := mongoAutomaticIDIndex(declaration) || generatedIndexCreationIsWired(declaration, files)
		used := declaration.Unique || declaration.Lifecycle
		expandedScopes := append([]expandedSourceScope(nil), expandedByService[declaration.Service]...)
		expandedScopes = append(expandedScopes, expandedByService[sharedProductionSourceKey]...)
		for _, expanded := range expandedScopes {
			insideObject := strings.Contains(expanded.path, "/"+objectPrefix)
			scope := expanded.scope
			if !created &&
				hasSemanticIndexKeySet(scope.indexKeySets, declaration.Keys, declaration.KeyOrderAuthored, keyAliases) &&
				(insideObject || hasSemanticToken(scope.tokens, declaration.StoreName)) {
				created = true
			}
			if !used && scope.queriesStore &&
				(insideObject || hasSemanticToken(scope.tokens, declaration.StoreName)) &&
				hasSemanticKeysWithAliases(scope.tokens, declaration.Keys, keyAliases) {
				used = true
			}
		}
		if created {
			report.Created++
		} else {
			report.Issues = append(report.Issues, newIndexIssue(
				"CONTRACT.STORAGE.INDEX_CREATION_MISSING",
				declaration,
				"no production Go SetKeys/IndexModel, SQL CREATE INDEX, or Python create_index site matches the declared semantic key set",
			))
		}
		if used {
			report.Used++
		} else {
			report.Issues = append(report.Issues, newIndexIssue(
				"CONTRACT.STORAGE.INDEX_USAGE_MISSING",
				declaration,
				"no object-owned production query/sort/aggregation uses the declared semantic key set",
			))
		}
	}
	sort.Slice(report.Issues, func(i, j int) bool {
		left, right := report.Issues[i], report.Issues[j]
		if left.SourcePath != right.SourcePath {
			return left.SourcePath < right.SourcePath
		}
		if left.StoreName != right.StoreName {
			return left.StoreName < right.StoreName
		}
		if left.IndexName != right.IndexName {
			return left.IndexName < right.IndexName
		}
		return left.Code < right.Code
	})
	return report, nil
}

func newIndexIssue(code string, declaration IndexDeclaration, explanation string) IndexAuditIssue {
	return IndexAuditIssue{
		Code:        code,
		SourcePath:  declaration.SourcePath,
		StoreName:   declaration.StoreName,
		IndexName:   declaration.IndexName,
		Keys:        append([]string(nil), declaration.Keys...),
		Explanation: explanation,
	}
}

func discoverIndexDeclarations(repoRoot string) ([]IndexDeclaration, error) {
	serviceRoot := filepath.Join(repoRoot, "quwoquan_service")
	var result []IndexDeclaration
	for _, area := range []string{"services", "control-plane"} {
		areaRoot := filepath.Join(serviceRoot, area)
		err := filepath.WalkDir(areaRoot, func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() || entry.Name() != "storage.yaml" {
				return nil
			}
			parts, ownerErr := storageOwnerSegments(areaRoot, path)
			if ownerErr != nil {
				return ownerErr
			}
			document, loadErr := LoadOptional(path)
			if loadErr != nil {
				return loadErr
			}
			if document == nil {
				return nil
			}
			relative, _ := filepath.Rel(repoRoot, path)
			appendDeclaration := func(kind, store, name string, keys []string, keyOrderAuthored, unique, lifecycle, generatedCreation bool) {
				if len(keys) == 0 {
					return
				}
				result = append(result, IndexDeclaration{
					SourcePath: filepath.ToSlash(relative), Service: parts[0], Context: parts[1], Object: parts[2],
					StoreKind: kind, StoreName: store, IndexName: name,
					Keys: append([]string(nil), keys...), KeyOrderAuthored: keyOrderAuthored,
					Unique: unique, Lifecycle: lifecycle,
					GeneratedCreation: generatedCreation,
				})
			}
			codegenEnabled := document.Codegen != nil && document.Codegen.Enabled && !document.Codegen.EventsOnly
			skippedTables := map[string]struct{}{}
			if document.Codegen != nil {
				for _, table := range document.Codegen.MigrationSkipTables {
					skippedTables[table] = struct{}{}
				}
			}
			for store, table := range document.Tables {
				_, migrationSkipped := skippedTables[store]
				generatedCreation := codegenEnabled && !migrationSkipped
				for _, index := range table.Indexes {
					appendDeclaration("table", store, index.Name, index.Columns, true, index.Unique, false, generatedCreation)
				}
				for _, index := range table.UniqueConstraints {
					appendDeclaration("table", store, index.Name, index.Columns, true, true, false, generatedCreation)
				}
				for _, index := range table.SearchIndexes {
					appendDeclaration("table", store, index.Name, index.Columns, true, false, false, generatedCreation)
				}
			}
			for store, collection := range document.Collections {
				for _, index := range collection.Indexes {
					keys := index.KeyOrder
					if len(keys) == 0 {
						keys = sortedMapKeys(index.Keys)
					}
					if len(keys) == 0 {
						keys = append([]string(nil), index.Fields...)
					}
					if len(keys) == 0 && strings.TrimSpace(index.Field) != "" {
						keys = []string{index.Field}
					}
					appendDeclaration(
						"collection", store, index.Name, keys, len(index.KeyOrder) > 0, index.Unique,
						index.ExpireAfterSeconds != nil,
						codegenEnabled && len(index.Keys) > 0 && len(index.PartialFilter) == 0,
					)
				}
			}
			return nil
		})
		if err != nil && !os.IsNotExist(err) {
			return nil, err
		}
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].SourcePath != result[j].SourcePath {
			return result[i].SourcePath < result[j].SourcePath
		}
		if result[i].StoreName != result[j].StoreName {
			return result[i].StoreName < result[j].StoreName
		}
		return result[i].IndexName < result[j].IndexName
	})
	return result, nil
}

func storageOwnerSegments(areaRoot, storagePath string) ([3]string, error) {
	relative, err := filepath.Rel(areaRoot, storagePath)
	if err != nil {
		return [3]string{}, err
	}
	parts := strings.Split(filepath.ToSlash(relative), "/")
	if len(parts) != 5 || parts[1] != "contracts" || parts[4] != "storage.yaml" {
		return [3]string{}, fmt.Errorf("%s: storage path must be <service>/contracts/<context>/<object>/storage.yaml", storagePath)
	}
	return [3]string{parts[0], parts[2], parts[3]}, nil
}

func loadProductionSources(repoRoot string) (map[string][]sourceFile, error) {
	result := map[string][]sourceFile{}
	serviceRoot := filepath.Join(repoRoot, "quwoquan_service")
	loadTree := func(key, root, relativeRoot string) error {
		return filepath.WalkDir(root, func(path string, item fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if item.IsDir() {
				switch item.Name() {
				case "contracts", "generated", "tests", "test", "build", ".qwq_output", "vendor":
					if path != root {
						return filepath.SkipDir
					}
				}
				return nil
			}
			if strings.HasSuffix(item.Name(), "_test.go") {
				return nil
			}
			extension := strings.ToLower(filepath.Ext(path))
			if extension != ".go" && extension != ".py" && extension != ".sql" {
				return nil
			}
			data, readErr := os.ReadFile(path)
			if readErr != nil {
				return readErr
			}
			relative, _ := filepath.Rel(relativeRoot, path)
			text := strings.ToLower(string(data))
			scopes, scopeErr := productionSourceScopes(path, data)
			if scopeErr != nil {
				return scopeErr
			}
			result[key] = append(result[key], sourceFile{
				path: filepath.ToSlash(filepath.Join("/", relative)), text: text, tokens: semanticTokens(text), scopes: scopes,
			})
			return nil
		})
	}
	for _, area := range []string{"services", "control-plane"} {
		areaRoot := filepath.Join(serviceRoot, area)
		entries, err := os.ReadDir(areaRoot)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, err
		}
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			root := filepath.Join(areaRoot, entry.Name())
			err := loadTree(entry.Name(), root, root)
			if err != nil {
				return nil, err
			}
		}
	}
	for _, sharedRoot := range []string{
		filepath.Join(serviceRoot, "internal", "platform"),
		filepath.Join(serviceRoot, "runtime"),
	} {
		if err := loadTree(sharedProductionSourceKey, sharedRoot, serviceRoot); err != nil && !os.IsNotExist(err) {
			return nil, err
		}
	}
	return result, nil
}

const sharedProductionSourceKey = "_shared"

func productionSourceScopes(path string, data []byte) ([]sourceScope, error) {
	extension := strings.ToLower(filepath.Ext(path))
	switch extension {
	case ".go":
		return goSourceScopes(path, data)
	case ".sql":
		return delimitedSourceScopes(string(data), ";"), nil
	case ".py":
		return pythonSourceScopes(string(data)), nil
	default:
		return nil, nil
	}
}

type expandedSourceScope struct {
	path  string
	scope sourceScope
}

func expandedSourceScopes(files []sourceFile) []expandedSourceScope {
	byDirectory := map[string][]sourceFile{}
	for _, file := range files {
		byDirectory[filepath.Dir(file.path)] = append(byDirectory[filepath.Dir(file.path)], file)
	}
	var result []expandedSourceScope
	for _, directoryFiles := range byDirectory {
		var scopes []sourceScope
		var paths []string
		storeBindings := map[string]map[string]struct{}{}
		for _, file := range directoryFiles {
			for _, scope := range file.scopes {
				scopes = append(scopes, scope)
				paths = append(paths, file.path)
				for field, stores := range scope.storeBindings {
					if storeBindings[field] == nil {
						storeBindings[field] = map[string]struct{}{}
					}
					mergeTokens(storeBindings[field], stores)
				}
			}
		}
		byName := map[string][]int{}
		for index, scope := range scopes {
			name := canonicalStorageKey(scope.name)
			if name != "" {
				byName[name] = append(byName[name], index)
			}
		}
		for index := range scopes {
			expanded := expandSourceScope(index, scopes, byName)
			for field, stores := range storeBindings {
				if _, referenced := expanded.tokens[field]; referenced {
					mergeTokens(expanded.tokens, stores)
				}
			}
			result = append(result, expandedSourceScope{
				path:  paths[index],
				scope: expanded,
			})
		}
	}
	return result
}

func expandSourceScope(start int, scopes []sourceScope, byName map[string][]int) sourceScope {
	scope := scopes[start]
	expanded := sourceScope{
		name:          scope.name,
		text:          scope.text,
		tokens:        map[string]struct{}{},
		references:    map[string]struct{}{},
		storeBindings: map[string]map[string]struct{}{},
	}
	visited := map[int]struct{}{}
	queue := []int{start}
	for len(queue) > 0 {
		index := queue[0]
		queue = queue[1:]
		if _, seen := visited[index]; seen {
			continue
		}
		visited[index] = struct{}{}
		current := scopes[index]
		mergeTokens(expanded.tokens, current.tokens)
		mergeTokens(expanded.references, current.references)
		expanded.createsIndex = expanded.createsIndex || current.createsIndex
		expanded.queriesStore = expanded.queriesStore || current.queriesStore
		expanded.ensureIndexes = expanded.ensureIndexes || current.ensureIndexes
		expanded.indexKeySets = append(expanded.indexKeySets, current.indexKeySets...)
		for reference := range current.references {
			queue = append(queue, byName[reference]...)
		}
	}
	return expanded
}

func mergeTokens(target, source map[string]struct{}) {
	for token := range source {
		target[token] = struct{}{}
	}
}

func delimitedSourceScopes(source, delimiter string) []sourceScope {
	parts := strings.Split(source, delimiter)
	result := make([]sourceScope, 0, len(parts))
	for _, part := range parts {
		text := strings.ToLower(strings.TrimSpace(part))
		if text == "" {
			continue
		}
		result = append(result, sourceScope{
			text:         text,
			tokens:       semanticTokens(text),
			createsIndex: hasAnyMarker(text, indexCreationMarkers),
			queriesStore: hasAnyMarker(text, indexUsageMarkers),
			indexKeySets: extractTextIndexKeySets(text),
		})
	}
	return result
}

func pythonSourceScopes(source string) []sourceScope {
	// Python storage adapters keep each query/index operation in a top-level
	// function or method. Split on def/async def boundaries so an unrelated
	// query elsewhere in the file cannot lend keys to an index declaration.
	lines := strings.Split(source, "\n")
	var result []sourceScope
	var current []string
	flush := func() {
		text := strings.ToLower(strings.TrimSpace(strings.Join(current, "\n")))
		if text == "" {
			return
		}
		result = append(result, sourceScope{
			text:         text,
			tokens:       semanticTokens(text),
			createsIndex: hasAnyMarker(text, indexCreationMarkers),
			queriesStore: hasAnyMarker(text, indexUsageMarkers),
			indexKeySets: extractTextIndexKeySets(text),
		})
	}
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if (strings.HasPrefix(trimmed, "def ") || strings.HasPrefix(trimmed, "async def ")) &&
			(strings.HasSuffix(trimmed, ":") || strings.Contains(trimmed, ") ->")) {
			flush()
			current = current[:0]
		}
		current = append(current, line)
	}
	flush()
	return result
}

func generatedIndexCreationIsWired(declaration IndexDeclaration, files []sourceFile) bool {
	if !declaration.GeneratedCreation {
		return false
	}
	objectPrefix := filepath.ToSlash(filepath.Join("internal", declaration.Context, declaration.Object)) + "/"
	generatedImport := filepath.ToSlash(filepath.Join("generated", declaration.Context, declaration.Object, "persistence"))
	constructorNames := map[string]struct{}{}
	for _, file := range files {
		if !strings.Contains(file.path, "/"+objectPrefix) || !strings.Contains(file.text, generatedImport) {
			continue
		}
		for _, scope := range file.scopes {
			if strings.HasPrefix(strings.ToLower(scope.name), "new") && strings.Contains(scope.text, "storebase") {
				constructorNames[canonicalStorageKey(scope.name)] = struct{}{}
			}
		}
	}
	if len(constructorNames) == 0 {
		return false
	}
	for _, file := range files {
		for _, scope := range file.scopes {
			if !scope.ensureIndexes {
				continue
			}
			for constructorName := range constructorNames {
				if _, ok := scope.tokens[constructorName]; ok {
					return true
				}
			}
		}
	}
	return false
}

func mongoAutomaticIDIndex(declaration IndexDeclaration) bool {
	return declaration.StoreKind == "collection" && len(declaration.Keys) == 1 &&
		strings.TrimSpace(declaration.Keys[0]) == "_id"
}

func semanticTokens(text string) map[string]struct{} {
	result := map[string]struct{}{}
	for _, token := range sourceTokenPattern.FindAllString(text, -1) {
		result[canonicalStorageKey(token)] = struct{}{}
		for _, part := range strings.Split(token, ".") {
			if canonical := canonicalStorageKey(part); canonical != "" {
				result[canonical] = struct{}{}
			}
		}
	}
	return result
}

func canonicalStorageKey(value string) string {
	parts := strings.Fields(strings.TrimSpace(value))
	if len(parts) > 1 {
		direction := strings.ToLower(parts[len(parts)-1])
		if direction == "asc" || direction == "desc" {
			value = strings.Join(parts[:len(parts)-1], " ")
		}
	}
	var builder strings.Builder
	for _, character := range strings.ToLower(strings.TrimSpace(value)) {
		if character >= 'a' && character <= 'z' || character >= '0' && character <= '9' {
			builder.WriteRune(character)
		}
	}
	return builder.String()
}

func hasSemanticToken(tokens map[string]struct{}, value string) bool {
	_, exists := tokens[canonicalStorageKey(value)]
	return exists
}

func hasSemanticKeys(tokens map[string]struct{}, keys []string) bool {
	return hasSemanticKeysWithAliases(tokens, keys, nil)
}

func hasSemanticKeysWithAliases(
	tokens map[string]struct{},
	keys []string,
	aliases map[string]map[string]struct{},
) bool {
	if len(keys) == 0 {
		return false
	}
	for _, key := range keys {
		canonical := canonicalStorageKey(key)
		if _, exists := tokens[canonical]; exists {
			continue
		}
		matchedAlias := false
		for alias := range aliases[canonical] {
			if _, exists := tokens[alias]; exists {
				matchedAlias = true
				break
			}
		}
		if !matchedAlias {
			return false
		}
	}
	return true
}

func hasSemanticIndexKeySet(
	candidates [][]string,
	declared []string,
	ordered bool,
	aliases map[string]map[string]struct{},
) bool {
	for _, candidate := range candidates {
		if len(candidate) != len(declared) {
			continue
		}
		matches := orderedIndexKeysMatch(candidate, declared, ordered, aliases)
		if matches {
			return true
		}
	}
	return false
}

func orderedIndexKeysMatch(
	candidate, declared []string,
	ordered bool,
	aliases map[string]map[string]struct{},
) bool {
	if ordered {
		for index, key := range declared {
			if !storageKeyMatches(candidate[index], key, aliases) {
				return false
			}
		}
		return true
	}
	used := make([]bool, len(candidate))
	for _, key := range declared {
		matched := false
		for index, candidateKey := range candidate {
			if !used[index] && storageKeyMatches(candidateKey, key, aliases) {
				used[index] = true
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}
	return true
}

func storageKeyMatches(candidate, declared string, aliases map[string]map[string]struct{}) bool {
	declaredKey := canonicalStorageKey(declared)
	candidateKey := canonicalStorageKey(candidate)
	if candidateKey == declaredKey {
		return true
	}
	_, aliased := aliases[declaredKey][candidateKey]
	return aliased
}

func extractTextIndexKeySets(text string) [][]string {
	var result [][]string
	for _, pattern := range []*regexp.Regexp{sqlCreateIndexPattern, sqlUniqueKeyPattern, sqlPrimaryKeyPattern} {
		for _, match := range pattern.FindAllStringSubmatch(text, -1) {
			if len(match) != 2 {
				continue
			}
			var keys []string
			for _, expression := range strings.Split(match[1], ",") {
				if key := storageIndexExpressionKey(expression); key != "" {
					keys = append(keys, key)
				}
			}
			if len(keys) > 0 {
				result = append(result, keys)
			}
		}
	}
	for _, match := range pythonCreateIndexPattern.FindAllStringSubmatch(text, -1) {
		if len(match) != 2 {
			continue
		}
		var keys []string
		for _, keyMatch := range pythonIndexKeyPattern.FindAllStringSubmatch(match[1], -1) {
			if len(keyMatch) == 2 {
				keys = append(keys, keyMatch[1])
			}
		}
		if len(keys) > 0 {
			result = append(result, keys)
		}
	}
	return result
}

func storageIndexExpressionKey(expression string) string {
	expression = strings.TrimSpace(strings.Trim(expression, "\"`"))
	fields := strings.Fields(expression)
	if len(fields) == 0 {
		return ""
	}
	return strings.Trim(fields[0], "\"`()")
}

func storageKeyAliases(files []sourceFile, storeName string) map[string]map[string]struct{} {
	store := canonicalStorageKey(storeName)
	direct := map[string]map[string]struct{}{}
	for _, file := range files {
		if filepath.Ext(file.path) != ".sql" {
			continue
		}
		for _, match := range alterTableRenameColumnPattern.FindAllStringSubmatch(file.text, -1) {
			if len(match) != 4 || canonicalStorageKey(match[1]) != store {
				continue
			}
			oldKey := canonicalStorageKey(match[2])
			newKey := canonicalStorageKey(match[3])
			if oldKey == "" || newKey == "" {
				continue
			}
			if direct[newKey] == nil {
				direct[newKey] = map[string]struct{}{}
			}
			direct[newKey][oldKey] = struct{}{}
		}
	}
	// Follow sequential hard-cutover renames so a historical creation remains
	// valid after more than one canonical vocabulary migration.
	for target := range direct {
		queue := make([]string, 0, len(direct[target]))
		for alias := range direct[target] {
			queue = append(queue, alias)
		}
		for len(queue) > 0 {
			alias := queue[0]
			queue = queue[1:]
			for predecessor := range direct[alias] {
				if _, seen := direct[target][predecessor]; seen {
					continue
				}
				direct[target][predecessor] = struct{}{}
				queue = append(queue, predecessor)
			}
		}
	}
	return direct
}

func hasAnyMarker(text string, markers []string) bool {
	for _, marker := range markers {
		if strings.Contains(text, marker) {
			return true
		}
	}
	return false
}

func sortedMapKeys(values map[string]any) []string {
	result := make([]string, 0, len(values))
	for key := range values {
		result = append(result, key)
	}
	sort.Strings(result)
	return result
}
