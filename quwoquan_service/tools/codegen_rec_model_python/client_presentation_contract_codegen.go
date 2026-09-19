package main

import (
	"bytes"
	"fmt"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/tools/internal/presentationcontract"
)

// generateRankedWindowArtifacts 保持 ranked 契约可选，能力产物与真实 transport 同一次生成。
func generateRankedWindowArtifacts(source *contractcodegen.Source, servicePath, outputDir, goOutput string) error {
	owner := filepath.Join(filepath.Dir(servicePath), "ranked_recommendation_window")
	if !source.Has(filepath.Join(owner, "fields.yaml")) {
		return nil
	}
	output := filepath.Join(filepath.Dir(outputDir), "ranked_recommendation_window")
	if err := generateObjectTransportPackage(source, owner, output, nil); err != nil {
		return fmt.Errorf("generate ranked recommendation window: %w", err)
	}
	// 空或全空白 Go 目的路径只生成 Python；不得把缺席解释为当前目录文件。
	goOutput = strings.TrimSpace(goOutput)
	if goOutput != "" {
		if err := generateRankedWindowGoArtifact(source, owner, goOutput); err != nil {
			return err
		}
	}
	return writeClientPresentationContractArtifacts(source, output, goOutput)
}

func generateRankedWindowGoArtifact(source *contractcodegen.Source, owner, output string) error {
	fields, err := loadFields(source, filepath.Join(owner, "fields.yaml"))
	if err != nil {
		return fmt.Errorf("load ranked recommendation window Go fields: %w", err)
	}
	operations, err := loadOperations(source, filepath.Join(owner, "operations.yaml"))
	if err != nil {
		return fmt.Errorf("load ranked recommendation window Go operations: %w", err)
	}
	if _, err := resolveTransportClosure(fields, fields.Shared, operations); err != nil {
		return err
	}
	if err := writeRankedWindowGoTransport(output, fields, operations); err != nil {
		return fmt.Errorf("generate Content ranked window Go transport: %w", err)
	}
	return nil
}

// writeClientPresentationContractArtifacts 在 ranked transport 写完后调用。
// Python 写入已有 manifest 扫描根；Go 合并进已追踪的 transport，check/manifest 不需新路径表。
func writeClientPresentationContractArtifacts(source *contractcodegen.Source, rankedOutputDir, rankedGoOutput string) error {
	raw, err := source.Content("_shared/types.yaml")
	if err != nil {
		return err
	}
	model, err := presentationcontract.Load(raw)
	if err != nil {
		return err
	}
	python, err := model.RenderPython()
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(rankedOutputDir, "models", "client_presentation_contract.py"), []byte(python), 0644); err != nil {
		return err
	}
	golden, err := model.GoldenFixture()
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(rankedOutputDir, "models", "client_presentation_contract.golden.json"), golden, 0644); err != nil {
		return err
	}
	if rankedGoOutput == "" {
		return nil
	}
	transport, err := os.ReadFile(rankedGoOutput)
	if err != nil {
		return err
	}
	helpers, err := model.RenderGo("feeddeliverypage")
	if err != nil {
		return err
	}
	combined, err := mergePresentationGoTransport(transport, helpers)
	if err != nil {
		return err
	}
	return os.WriteFile(rankedGoOutput, combined, 0644)
}

// mergePresentationGoTransport 保留真实 transport enum 和 DTO，仅合并 helper import/声明。
func mergePresentationGoTransport(transport, helpers []byte) ([]byte, error) {
	fset := token.NewFileSet()
	base, err := parser.ParseFile(fset, "transport.go", transport, parser.ParseComments)
	if err != nil {
		return nil, err
	}
	extra, err := parser.ParseFile(fset, "helpers.go", helpers, 0)
	if err != nil {
		return nil, err
	}
	if base.Name.Name != extra.Name.Name {
		return nil, fmt.Errorf("presentation helper package mismatch")
	}
	imports := map[string]bool{}
	for _, spec := range base.Imports {
		imports[spec.Path.Value] = true
	}
	var newImports []ast.Spec
	for _, decl := range extra.Decls {
		if group, ok := decl.(*ast.GenDecl); ok && group.Tok == token.IMPORT {
			for _, spec := range group.Specs {
				item := spec.(*ast.ImportSpec)
				if !imports[item.Path.Value] {
					newImports = append(newImports, &ast.ImportSpec{Path: &ast.BasicLit{Kind: token.STRING, Value: item.Path.Value}})
					imports[item.Path.Value] = true
				}
			}
			continue
		}
		base.Decls = append(base.Decls, decl)
	}
	if len(newImports) > 0 {
		base.Decls = append([]ast.Decl{&ast.GenDecl{Tok: token.IMPORT, Specs: newImports}}, base.Decls...)
	}
	var buf bytes.Buffer
	if err := format.Node(&buf, fset, base); err != nil {
		return nil, err
	}
	// AST 格式化不会修改已有 enum 的严格 Marshal/Unmarshal 逻辑。
	return format.Source(buf.Bytes())
}
