// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
package es

import (
	"go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

const esImportPath = "quwoquan_service/runtime/search/es"

// legacyIndexerMethods 与 legacyClientMethods 是已从 runtime 删除的无版本写入面。
// 任何生产代码再次声明或调用它们都意味着回到了「旧轨乱序 upsert 覆盖新轨高版本、
// 硬删除抹掉 tombstone」的双轨状态。
var (
	legacyIndexerMethods = map[string]bool{"Apply": true, "Bulk": true}
	legacyClientMethods  = map[string]bool{"Upsert": true, "Delete": true, "Bulk": true}
	legacyTypeNames      = map[string]bool{"ChangeEvent": true, "Writer": true}
)

// TestRuntimeDeclaresOnlyVersionedElasticsearchWriteTrack 断言 runtime/search/es
// 自身不再声明无版本写入契约：没有 ChangeEvent / Writer 类型，也没有 Indexer.Apply、
// Indexer.Bulk、Client.Upsert、Client.Delete、Client.Bulk 方法。
func TestRuntimeDeclaresOnlyVersionedElasticsearchWriteTrack(t *testing.T) {
	files := parseGoFiles(t, ".", false)
	for path, file := range files {
		ast.Inspect(file, func(node ast.Node) bool {
			switch decl := node.(type) {
			case *ast.TypeSpec:
				if legacyTypeNames[decl.Name.Name] {
					t.Errorf("%s: legacy unversioned type %q must not be re-declared", path, decl.Name.Name)
				}
			case *ast.FuncDecl:
				if decl.Recv == nil || len(decl.Recv.List) == 0 {
					return true
				}
				receiver := receiverTypeName(decl.Recv.List[0].Type)
				switch {
				case receiver == "Indexer" && legacyIndexerMethods[decl.Name.Name]:
					t.Errorf("%s: (*Indexer).%s re-introduces the unversioned write track", path, decl.Name.Name)
				case receiver == "Client" && legacyClientMethods[decl.Name.Name]:
					t.Errorf("%s: (*Client).%s re-introduces the unversioned write track", path, decl.Name.Name)
				}
			}
			return true
		})
	}
}

// TestProductionCodeUsesOnlyVersionedElasticsearchWrites 扫描 services/** 与
// runtime/** 的生产代码（排除 *_test.go）：凡是导入 runtime/search/es 的文件，
// 不得再引用 es.ChangeEvent / es.Writer，也不得在 *es.Indexer 字段或变量上调用
// Apply/Bulk，或在 *es.Client 上调用 Upsert/Delete/Bulk。
func TestProductionCodeUsesOnlyVersionedElasticsearchWrites(t *testing.T) {
	root := moduleRoot(t)
	var violations []string
	for _, dir := range []string{"services", "runtime"} {
		files := parseGoFiles(t, filepath.Join(root, dir), true)
		for path, file := range files {
			alias := esImportAlias(file)
			if alias == "" {
				continue
			}
			relative, _ := filepath.Rel(root, path)
			for _, violation := range legacyESUsages(file, alias) {
				violations = append(violations, relative+": "+violation)
			}
		}
	}
	sort.Strings(violations)
	if len(violations) > 0 {
		t.Fatalf(
			"unversioned Elasticsearch writes are forbidden (DEC-002 / DEC-032); every projection sink must use ApplyVersioned / UpsertVersioned / TombstoneVersioned:\n%s",
			strings.Join(violations, "\n"),
		)
	}
}

func legacyESUsages(file *ast.File, alias string) []string {
	var out []string
	indexerNames := map[string]bool{}
	clientNames := map[string]bool{}
	// 第一遍：收集声明为 *es.Indexer / *es.Client 的字段、参数与变量名。
	ast.Inspect(file, func(node ast.Node) bool {
		switch decl := node.(type) {
		case *ast.Field:
			for _, name := range decl.Names {
				switch esTypeName(decl.Type, alias) {
				case "Indexer":
					indexerNames[name.Name] = true
				case "Client":
					clientNames[name.Name] = true
				}
			}
		case *ast.ValueSpec:
			for _, name := range decl.Names {
				switch esTypeName(decl.Type, alias) {
				case "Indexer":
					indexerNames[name.Name] = true
				case "Client":
					clientNames[name.Name] = true
				}
			}
		}
		return true
	})
	// 第二遍：检查禁止的选择器与方法调用。
	ast.Inspect(file, func(node ast.Node) bool {
		switch expr := node.(type) {
		case *ast.SelectorExpr:
			if ident, ok := expr.X.(*ast.Ident); ok && ident.Name == alias && legacyTypeNames[expr.Sel.Name] {
				out = append(out, "references "+alias+"."+expr.Sel.Name)
			}
		case *ast.CallExpr:
			selector, ok := expr.Fun.(*ast.SelectorExpr)
			if !ok {
				return true
			}
			receiverName := terminalIdentName(selector.X)
			if receiverName == "" {
				return true
			}
			if indexerNames[receiverName] && legacyIndexerMethods[selector.Sel.Name] {
				out = append(out, "calls "+receiverName+"."+selector.Sel.Name+" on *"+alias+".Indexer")
			}
			if clientNames[receiverName] && legacyClientMethods[selector.Sel.Name] {
				out = append(out, "calls "+receiverName+"."+selector.Sel.Name+" on *"+alias+".Client")
			}
		}
		return true
	})
	return out
}

func esTypeName(expr ast.Expr, alias string) string {
	if star, ok := expr.(*ast.StarExpr); ok {
		expr = star.X
	}
	selector, ok := expr.(*ast.SelectorExpr)
	if !ok {
		return ""
	}
	if ident, ok := selector.X.(*ast.Ident); ok && ident.Name == alias {
		return selector.Sel.Name
	}
	return ""
}

func terminalIdentName(expr ast.Expr) string {
	switch value := expr.(type) {
	case *ast.Ident:
		return value.Name
	case *ast.SelectorExpr:
		return value.Sel.Name
	default:
		return ""
	}
}

func receiverTypeName(expr ast.Expr) string {
	if star, ok := expr.(*ast.StarExpr); ok {
		expr = star.X
	}
	if ident, ok := expr.(*ast.Ident); ok {
		return ident.Name
	}
	return ""
}

func esImportAlias(file *ast.File) string {
	for _, spec := range file.Imports {
		if strings.Trim(spec.Path.Value, `"`) != esImportPath {
			continue
		}
		if spec.Name != nil {
			return spec.Name.Name
		}
		return "es"
	}
	return ""
}

func parseGoFiles(t *testing.T, root string, skipTests bool) map[string]*ast.File {
	t.Helper()
	files := map[string]*ast.File{}
	fileSet := token.NewFileSet()
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			name := entry.Name()
			if name == "testdata" || name == "node_modules" || strings.HasPrefix(name, ".") && path != root {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") {
			return nil
		}
		if skipTests && strings.HasSuffix(path, "_test.go") {
			return nil
		}
		file, parseErr := parser.ParseFile(fileSet, path, nil, parser.SkipObjectResolution)
		if parseErr != nil {
			return parseErr
		}
		files[path] = file
		return nil
	})
	if err != nil {
		t.Fatalf("parse go files under %s: %v", root, err)
	}
	return files
}

func moduleRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "go.mod")); statErr == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("go.mod not found above runtime/search/es")
		}
		dir = parent
	}
}
