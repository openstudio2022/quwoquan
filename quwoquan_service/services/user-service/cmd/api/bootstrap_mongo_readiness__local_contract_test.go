// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package bootstrap

import (
	"go/ast"
	"go/parser"
	"go/token"
	"testing"
)

func TestUserMongoReadinessIsOwnedByServicekitComponent(t *testing.T) {
	parsed, err := parser.ParseFile(
		token.NewFileSet(),
		"bootstrap.go",
		nil,
		parser.SkipObjectResolution,
	)
	if err != nil {
		t.Fatalf("parse bootstrap.go: %v", err)
	}

	var customMongoCalls int
	var usesDriverReadinessBudget bool
	var directMongoRegistrations int
	ast.Inspect(parsed, func(node ast.Node) bool {
		call, ok := node.(*ast.CallExpr)
		if !ok {
			return true
		}
		selector, ok := call.Fun.(*ast.SelectorExpr)
		if !ok {
			return true
		}
		receiver, ok := selector.X.(*ast.Ident)
		if ok && receiver.Name == "asm" && selector.Sel.Name == "MongoWithReadinessTimeout" {
			customMongoCalls++
			if len(call.Args) == 2 {
				budget, ok := call.Args[1].(*ast.SelectorExpr)
				budgetPackage, packageOK := budget.X.(*ast.Ident)
				usesDriverReadinessBudget = ok && packageOK &&
					budgetPackage.Name == "rtmongo" &&
					budget.Sel.Name == "DefaultReadinessTimeout"
			}
		}
		if selector.Sel.Name != "Register" && selector.Sel.Name != "RegisterWithTimeout" {
			return true
		}
		if healthSelector, ok := selector.X.(*ast.SelectorExpr); !ok {
			return true
		} else if assembly, ok := healthSelector.X.(*ast.Ident); !ok ||
			assembly.Name != "asm" || healthSelector.Sel.Name != "Health" {
			return true
		}
		if len(call.Args) == 0 {
			return true
		}
		name, ok := call.Args[0].(*ast.BasicLit)
		if ok && name.Kind == token.STRING && name.Value == `"mongodb"` {
			directMongoRegistrations++
		}
		return true
	})

	if customMongoCalls != 1 {
		t.Fatalf("user-service must assemble Mongo once with its readiness budget, got %d calls", customMongoCalls)
	}
	if !usesDriverReadinessBudget {
		t.Fatal("user-service Mongo readiness must use rtmongo.DefaultReadinessTimeout")
	}
	if directMongoRegistrations != 0 {
		t.Fatalf("user-service must not register mongodb health outside servicekit, got %d registrations", directMongoRegistrations)
	}
}
