package testinfra

import (
	goast "go/ast"
	"go/parser"
	"go/token"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// TransactionalOutboxRule 描述一个 Mongo store 源文件必须满足的事务性发布形状：
// 提交方法先取得事务句柄，聚合状态与 outbox 追加都只通过该句柄的 context 执行，
// 提交方法内不得存在绕开事务的第二条写入路径。
type TransactionalOutboxRule struct {
	// SourcePath 是相对仓库根的 store 源文件路径。
	SourcePath string
	// CommitFunctions 是必须在事务内同时写聚合状态与 outbox 的方法名。
	CommitFunctions []string
	// OutboxField 是 outbox 集合句柄的字段名。
	OutboxField string
	// OutboxDelegates 是把 outbox 追加委托出去的同文件辅助方法名。
	OutboxDelegates []string
	// StateDelegates 是把聚合状态写入委托出去的方法名（嵌入 store 或同文件辅助方法）。
	StateDelegates []string
	// SessionGuardedFunctions 是不自己开事务、但必须继承调用方事务句柄的追加方法名：
	// 它们要么在已有 session 内执行，要么整笔失败。
	SessionGuardedFunctions []string
	// ForbiddenIdentifiers 是不得复活的旁路符号（非事务提交回退、事务开关等）。
	ForbiddenIdentifiers []string
}

var mongoWriteMethods = map[string]bool{
	"InsertOne": true, "InsertMany": true, "UpdateOne": true, "UpdateMany": true,
	"ReplaceOne": true, "BulkWrite": true, "FindOneAndUpdate": true,
	"DeleteOne": true, "DeleteMany": true,
}

// AssertTransactionalOutboxAppend 断言 rule 描述的形状成立。
func AssertTransactionalOutboxAppend(t *testing.T, rule TransactionalOutboxRule) {
	t.Helper()
	path := filepath.Join(RepositoryRoot(t), rule.SourcePath)
	fileSet := token.NewFileSet()
	file, err := parser.ParseFile(fileSet, path, nil, parser.SkipObjectResolution)
	if err != nil {
		t.Fatalf("parse %s: %v", rule.SourcePath, err)
	}
	for _, forbidden := range rule.ForbiddenIdentifiers {
		goast.Inspect(file, func(node goast.Node) bool {
			if ident, ok := node.(*goast.Ident); ok && ident.Name == forbidden {
				t.Fatalf(
					"%s 重新引入了绕开事务的符号 %q：outbox 追加必须只有事务内一条路径",
					rule.SourcePath, forbidden,
				)
			}
			return true
		})
	}
	for _, name := range rule.CommitFunctions {
		assertCommitFunction(t, fileSet, file, rule, name)
	}
	for _, name := range rule.SessionGuardedFunctions {
		assertSessionGuardedFunction(t, file, rule, name)
	}
}

// assertSessionGuardedFunction 断言不自开事务的追加方法必须先确认调用方已经持有
// Mongo session：没有 session 就返回失败，而不是退化成事务外写入。
func assertSessionGuardedFunction(
	t *testing.T,
	file *goast.File,
	rule TransactionalOutboxRule,
	name string,
) {
	t.Helper()
	function := findMethod(file, name)
	if function == nil || function.Body == nil {
		t.Fatalf("%s 中找不到方法 %s", rule.SourcePath, name)
	}
	if !callsSelector(function.Body, "SessionFromContext") {
		t.Fatalf(
			"%s.%s 没有校验调用方事务句柄：缺少 SessionFromContext 守卫，"+
				"outbox 追加可能落在事务外",
			rule.SourcePath, name,
		)
	}
	appends := false
	goast.Inspect(function.Body, func(node goast.Node) bool {
		if call, ok := node.(*goast.CallExpr); ok && isOutboxAppend(call, rule) {
			appends = true
		}
		return true
	})
	if !appends {
		t.Fatalf("%s.%s 不再追加 outbox：该方法与本规则声明的发布路径不符", rule.SourcePath, name)
	}
}

func assertCommitFunction(
	t *testing.T,
	fileSet *token.FileSet,
	file *goast.File,
	rule TransactionalOutboxRule,
	name string,
) {
	t.Helper()
	function := findMethod(file, name)
	if function == nil || function.Body == nil {
		t.Fatalf("%s 中找不到提交方法 %s", rule.SourcePath, name)
	}
	if !callsSelector(function.Body, "WithTransaction") {
		t.Fatalf("%s.%s 没有取得事务句柄：缺少 WithTransaction 调用", rule.SourcePath, name)
	}
	literal := findTransactionLiteral(function.Body)
	if literal == nil {
		t.Fatalf("%s.%s 没有事务闭包：无法证明写入落在同一事务内", rule.SourcePath, name)
	}
	txContext := firstParameterName(literal)
	if txContext == "" || txContext == "_" {
		t.Fatalf("%s.%s 的事务闭包没有具名 context 参数", rule.SourcePath, name)
	}

	outboxInside := false
	stateInside := false
	goast.Inspect(literal.Body, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok || len(call.Args) == 0 || !isIdent(call.Args[0], txContext) {
			return true
		}
		switch {
		case isOutboxAppend(call, rule):
			outboxInside = true
		case isStateWrite(call, rule):
			stateInside = true
		}
		return true
	})
	if !outboxInside {
		t.Fatalf(
			"%s.%s 的事务闭包内没有用 %s 追加 outbox：事件可能落在事务外",
			rule.SourcePath, name, txContext,
		)
	}
	if !stateInside {
		t.Fatalf(
			"%s.%s 的事务闭包内没有用 %s 写聚合状态：无法证明状态与事件同事务",
			rule.SourcePath, name, txContext,
		)
	}

	start, end := literal.Pos(), literal.End()
	goast.Inspect(function.Body, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok || (call.Pos() >= start && call.End() <= end) {
			return true
		}
		if isOutboxAppend(call, rule) {
			t.Fatalf(
				"%s.%s 在事务闭包外仍向 outbox 追加（%s）：存在绕开事务的第二条路径",
				rule.SourcePath, name, fileSet.Position(call.Pos()),
			)
		}
		return true
	})
}

func isOutboxAppend(call *goast.CallExpr, rule TransactionalOutboxRule) bool {
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok {
		return false
	}
	for _, delegate := range rule.OutboxDelegates {
		if selector.Sel.Name == delegate {
			return true
		}
	}
	if !mongoWriteMethods[selector.Sel.Name] {
		return false
	}
	field, ok := selector.X.(*goast.SelectorExpr)
	return ok && field.Sel.Name == rule.OutboxField
}

func isStateWrite(call *goast.CallExpr, rule TransactionalOutboxRule) bool {
	selector, ok := call.Fun.(*goast.SelectorExpr)
	if !ok {
		return false
	}
	for _, delegate := range rule.StateDelegates {
		if selector.Sel.Name == delegate {
			return true
		}
	}
	if !mongoWriteMethods[selector.Sel.Name] {
		return false
	}
	field, ok := selector.X.(*goast.SelectorExpr)
	return ok && field.Sel.Name != rule.OutboxField
}

func findMethod(file *goast.File, name string) *goast.FuncDecl {
	for _, declaration := range file.Decls {
		function, ok := declaration.(*goast.FuncDecl)
		if ok && function.Name.Name == name {
			return function
		}
	}
	return nil
}

// findTransactionLiteral 找到提交方法里承载事务体的闭包：签名形如
// func(context.Context) (any, error)，无论它是 WithTransaction 的内联实参
// 还是先赋给局部变量再传入。
func findTransactionLiteral(body *goast.BlockStmt) *goast.FuncLit {
	var found *goast.FuncLit
	goast.Inspect(body, func(node goast.Node) bool {
		literal, ok := node.(*goast.FuncLit)
		if !ok || found != nil {
			return true
		}
		params := literal.Type.Params
		if params == nil || len(params.List) != 1 {
			return true
		}
		if selector, ok := params.List[0].Type.(*goast.SelectorExpr); ok &&
			selector.Sel.Name == "Context" {
			found = literal
		}
		return true
	})
	return found
}

func firstParameterName(literal *goast.FuncLit) string {
	params := literal.Type.Params
	if params == nil || len(params.List) != 1 || len(params.List[0].Names) != 1 {
		return ""
	}
	return params.List[0].Names[0].Name
}

func callsSelector(body *goast.BlockStmt, name string) bool {
	found := false
	goast.Inspect(body, func(node goast.Node) bool {
		call, ok := node.(*goast.CallExpr)
		if !ok {
			return true
		}
		if selector, ok := call.Fun.(*goast.SelectorExpr); ok && selector.Sel.Name == name {
			found = true
		}
		return true
	})
	return found
}

func isIdent(expression goast.Expr, name string) bool {
	ident, ok := expression.(*goast.Ident)
	return ok && ident.Name == name
}

// RepositoryRoot 返回仓库根目录，供源码级契约测试定位被检查的实现文件。
func RepositoryRoot(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("无法定位测试支持文件路径")
	}
	root := thisFile
	for i := 0; i < 12; i++ {
		root = filepath.Dir(root)
		if strings.HasSuffix(root, string(filepath.Separator)+"quwoquan_service") {
			return filepath.Dir(root)
		}
	}
	t.Fatalf("从 %s 向上找不到仓库根", thisFile)
	return ""
}
