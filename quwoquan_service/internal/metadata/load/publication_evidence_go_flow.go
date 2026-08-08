package load

import (
	goast "go/ast"
	"go/token"
	"regexp"
	"sort"
	"strings"
)

func functionReturnsString(function *goast.FuncDecl) bool {
	if function == nil || function.Type == nil || function.Type.Results == nil ||
		len(function.Type.Results.List) != 1 {
		return false
	}
	result, ok := function.Type.Results.List[0].Type.(*goast.Ident)
	return ok && result.Name == "string"
}

// collectConditionalRelationResolvers recognizes only a receiver-field switch with literal
// cases and literal relation returns. It does not infer from method names, comments, default
// branches or string proximity. The configured field value must later arrive through a real
// constructor call before any relation can be selected.
func (scan *serviceScan) collectConditionalRelationResolvers(
	dir string,
	function *goast.FuncDecl,
	constants map[string]string,
) {
	receiverName, receiverType, ok := methodReceiver(function)
	if !ok || !functionReturnsString(function) {
		return
	}
	key := methodRelationKey{
		packageDir: dir, receiverType: receiverType, method: function.Name.Name,
	}
	for _, statement := range function.Body.List {
		switchStatement, isSwitch := statement.(*goast.SwitchStmt)
		if !isSwitch || switchStatement.Tag == nil {
			continue
		}
		selector, isSelector := switchStatement.Tag.(*goast.SelectorExpr)
		if !isSelector {
			continue
		}
		receiver, isReceiver := selector.X.(*goast.Ident)
		if !isReceiver || receiver.Name != receiverName {
			continue
		}
		resolver := conditionalRelationResolver{
			field:            receiverFieldKey{receiverType: receiverType, field: selector.Sel.Name},
			relationsByValue: map[string]map[string]struct{}{},
		}
		for _, clauseStatement := range switchStatement.Body.List {
			clause, isClause := clauseStatement.(*goast.CaseClause)
			if !isClause || len(clause.List) == 0 {
				// A default branch is intentionally unusable: it is not tied to an exact
				// production composition value.
				continue
			}
			relation, returned := singleReturnedRelation(clause.Body, constants)
			if !returned {
				continue
			}
			for _, caseExpression := range clause.List {
				value, resolved := stringArgument(caseExpression, constants)
				if !resolved {
					continue
				}
				if resolver.relationsByValue[value] == nil {
					resolver.relationsByValue[value] = map[string]struct{}{}
				}
				resolver.relationsByValue[value][relation] = struct{}{}
			}
		}
		if len(resolver.relationsByValue) != 0 {
			scan.relationResolvers[key] = append(scan.relationResolvers[key], resolver)
		}
	}
}

func singleReturnedRelation(
	statements []goast.Stmt,
	constants map[string]string,
) (string, bool) {
	if len(statements) != 1 {
		return "", false
	}
	result, ok := statements[0].(*goast.ReturnStmt)
	if !ok || len(result.Results) != 1 {
		return "", false
	}
	relation, resolved := stringArgument(result.Results[0], constants)
	if !resolved || !relationNamePattern.MatchString(relation) {
		return "", false
	}
	return relation, true
}

// collectDynamicTransactionalSQLWrites follows one bounded, explicit local flow:
//
//	relation := receiver.literalSwitchResolver()
//	query := fmt.Sprintf("INSERT INTO %s (...) ...", relation)
//	tx.Exec(ctx, query, ...)
//
// The fmt import identity, SQL relation placeholder, receiver identity and transaction handle
// are all required. A similar-looking log string, SELECT, pool.Exec or uncomposed resolver does
// not become publication evidence.
func collectDynamicTransactionalSQLWrites(
	dir string,
	function *goast.FuncDecl,
	handles map[string]struct{},
	constants map[string]string,
	imports map[string]string,
) []methodRelationKey {
	receiverName, receiverType, hasReceiver := methodReceiver(function)
	if !hasReceiver {
		return nil
	}
	relationLocals := map[string]methodRelationKey{}
	queryLocals := map[string]methodRelationKey{}
	writes := []methodRelationKey{}
	goast.Inspect(function.Body, func(node goast.Node) bool {
		switch typed := node.(type) {
		case *goast.AssignStmt:
			for _, target := range typed.Lhs {
				if identifier, ok := target.(*goast.Ident); ok {
					delete(relationLocals, identifier.Name)
					delete(queryLocals, identifier.Name)
				}
			}
			if len(typed.Lhs) != len(typed.Rhs) {
				return true
			}
			for position, expression := range typed.Rhs {
				target, isIdentifier := typed.Lhs[position].(*goast.Ident)
				if !isIdentifier || target.Name == "_" {
					continue
				}
				if key, ok := receiverRelationMethodCall(
					dir, receiverName, receiverType, expression,
				); ok {
					relationLocals[target.Name] = key
					continue
				}
				if key, ok := formattedSQLRelationCall(
					expression, relationLocals, constants, imports,
				); ok {
					queryLocals[target.Name] = key
				}
			}
		case *goast.CallExpr:
			if !writeMethodNames[callTargetName(typed)] {
				return true
			}
			selector, isSelector := typed.Fun.(*goast.SelectorExpr)
			if !isSelector {
				return true
			}
			tx, isTransaction := selector.X.(*goast.Ident)
			if !isTransaction {
				return true
			}
			if _, allowed := handles[tx.Name]; !allowed {
				return true
			}
			for _, argument := range typed.Args {
				query, isIdentifier := argument.(*goast.Ident)
				if !isIdentifier {
					continue
				}
				if key, bound := queryLocals[query.Name]; bound {
					writes = appendUniqueMethodRelationKey(writes, key)
				}
			}
		}
		return true
	})
	return writes
}

func receiverRelationMethodCall(
	dir string,
	receiverName string,
	receiverType string,
	expression goast.Expr,
) (methodRelationKey, bool) {
	call, ok := expression.(*goast.CallExpr)
	if !ok || len(call.Args) != 0 {
		return methodRelationKey{}, false
	}
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok {
		return methodRelationKey{}, false
	}
	receiver, ok := selector.X.(*goast.Ident)
	if !ok || receiver.Name != receiverName {
		return methodRelationKey{}, false
	}
	return methodRelationKey{
		packageDir: dir, receiverType: receiverType, method: selector.Sel.Name,
	}, true
}

func formattedSQLRelationCall(
	expression goast.Expr,
	relationLocals map[string]methodRelationKey,
	constants map[string]string,
	imports map[string]string,
) (methodRelationKey, bool) {
	call, ok := expression.(*goast.CallExpr)
	if !ok || len(call.Args) != 2 {
		return methodRelationKey{}, false
	}
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok || selector.Sel.Name != "Sprintf" {
		return methodRelationKey{}, false
	}
	qualifier, ok := selector.X.(*goast.Ident)
	if !ok || imports[qualifier.Name] != "fmt" {
		return methodRelationKey{}, false
	}
	format, resolved := stringArgument(call.Args[0], constants)
	if !resolved || strings.Count(format, "%s") != 1 ||
		!sqlWriteRelationPlaceholderPattern.MatchString(format) {
		return methodRelationKey{}, false
	}
	relation, ok := call.Args[1].(*goast.Ident)
	if !ok {
		return methodRelationKey{}, false
	}
	key, bound := relationLocals[relation.Name]
	return key, bound
}

func appendUniqueMethodRelationKey(
	keys []methodRelationKey,
	key methodRelationKey,
) []methodRelationKey {
	for _, existing := range keys {
		if existing == key {
			return keys
		}
	}
	return append(keys, key)
}

// collectTransactionClosureHandles 把 `session.WithTransaction(ctx, func(txCtx ...))` 的闭包
// 形参识别成事务句柄。Mongo 的事务上下文就是这个闭包参数，签名类型上看不出来。
func collectTransactionClosureHandles(call *goast.CallExpr, handles map[string]struct{}) {
	name := callTargetName(call)
	if !transactionOpenerNames[name] && !transactionScopeCallNames[name] {
		return
	}
	for _, argument := range call.Args {
		literal, ok := argument.(*goast.FuncLit)
		if !ok || literal.Type == nil || literal.Type.Params == nil {
			continue
		}
		for _, field := range literal.Type.Params.List {
			for _, parameterName := range field.Names {
				if parameterName.Name != "_" {
					handles[parameterName.Name] = struct{}{}
				}
			}
		}
	}
}

// collectAccessTargets 抽出函数体内的写入目标、读取目标、是否推进进度，以及「以事务句柄
// 调用了哪些方法」。目标可能是字段、局部句柄或 SQL 关系位，解析统一推迟到 resolve。
func collectAccessTargets(
	body *goast.BlockStmt,
	handles map[string]struct{},
	record *functionRecord,
	constants map[string]string,
) {
	goast.Inspect(body, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		name := callTargetName(call)
		if name != "" {
			arguments := make([]argumentReference, 0, len(call.Args))
			for _, argument := range call.Args {
				arguments = append(
					arguments,
					argumentReferenceForExpression(argument, constants),
				)
			}
			record.calls = append(record.calls, functionCall{
				callee: name, arguments: arguments,
			})
			record.deliveryRead = record.deliveryRead || isDeliveryReadCall(name)
			record.deliveryAdvance = record.deliveryAdvance || isDeliveryAdvanceCall(name)
			record.deliveryHandoff = record.deliveryHandoff || isDeliveryHandoffCall(name)
		}
		if callPassesHandle(call, handles) && name != "" {
			record.handleCallees = append(record.handleCallees, name)
		}
		// 领取型原子操作（`FindOneAndUpdate` 等）同时是读与推进：投递侧的「认领一条」
		// 就是这一个调用，拆成读或写任一侧都会漏判。
		isWrite := writeMethodNames[name] || claimMethodNames[name]
		isRead := readMethodNames[name] || claimMethodNames[name]
		if !isWrite && !isRead {
			return true
		}
		if selector, isSelector := call.Fun.(*goast.SelectorExpr); isSelector {
			switch receiver := selector.X.(type) {
			case *goast.SelectorExpr:
				// `s.outbox.InsertOne(...)`：接收者是结构体字段。
				if isWrite {
					record.writtenFields = append(record.writtenFields, receiver.Sel.Name)
					record.advancesProgres = true
				}
				if isRead {
					record.readFields = append(record.readFields, receiver.Sel.Name)
				}
			case *goast.Ident:
				if isWrite {
					record.writtenLocals = append(record.writtenLocals, receiver.Name)
					record.advancesProgres = true
				}
				if isRead {
					record.readLocals = append(record.readLocals, receiver.Name)
				}
			case *goast.CallExpr:
				if storageHandleBindingCalls[callTargetName(receiver)] {
					if relation, resolved := handleBindingRelation(receiver, constants); resolved {
						if isWrite {
							record.writtenSQL = append(record.writtenSQL, relation)
							record.advancesProgres = true
						}
						if isRead {
							record.readSQL = append(record.readSQL, relation)
						}
					}
				}
			}
		}
		for _, argument := range call.Args {
			statement, resolved := stringArgument(argument, constants)
			if !resolved {
				continue
			}
			for _, relation := range sqlWriteRelations(statement) {
				record.writtenSQL = append(record.writtenSQL, relation)
				record.advancesProgres = true
			}
			for _, relation := range sqlReadRelations(statement) {
				record.readSQL = append(record.readSQL, relation)
			}
		}
		return true
	})
}

// 三类调用必须在同一个 relay/drain 函数中形成闭环。这里匹配的是 AST selector call 的
// canonical operation identity，不扫描原始 token；注释、TODO、错误字符串和同名文件均
// 不可能命中。名称集合覆盖仓内现有 OutboxReader / lease / checkpoint port 形状。
func isDeliveryReadCall(name string) bool {
	return name == "ReadAfter" ||
		(strings.HasPrefix(name, "Read") && strings.Contains(name, "Outbox")) ||
		strings.HasPrefix(name, "ClaimPending") ||
		strings.HasPrefix(name, "LeaseNext")
}

func isDeliveryAdvanceCall(name string) bool {
	return (strings.HasPrefix(name, "Save") && strings.Contains(name, "Checkpoint")) ||
		(strings.HasPrefix(name, "Mark") &&
			(strings.Contains(name, "Published") || strings.Contains(name, "Dispatched"))) ||
		strings.HasPrefix(name, "Acknowledge")
}

func isDeliveryHandoffCall(name string) bool {
	return strings.HasPrefix(name, "Publish") || name == "AppendDurable"
}

func argumentReferenceForExpression(
	expression goast.Expr,
	constants map[string]string,
) argumentReference {
	switch typed := expression.(type) {
	case *goast.Ident:
		if value, ok := constants[typed.Name]; ok && relationNamePattern.MatchString(value) {
			return argumentReference{literal: value}
		}
		return argumentReference{identifier: typed.Name}
	case *goast.SelectorExpr:
		return argumentReference{field: typed.Sel.Name}
	case *goast.BasicLit:
		value, ok := stringArgument(typed, constants)
		if ok && relationNamePattern.MatchString(value) {
			return argumentReference{literal: value}
		}
	}
	return argumentReference{}
}

func callPassesHandle(call *goast.CallExpr, handles map[string]struct{}) bool {
	for _, argument := range call.Args {
		identifier, ok := argument.(*goast.Ident)
		if !ok {
			continue
		}
		if _, isHandle := handles[identifier.Name]; isHandle {
			return true
		}
	}
	return false
}

type propagatedCallFacts struct {
	transactionVars    map[int]map[string]struct{}
	transactional      map[int]bool
	parameterRelations map[int]map[string]map[string]struct{}
}

// propagateCallFacts 只沿同包、已声明函数和精确实参位置传播，且最多四跳。该上界覆盖现仓
// `WithTransaction -> appendOutbox -> appendOutboxEvent -> InsertOne`，同时阻止 context 或
// collection 一旦进入通用 helper 就无界污染全服务。
func (scan *serviceScan) propagateCallFacts() propagatedCallFacts {
	facts := propagatedCallFacts{
		transactionVars:    map[int]map[string]struct{}{},
		transactional:      map[int]bool{},
		parameterRelations: map[int]map[string]map[string]struct{}{},
	}
	recordsByKey := map[functionKey][]int{}
	for index, record := range scan.functions {
		key := functionKey{packageDir: record.packageDir, name: record.name}
		recordsByKey[key] = append(recordsByKey[key], index)
		facts.transactionVars[index] = map[string]struct{}{}
		for _, name := range record.transactionVars {
			facts.transactionVars[index][name] = struct{}{}
		}
		// 保留既有「事务句柄作为实参调用同名方法」的跨包接口事实；它覆盖 application
		// 通过 interface 调用 persistence method 的形状。后续 helper 传播仍只沿同包已声明
		// 调用图进行，避免把同名函数无限扩散到整个服务。
		_, invokedWithTransaction := scan.txInvokedMethods[record.name]
		facts.transactional[index] = record.holdsHandle || invokedWithTransaction
		facts.parameterRelations[index] = map[string]map[string]struct{}{}
	}

	for depth := 0; depth < maxPublicationCallDepth; depth++ {
		changed := false
		for callerIndex, caller := range scan.functions {
			bindings := scan.bindings[caller.packageDir]
			if bindings == nil {
				continue
			}
			locals := bindings.localsByFunction[caller.name]
			for _, call := range caller.calls {
				targets := recordsByKey[functionKey{
					packageDir: caller.packageDir,
					name:       call.callee,
				}]
				for _, targetIndex := range targets {
					target := scan.functions[targetIndex]
					for position, reference := range call.arguments {
						if position >= len(target.parameters) || target.parameters[position] == "" {
							continue
						}
						parameter := target.parameters[position]
						if reference.identifier != "" {
							if _, tainted := facts.transactionVars[callerIndex][reference.identifier]; tainted {
								if addSetValue(facts.transactionVars[targetIndex], parameter) {
									changed = true
								}
								facts.transactional[targetIndex] = true
							}
						}
						relations := resolveArgumentRelations(
							reference,
							bindings,
							locals,
							facts.parameterRelations[callerIndex],
						)
						if len(relations) == 0 {
							continue
						}
						if facts.parameterRelations[targetIndex][parameter] == nil {
							facts.parameterRelations[targetIndex][parameter] = map[string]struct{}{}
						}
						for relation := range relations {
							if addSetValue(
								facts.parameterRelations[targetIndex][parameter], relation,
							) {
								changed = true
							}
						}
					}
				}
			}
		}
		if !changed {
			break
		}
	}
	return facts
}

func addSetValue(values map[string]struct{}, value string) bool {
	if value == "" {
		return false
	}
	if _, exists := values[value]; exists {
		return false
	}
	values[value] = struct{}{}
	return true
}

func resolveArgumentRelations(
	reference argumentReference,
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
) map[string]struct{} {
	result := map[string]struct{}{}
	if reference.literal != "" {
		result[reference.literal] = struct{}{}
	}
	if reference.field != "" {
		for relation := range bindings.fieldRelations[reference.field] {
			result[relation] = struct{}{}
		}
	}
	if reference.identifier != "" {
		if relation, ok := locals[reference.identifier]; ok {
			result[relation] = struct{}{}
		}
		for relation := range parameters[reference.identifier] {
			result[relation] = struct{}{}
		}
	}
	return result
}

// resolve 把推迟的目标解析成关系名，并合成事务性判定。
func (scan *serviceScan) resolve(index *serviceWriteIndex) {
	// 构造形参注入的集合名：按「构造函数名 + 实参位置」补齐，位置匹配保证
	// `NewStore(db, "conversations", "conversations_outbox", "..._sequences")` 里三个名字
	// 各归各的字段，不会互相串味。
	for _, bindings := range scan.bindings {
		for field, params := range bindings.fieldConstructorParams {
			for _, param := range params {
				for relation := range scan.constructorCallArgs[param.constructor][param.index] {
					addFieldRelation(bindings, field, relation)
				}
			}
		}
		for field, params := range bindings.fieldValueConstructorParams {
			for _, param := range params {
				for value := range scan.constructorStringCallArgs[param.constructor][param.index] {
					addFieldValue(bindings, field, value)
				}
			}
		}
	}
	callFacts := scan.propagateCallFacts()
	for _, candidate := range scan.externalCandidates {
		if _, declared := scan.declaredFunctions[candidate.callee]; declared && !candidate.external {
			continue
		}
		index.externalBindings[candidate.relation] = append(
			index.externalBindings[candidate.relation], candidate.file,
		)
	}
	for recordIndex, record := range scan.functions {
		bindings := scan.bindings[record.packageDir]
		if bindings == nil {
			continue
		}
		if record.deliveryRead && record.deliveryAdvance && record.deliveryHandoff {
			if scope := publicationImplementationScope(record.file); scope != "" {
				index.deliveryRelayScopes[scope] = struct{}{}
			}
		}
		transactional := record.holdsHandle || callFacts.transactional[recordIndex]
		site := writeSite{file: record.file, function: record.name}
		locals := bindings.localsByFunction[record.name]
		if transactional {
			if len(record.writtenFields)+len(record.writtenLocals)+len(record.writtenSQL)+
				len(record.dynamicSQLWrites) > 0 {
				index.packagesWritingTransactionally[record.packageDir] = struct{}{}
			}
			dynamicWrites := scan.resolveDynamicSQLWrites(record.dynamicSQLWrites, bindings)
			for _, relation := range record.resolvedWrites(
				bindings, locals, callFacts.parameterRelations[recordIndex], dynamicWrites,
			) {
				index.transactionalWrites[relation] = appendSite(
					index.transactionalWrites[relation], site,
				)
			}
		}
		// 投递实现不要求事务：relay 通常在事务外拉取，再单独提交检查点。
		if record.advancesProgres {
			index.packagesAdvancingProgress[record.packageDir] = struct{}{}
		}
		for _, relation := range record.resolvedReads(
			bindings, locals, callFacts.parameterRelations[recordIndex],
		) {
			index.deliveryReads[relation] = appendReadSite(
				index.deliveryReads[relation],
				readSite{writeSite: site, packageDir: record.packageDir},
			)
		}
	}
}

func (scan *serviceScan) resolveDynamicSQLWrites(
	keys []methodRelationKey,
	bindings *packageBindings,
) []string {
	found := map[string]struct{}{}
	for _, key := range keys {
		for _, resolver := range scan.relationResolvers[key] {
			for value := range bindings.fieldValues[resolver.field] {
				for relation := range resolver.relationsByValue[value] {
					found[relation] = struct{}{}
				}
			}
		}
	}
	relations := make([]string, 0, len(found))
	for relation := range found {
		relations = append(relations, relation)
	}
	sort.Strings(relations)
	return relations
}

func (record functionRecord) resolvedWrites(
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
	dynamic []string,
) []string {
	return resolveTargets(
		record.writtenFields, record.writtenLocals, append(record.writtenSQL, dynamic...),
		bindings, locals, parameters,
	)
}

func (record functionRecord) resolvedReads(
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
) []string {
	return resolveTargets(
		record.readFields, record.readLocals, record.readSQL,
		bindings, locals, parameters,
	)
}

func resolveTargets(
	fields []string,
	localNames []string,
	direct []string,
	bindings *packageBindings,
	locals map[string]string,
	parameters map[string]map[string]struct{},
) []string {
	found := map[string]struct{}{}
	for _, field := range fields {
		for relation := range bindings.fieldRelations[field] {
			found[relation] = struct{}{}
		}
	}
	for _, name := range localNames {
		if relation, ok := locals[name]; ok {
			found[relation] = struct{}{}
		}
		for relation := range parameters[name] {
			found[relation] = struct{}{}
		}
	}
	for _, relation := range direct {
		found[relation] = struct{}{}
	}
	relations := make([]string, 0, len(found))
	for relation := range found {
		relations = append(relations, relation)
	}
	sort.Strings(relations)
	return relations
}

func appendReadSite(sites []readSite, site readSite) []readSite {
	for _, existing := range sites {
		if existing == site {
			return sites
		}
	}
	return append(sites, site)
}

func appendSite(sites []writeSite, site writeSite) []writeSite {
	for _, existing := range sites {
		if existing == site {
			return sites
		}
	}
	return append(sites, site)
}

func appendUniqueString(values []string, value string) []string {
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}

// collectLocalRelationBindings 解析函数体内的局部句柄绑定：`events := db.Collection("x")`。
func collectLocalRelationBindings(
	statement *goast.AssignStmt,
	locals map[string]string,
	constants map[string]string,
) {
	for position, value := range statement.Rhs {
		call, ok := value.(*goast.CallExpr)
		if !ok || !storageHandleBindingCalls[callTargetName(call)] {
			continue
		}
		relation, resolved := handleBindingRelation(call, constants)
		if !resolved || position >= len(statement.Lhs) {
			continue
		}
		if identifier, isIdent := statement.Lhs[position].(*goast.Ident); isIdent {
			locals[identifier.Name] = relation
		}
	}
}

func handleBindingRelation(
	call *goast.CallExpr,
	constants map[string]string,
) (string, bool) {
	for _, argument := range call.Args {
		value, ok := stringArgument(argument, constants)
		if !ok {
			continue
		}
		if relationNamePattern.MatchString(value) {
			return value, true
		}
	}
	return "", false
}

// stringArgument 把实参解析成字符串：字面量直接取，标识符回查包内 const/var。
func stringArgument(expression goast.Expr, constants map[string]string) (string, bool) {
	switch typed := expression.(type) {
	case *goast.BasicLit:
		if typed.Kind != token.STRING {
			return "", false
		}
		return trimStringLiteral(typed.Value), true
	case *goast.Ident:
		value, ok := constants[typed.Name]
		return value, ok
	}
	return "", false
}

// sqlWriteRelations 抽 SQL 写语句关系位的裸标识符。Postgres 不带引号，所以按词边界匹配、
// 不要求引号——`INSERT INTO credential_bindings_outbox(` 这种紧跟左括号的形态也必须命中。
func sqlWriteRelations(statement string) []string {
	return matchRelations(sqlWritePattern, statement)
}

func sqlReadRelations(statement string) []string {
	return matchRelations(sqlReadPattern, statement)
}

func sqlRelations(statement string) []string {
	return append(sqlWriteRelations(statement), sqlReadRelations(statement)...)
}

func matchRelations(pattern *regexp.Regexp, statement string) []string {
	var relations []string
	for _, match := range pattern.FindAllStringSubmatch(statement, -1) {
		relation := strings.Trim(strings.ToLower(match[1]), `"`)
		if !relationNamePattern.MatchString(relation) {
			continue
		}
		// `ON CONFLICT ... DO UPDATE SET col = ...` 的 `SET` 会落在 UPDATE 的关系位上，
		// `DELETE FROM ... USING ...` 同理。SQL 关键字不是关系名。
		if sqlKeywords[relation] {
			continue
		}
		relations = append(relations, relation)
	}
	return relations
}

func isConstructorName(name string) bool {
	return strings.HasPrefix(name, "New") || strings.HasPrefix(name, "Open")
}

func trimStringLiteral(literal string) string {
	return strings.Trim(literal, "`\"'")
}

var (
	// relationNamePattern 是「整体就是一个关系名」的形状：小写标识符 token，允许 schema
	// 前缀与连字符。散文与 SQL 片段不会整体匹配到它。
	relationNamePattern = regexp.MustCompile(`^[a-z][a-z0-9_]*(?:[.$-][a-z0-9_]+)*$`)
	sqlWritePattern     = regexp.MustCompile(
		`(?is)\b(?:insert\s+into|update|delete\s+from|` +
			`create\s+table(?:\s+if\s+not\s+exists)?)\s+("?[a-z][a-z0-9_.$-]*"?)`,
	)
	sqlReadPattern = regexp.MustCompile(
		`(?is)\bfrom\s+("?[a-z][a-z0-9_.$-]*"?)`,
	)
	// Dynamic SQL is accepted only when fmt.Sprintf places its sole `%s` directly in a
	// write-statement relation slot. Other formatting, diagnostics and SELECTs are ignored.
	sqlWriteRelationPlaceholderPattern = regexp.MustCompile(
		`(?is)\b(?:insert\s+into|update|delete\s+from|` +
			`create\s+table(?:\s+if\s+not\s+exists)?)\s+%s(?:\s|\(|"|$)`,
	)
	sqlKeywords = map[string]bool{
		"set": true, "of": true, "only": true, "select": true, "where": true,
		"values": true, "returning": true, "using": true, "as": true, "on": true,
	}
	// storageHandleBindingCalls 是把集合/表名字面量绑定成存储句柄的调用。
	storageHandleBindingCalls = map[string]bool{
		"Collection":     true,
		"Table":          true,
		"GetCollection":  true,
		"WithCollection": true,
	}
	writeMethodNames = map[string]bool{
		"InsertOne":   true,
		"InsertMany":  true,
		"BulkWrite":   true,
		"ReplaceOne":  true,
		"UpdateOne":   true,
		"UpdateMany":  true,
		"Exec":        true,
		"ExecContext": true,
	}
	// transactionScopeCallNames 是「把事务范围交给闭包」的调用：闭包形参就是事务上下文。
	// Mongo 与领域事务端口都走这个形状（`s.transactions.RunInTransaction(ctx, func(txCtx
	// context.Context) error {...})`），签名类型上完全看不出事务性。
	transactionScopeCallNames = map[string]bool{
		"WithTransaction":      true,
		"UseSession":           true,
		"RunInTransaction":     true,
		"RunTransaction":       true,
		"InTransaction":        true,
		"ExecuteInTransaction": true,
		"WithTx":               true,
		"RunInTx":              true,
	}
	claimMethodNames = map[string]bool{
		"FindOneAndUpdate":  true,
		"FindOneAndDelete":  true,
		"FindOneAndReplace": true,
	}
	readMethodNames = map[string]bool{
		"Find":      true,
		"FindOne":   true,
		"Query":     true,
		"QueryRow":  true,
		"Aggregate": true,
	}
)
