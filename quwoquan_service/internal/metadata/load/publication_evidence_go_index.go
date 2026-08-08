package load

import (
	goast "go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// serviceScan 承载解析阶段的中间事实。
type serviceScan struct {
	functions                 []functionRecord
	bindings                  map[string]*packageBindings
	constructorCallArgs       map[string]map[int]map[string]struct{}
	constructorStringCallArgs map[constructorCallKey]map[int]map[string]struct{}
	relationResolvers         map[methodRelationKey][]conditionalRelationResolver
	txInvokedMethods          map[string]struct{}
	declaredFunctions         map[string]struct{}
	externalCandidates        []externalCandidate
	sharedPackageCalls        map[string]struct{}
	serviceDir                string
}

type externalCandidate struct {
	relation string
	callee   string
	file     string
	// external 为 true 表示被调方来自本服务之外的包，无需再按函数名回查。函数名回查会
	// 误判：`pgoutbox.NewDispatcher` 与本服务自己的 `NewDispatcher` 同名但不是同一个函数。
	external bool
}

func (scan *serviceScan) packageBindings(dir string) *packageBindings {
	bindings := scan.bindings[dir]
	if bindings == nil {
		bindings = &packageBindings{
			fieldRelations:              map[string]map[string]struct{}{},
			fieldConstructorParams:      map[string][]constructorParam{},
			fieldValues:                 map[receiverFieldKey]map[string]struct{}{},
			fieldValueConstructorParams: map[receiverFieldKey][]scalarConstructorParam{},
			localsByFunction:            map[string]map[string]string{},
			constants:                   map[string]string{},
		}
		scan.bindings[dir] = bindings
	}
	return bindings
}

func isNonProductionDir(name string) bool {
	if name == "tests" || name == "test" {
		return true
	}
	_, nonProduction := nonProductionSegments[name]
	return nonProduction
}

func isProductionSourceFile(path string) bool {
	if strings.HasSuffix(path, "_test.go") {
		return false
	}
	_, ok := cloudSourceSuffixes[strings.ToLower(filepath.Ext(path))]
	return ok
}

func (scan *serviceScan) indexGoFile(index *serviceWriteIndex, path string, data []byte) {
	fileSet := token.NewFileSet()
	file, err := parser.ParseFile(fileSet, path, data, parser.SkipObjectResolution)
	if err != nil {
		return
	}
	dir := filepath.Dir(path)
	bindings := scan.packageBindings(dir)
	imports := importPathsByName(file)
	// 文件级 const/var 字符串是同一份静态事实：`const outboxCollection = "gathering_outbox"`
	// 必须能解析回字面量，否则 Go 里最常见的一种表名写法整类漏判。
	goast.Inspect(file, func(node goast.Node) bool {
		spec, ok := node.(*goast.ValueSpec)
		if !ok {
			return true
		}
		for position, value := range spec.Values {
			literal, isLiteral := value.(*goast.BasicLit)
			if !isLiteral || literal.Kind != token.STRING || position >= len(spec.Names) {
				continue
			}
			bindings.constants[spec.Names[position].Name] = trimStringLiteral(literal.Value)
		}
		return true
	})
	index.indexRelationBindings(dir, file, bindings.constants)
	scan.indexExternalCandidates(path, file, bindings.constants)
	scan.indexCompositionCalls(index, path, file, bindings.constants)
	for _, declaration := range file.Decls {
		function, ok := declaration.(*goast.FuncDecl)
		if !ok || function.Body == nil {
			continue
		}
		scan.indexFunction(path, dir, bindings, imports, function)
	}
}

const (
	firstPartyPlatformImportPrefix = "quwoquan_service/internal/platform/"
	postgresOutboxImportPath       = "quwoquan_service/internal/platform/pgoutbox"
)

// indexCompositionCalls 只认真实 AST call 与解析后的 import identity：
//
//   - 被实际调用的第一方 shared platform package 才进入后续扫描；
//   - cmd composition root 对本服务对象 relay constructor 的调用，绑定到该对象 scope；
//   - `pgoutbox.NewDispatcher(..., relation)` 是 canonical PostgreSQL outbox 投递装配，
//     具体 relation 只存在于调用点，因此在此绑定为 delivery evidence。
//
// 同名本地函数、其它 import 的 NewDispatcher、注释与字符串都不会命中。
func (scan *serviceScan) indexCompositionCalls(
	index *serviceWriteIndex,
	path string,
	file *goast.File,
	constants map[string]string,
) {
	imports := importPathsByName(file)
	for _, declaration := range file.Decls {
		function, ok := declaration.(*goast.FuncDecl)
		if !ok || function.Body == nil {
			continue
		}
		goast.Inspect(function.Body, func(node goast.Node) bool {
			call, isCall := node.(*goast.CallExpr)
			if !isCall {
				return true
			}
			selector, isSelector := call.Fun.(*goast.SelectorExpr)
			if !isSelector {
				return true
			}
			qualifier, isIdentifier := selector.X.(*goast.Ident)
			if !isIdentifier {
				return true
			}
			importPath, imported := imports[qualifier.Name]
			if !imported {
				return true
			}
			if strings.HasPrefix(importPath, firstPartyPlatformImportPrefix) {
				scan.sharedPackageCalls[importPath] = struct{}{}
			}
			if scope := composedObjectRelayScope(path, importPath, selector.Sel.Name); scope != "" {
				index.composedDeliveryRelayScopes[scope] = struct{}{}
			}
			if importPath != postgresOutboxImportPath || selector.Sel.Name != "NewDispatcher" {
				return true
			}
			for _, argument := range call.Args {
				relation, resolved := stringArgument(argument, constants)
				if !resolved || !relationNamePattern.MatchString(relation) {
					continue
				}
				index.compositionDeliveries[relation] = appendSite(
					index.compositionDeliveries[relation],
					writeSite{file: path, function: function.Name.Name},
				)
			}
			return true
		})
	}
}

// composedObjectRelayScope 将 cmd 里的 import-qualified relay constructor 解析回同一服务
// 的 canonical object scope。只接受 `New*Relay*` 的真实调用和本服务 private internal import；
// 字符串、注释、兄弟服务私有包以及 internal 内部自构造都不能形成生产装配证据。
func composedObjectRelayScope(path string, importPath string, constructor string) string {
	if !strings.HasPrefix(constructor, "New") || !strings.Contains(constructor, "Relay") {
		return ""
	}
	cleanPath := filepath.ToSlash(filepath.Clean(path))
	marker := "/cmd/"
	position := strings.Index(cleanPath, marker)
	if position < 0 {
		return ""
	}
	serviceRoot := cleanPath[:position]
	rootParent := filepath.Base(filepath.Dir(filepath.FromSlash(serviceRoot)))
	if rootParent != "services" && rootParent != "control-plane" {
		return ""
	}
	importMarker := "/internal/"
	importPosition := strings.Index(importPath, importMarker)
	if importPosition < 0 {
		return ""
	}
	wantImportRoot := "quwoquan_service/" + rootParent + "/" + filepath.Base(filepath.FromSlash(serviceRoot))
	if importPath[:importPosition] != wantImportRoot {
		return ""
	}
	implementationPath := filepath.Join(
		filepath.FromSlash(serviceRoot),
		filepath.FromSlash(strings.TrimPrefix(importPath[importPosition:], "/")),
		"package.go",
	)
	return publicationImplementationScope(implementationPath)
}

// indexSharedPlatformPackage 将真实 composition call 指向的单个第一方 package 纳入与服务
// 相同的 AST 索引。路径由 import identity 推导并强制留在 moduleRoot/internal/platform 下；
// 不递归吞并未被装配的兄弟 package。
func (scan *serviceScan) indexSharedPlatformPackage(
	index *serviceWriteIndex,
	moduleRoot string,
	importPath string,
) error {
	if !strings.HasPrefix(importPath, firstPartyPlatformImportPrefix) {
		return nil
	}
	relative := strings.TrimPrefix(importPath, "quwoquan_service/")
	packageDir := filepath.Clean(filepath.Join(moduleRoot, filepath.FromSlash(relative)))
	platformRoot := filepath.Clean(filepath.Join(moduleRoot, "internal", "platform"))
	if packageDir == platformRoot || !strings.HasPrefix(
		packageDir, platformRoot+string(filepath.Separator),
	) {
		return nil
	}
	if scope := publicationImplementationScope(filepath.Join(packageDir, "package.go")); scope != "" {
		index.composedSharedScopes[scope] = struct{}{}
	}
	entries, err := os.ReadDir(packageDir)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		path := filepath.Join(packageDir, entry.Name())
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		scan.indexGoFile(index, path, data)
	}
	return nil
}

// indexRelationBindings 记录关系名的绑定位置，用途只有一个：区分「跟不动」与「不存在」。
func (index *serviceWriteIndex) indexRelationBindings(
	dir string,
	file *goast.File,
	constants map[string]string,
) {
	record := func(relation string) {
		for _, existing := range index.relationBindings[relation] {
			if existing == dir {
				return
			}
		}
		index.relationBindings[relation] = append(index.relationBindings[relation], dir)
	}
	for _, value := range constants {
		if relationNamePattern.MatchString(value) {
			record(value)
			continue
		}
		for _, relation := range sqlRelations(value) {
			record(relation)
		}
	}
	goast.Inspect(file, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		bindingCall := storageHandleBindingCalls[callTargetName(call)] ||
			isConstructorName(callTargetName(call))
		for _, argument := range call.Args {
			value, resolved := stringArgument(argument, constants)
			if !resolved {
				continue
			}
			if bindingCall && relationNamePattern.MatchString(value) {
				record(value)
				continue
			}
			for _, relation := range sqlRelations(value) {
				record(relation)
			}
		}
		return true
	})
}

// indexExternalCandidates 记录「关系名被当实参传给某个函数」这条边，等全服务函数名收齐后
// 再判断被调方是否在扫描范围内。
func (scan *serviceScan) indexExternalCandidates(
	path string,
	file *goast.File,
	constants map[string]string,
) {
	imports := importPathsByName(file)
	goast.Inspect(file, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		callee := callTargetName(call)
		if callee == "" || storageHandleBindingCalls[callee] {
			return true
		}
		external := scan.callTargetsOutsideService(call, imports)
		for _, argument := range call.Args {
			value, resolved := stringArgument(argument, constants)
			if !resolved || !relationNamePattern.MatchString(value) {
				continue
			}
			scan.externalCandidates = append(scan.externalCandidates, externalCandidate{
				relation: value, callee: callee, file: path, external: external,
			})
		}
		return true
	})
}

// callTargetsOutsideService 判断 `pkg.Fn(...)` 的 pkg 是否来自本服务之外的导入路径。
func (scan *serviceScan) callTargetsOutsideService(
	call *goast.CallExpr,
	imports map[string]string,
) bool {
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok {
		return false
	}
	qualifier, isIdent := selector.X.(*goast.Ident)
	if !isIdent {
		return false
	}
	path, imported := imports[qualifier.Name]
	if !imported {
		return false
	}
	return !strings.Contains(path, "/"+scan.serviceDir+"/")
}

func importPathsByName(file *goast.File) map[string]string {
	paths := map[string]string{}
	for _, entry := range file.Imports {
		if entry.Path == nil {
			continue
		}
		path := trimStringLiteral(entry.Path.Value)
		name := path
		if index := strings.LastIndex(path, "/"); index >= 0 {
			name = path[index+1:]
		}
		if entry.Name != nil {
			name = entry.Name.Name
		}
		paths[name] = path
	}
	return paths
}

// indexFunction 抽出单个函数的写入/读取目标与事务性来源，目标解析推迟到 resolve。
func (scan *serviceScan) indexFunction(
	path string,
	dir string,
	bindings *packageBindings,
	imports map[string]string,
	function *goast.FuncDecl,
) {
	handles := map[string]struct{}{}
	collectTransactionHandles(function.Type, handles)
	locals := map[string]string{}
	// 字段绑定在**所有**函数里收集：投递侧常把句柄放进函数内的匿名结构体切片
	// （`{name: "GatheringParticipation", collection: db.Collection("gathering_participation_outbox")}`），
	// 只认构造函数会漏掉整类投递实现。形参位置绑定仍只对构造函数有效，因为只有构造调用
	// 点会传入集合名。
	paramIndex := map[string]int{}
	if isConstructorName(function.Name.Name) {
		paramIndex = parameterIndexes(function.Type)
	}
	goast.Inspect(function.Body, func(node goast.Node) bool {
		switch typed := node.(type) {
		case *goast.FuncLit:
			collectTransactionHandles(typed.Type, handles)
		case *goast.AssignStmt:
			collectTransactionAssignments(typed, handles)
			collectLocalRelationBindings(typed, locals, bindings.constants)
			scan.collectFieldAssignments(typed, bindings, paramIndex, function.Name.Name)
		case *goast.CompositeLit:
			scan.collectFieldComposites(typed, bindings, paramIndex, function.Name.Name)
			scan.collectConstructorValueComposite(
				dir, typed, bindings, paramIndex, function.Name.Name,
			)
		case *goast.CallExpr:
			collectTransactionClosureHandles(typed, handles)
			scan.collectConstructorCallArgs(typed, dir, imports, bindings.constants)
		}
		return true
	})
	record := functionRecord{
		file:            path,
		packageDir:      dir,
		name:            function.Name.Name,
		parameters:      parameterNames(function.Type),
		transactionVars: sortedSetKeys(handles),
		holdsHandle:     functionUsesTransactionHandle(function.Body, handles),
		dynamicSQLWrites: collectDynamicTransactionalSQLWrites(
			dir, function, handles, bindings.constants, imports,
		),
	}
	scan.collectConditionalRelationResolvers(dir, function, bindings.constants)
	collectAccessTargets(function.Body, handles, &record, bindings.constants)
	bindings.localsByFunction[function.Name.Name] = locals
	scan.declaredFunctions[function.Name.Name] = struct{}{}
	scan.functions = append(scan.functions, record)
	for _, callee := range record.handleCallees {
		scan.txInvokedMethods[callee] = struct{}{}
	}
}

func parameterNames(signature *goast.FuncType) []string {
	if signature == nil || signature.Params == nil {
		return nil
	}
	names := []string{}
	for _, field := range signature.Params.List {
		if len(field.Names) == 0 {
			names = append(names, "")
			continue
		}
		for _, name := range field.Names {
			names = append(names, name.Name)
		}
	}
	return names
}

func sortedSetKeys(values map[string]struct{}) []string {
	keys := make([]string, 0, len(values))
	for value := range values {
		keys = append(keys, value)
	}
	sort.Strings(keys)
	return keys
}

func parameterIndexes(signature *goast.FuncType) map[string]int {
	indexes := map[string]int{}
	if signature == nil || signature.Params == nil {
		return indexes
	}
	position := 0
	for _, field := range signature.Params.List {
		if len(field.Names) == 0 {
			position++
			continue
		}
		for _, name := range field.Names {
			indexes[name.Name] = position
			position++
		}
	}
	return indexes
}

// collectFieldComposites 解析 `&Store{outbox: db.Collection("content_outbox")}` 形态。
func (scan *serviceScan) collectFieldComposites(
	literal *goast.CompositeLit,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	for _, element := range literal.Elts {
		pair, ok := element.(*goast.KeyValueExpr)
		if !ok {
			continue
		}
		key, isIdent := pair.Key.(*goast.Ident)
		if !isIdent {
			continue
		}
		bindFieldValue(key.Name, pair.Value, bindings, paramIndex, constructor)
	}
}

// collectConstructorValueComposite records only direct scalar constructor propagation:
// `func NewStore(..., scope string) *Store { return &Store{scope: scope} }`.
// It deliberately does not treat that scalar as a relation. A relation is selected later only
// when a receiver method contains an exact field-switch/case-return mapping.
func (scan *serviceScan) collectConstructorValueComposite(
	dir string,
	literal *goast.CompositeLit,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	if !isConstructorName(constructor) || len(paramIndex) == 0 {
		return
	}
	receiverType := namedTypeExpression(literal.Type)
	if receiverType == "" {
		return
	}
	for _, element := range literal.Elts {
		pair, ok := element.(*goast.KeyValueExpr)
		if !ok {
			continue
		}
		field, fieldOK := pair.Key.(*goast.Ident)
		value, valueOK := pair.Value.(*goast.Ident)
		if !fieldOK || !valueOK {
			continue
		}
		position, bound := paramIndex[value.Name]
		if !bound {
			continue
		}
		key := receiverFieldKey{receiverType: receiverType, field: field.Name}
		bindings.fieldValueConstructorParams[key] = append(
			bindings.fieldValueConstructorParams[key],
			scalarConstructorParam{
				constructor: constructorCallKey{packageDir: dir, name: constructor},
				index:       position,
			},
		)
	}
}

func namedTypeExpression(expression goast.Expr) string {
	switch typed := expression.(type) {
	case *goast.Ident:
		return typed.Name
	case *goast.StarExpr:
		return namedTypeExpression(typed.X)
	case *goast.IndexExpr:
		return namedTypeExpression(typed.X)
	case *goast.IndexListExpr:
		return namedTypeExpression(typed.X)
	}
	return ""
}

// collectFieldAssignments 解析 `store.outbox = db.Collection(collectionName)` 形态。
func (scan *serviceScan) collectFieldAssignments(
	statement *goast.AssignStmt,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	for position, target := range statement.Lhs {
		selector, ok := target.(*goast.SelectorExpr)
		if !ok || position >= len(statement.Rhs) {
			continue
		}
		bindFieldValue(
			selector.Sel.Name, statement.Rhs[position], bindings, paramIndex, constructor,
		)
	}
}

func bindFieldValue(
	field string,
	value goast.Expr,
	bindings *packageBindings,
	paramIndex map[string]int,
	constructor string,
) {
	call, ok := value.(*goast.CallExpr)
	if !ok || !storageHandleBindingCalls[callTargetName(call)] {
		return
	}
	for _, argument := range call.Args {
		if literal, resolved := stringArgument(argument, bindings.constants); resolved {
			if relationNamePattern.MatchString(literal) {
				addFieldRelation(bindings, field, literal)
			}
			continue
		}
		identifier, isIdent := argument.(*goast.Ident)
		if !isIdent {
			continue
		}
		// 集合名由构造形参注入：等全服务装配点扫完，再用实参补齐这条边。
		if index, known := paramIndex[identifier.Name]; known {
			bindings.fieldConstructorParams[field] = append(
				bindings.fieldConstructorParams[field],
				constructorParam{constructor: constructor, index: index},
			)
		}
	}
}

func addFieldRelation(bindings *packageBindings, field string, relation string) {
	relations := bindings.fieldRelations[field]
	if relations == nil {
		relations = map[string]struct{}{}
		bindings.fieldRelations[field] = relations
	}
	relations[relation] = struct{}{}
}

func addFieldValue(bindings *packageBindings, field receiverFieldKey, value string) {
	values := bindings.fieldValues[field]
	if values == nil {
		values = map[string]struct{}{}
		bindings.fieldValues[field] = values
	}
	values[value] = struct{}{}
}

// collectConstructorCallArgs 记录装配点传给构造函数的关系名字面量，按实参位置登记。位置
// 匹配保证 `NewStore(db, "conversations", "conversations_outbox", "..._sequences")` 里
// 三个名字各归各的字段，不会互相串味。
func (scan *serviceScan) collectConstructorCallArgs(
	call *goast.CallExpr,
	dir string,
	imports map[string]string,
	constants map[string]string,
) {
	name := callTargetName(call)
	if !isConstructorName(name) {
		return
	}
	scalarKey, hasScalarIdentity := constructorCallIdentity(call, dir, imports)
	for position, argument := range call.Args {
		value, resolved := stringArgument(argument, constants)
		if !resolved {
			continue
		}
		if hasScalarIdentity {
			stringByIndex := scan.constructorStringCallArgs[scalarKey]
			if stringByIndex == nil {
				stringByIndex = map[int]map[string]struct{}{}
				scan.constructorStringCallArgs[scalarKey] = stringByIndex
			}
			if stringByIndex[position] == nil {
				stringByIndex[position] = map[string]struct{}{}
			}
			stringByIndex[position][value] = struct{}{}
		}
		if !relationNamePattern.MatchString(value) {
			continue
		}
		byIndex := scan.constructorCallArgs[name]
		if byIndex == nil {
			byIndex = map[int]map[string]struct{}{}
			scan.constructorCallArgs[name] = byIndex
		}
		if byIndex[position] == nil {
			byIndex[position] = map[string]struct{}{}
		}
		byIndex[position][value] = struct{}{}
	}
}

// constructorCallIdentity resolves only local calls or import-qualified first-party calls.
// This prevents an unrelated package's same-named constructor from supplying the scope for a
// shared store scanned in the same service composition.
func constructorCallIdentity(
	call *goast.CallExpr,
	dir string,
	imports map[string]string,
) (constructorCallKey, bool) {
	switch target := call.Fun.(type) {
	case *goast.Ident:
		return constructorCallKey{packageDir: dir, name: target.Name}, true
	case *goast.SelectorExpr:
		qualifier, ok := target.X.(*goast.Ident)
		if !ok {
			return constructorCallKey{}, false
		}
		importPath, imported := imports[qualifier.Name]
		if !imported || !strings.HasPrefix(importPath, "quwoquan_service/") {
			return constructorCallKey{}, false
		}
		packageDir, resolved := firstPartyPackageDir(dir, importPath)
		if !resolved {
			return constructorCallKey{}, false
		}
		return constructorCallKey{packageDir: packageDir, name: target.Sel.Name}, true
	}
	return constructorCallKey{}, false
}

func firstPartyPackageDir(currentDir string, importPath string) (string, bool) {
	current := filepath.ToSlash(filepath.Clean(currentDir))
	const moduleMarker = "/quwoquan_service/"
	position := strings.Index(current, moduleMarker)
	if position < 0 {
		return "", false
	}
	moduleRoot := current[:position] + "/quwoquan_service"
	relative := strings.TrimPrefix(importPath, "quwoquan_service/")
	if relative == importPath || relative == "" {
		return "", false
	}
	return filepath.Clean(filepath.FromSlash(moduleRoot + "/" + relative)), true
}

func methodReceiver(function *goast.FuncDecl) (string, string, bool) {
	if function == nil || function.Recv == nil || len(function.Recv.List) != 1 {
		return "", "", false
	}
	field := function.Recv.List[0]
	if len(field.Names) != 1 {
		return "", "", false
	}
	typeName := namedTypeExpression(field.Type)
	if typeName == "" || field.Names[0].Name == "_" {
		return "", "", false
	}
	return field.Names[0].Name, typeName, true
}
