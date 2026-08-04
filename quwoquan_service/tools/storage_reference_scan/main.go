package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type reference struct {
	Kind   string `json:"kind"`
	Name   string `json:"name"`
	Path   string `json:"path"`
	Access string `json:"access"`
}

type parsedFile struct {
	path      string
	relative  string
	directory string
	packageID string
	file      *ast.File
}

type packageConstants map[string]ast.Expr

func main() {
	var repositoryRoot string
	flag.StringVar(&repositoryRoot, "repo-root", "..", "repository root")
	flag.Parse()
	repositoryRoot, err := filepath.Abs(repositoryRoot)
	if err != nil {
		exitErr(err)
	}
	servicesRoot := filepath.Join(repositoryRoot, "quwoquan_service", "services")
	files, constants, err := parseProductionFiles(repositoryRoot, servicesRoot)
	if err != nil {
		exitErr(err)
	}
	seen := map[reference]struct{}{}
	for _, source := range files {
		scanFile(source, constants[source.packageID], seen)
	}
	result := make([]reference, 0, len(seen))
	for item := range seen {
		result = append(result, item)
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].Kind != result[j].Kind {
			return result[i].Kind < result[j].Kind
		}
		if result[i].Name != result[j].Name {
			return result[i].Name < result[j].Name
		}
		if result[i].Path != result[j].Path {
			return result[i].Path < result[j].Path
		}
		return result[i].Access < result[j].Access
	})
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		exitErr(err)
	}
}

func parseProductionFiles(repositoryRoot, servicesRoot string) ([]parsedFile, map[string]packageConstants, error) {
	fset := token.NewFileSet()
	var files []parsedFile
	constants := map[string]packageConstants{}
	err := filepath.WalkDir(servicesRoot, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			switch entry.Name() {
			case "tests", "test", "generated", "contracts", "vendor":
				if path != servicesRoot {
					return filepath.SkipDir
				}
			}
			return nil
		}
		if filepath.Ext(path) != ".go" || strings.HasSuffix(path, "_test.go") {
			return nil
		}
		parsed, err := parser.ParseFile(fset, path, nil, 0)
		if err != nil {
			return fmt.Errorf("parse %s: %w", path, err)
		}
		relative, err := filepath.Rel(repositoryRoot, path)
		if err != nil {
			return err
		}
		directory := filepath.Dir(path)
		packageID := directory + "\x00" + parsed.Name.Name
		item := parsedFile{
			path:      path,
			relative:  filepath.ToSlash(relative),
			directory: directory,
			packageID: packageID,
			file:      parsed,
		}
		files = append(files, item)
		if constants[packageID] == nil {
			constants[packageID] = packageConstants{}
		}
		collectConstants(parsed, constants[packageID])
		return nil
	})
	return files, constants, err
}

func collectConstants(file *ast.File, constants packageConstants) {
	for _, declaration := range file.Decls {
		if function, ok := declaration.(*ast.FuncDecl); ok {
			if function.Recv != nil || function.Body == nil || len(function.Body.List) != 1 {
				continue
			}
			result, ok := function.Body.List[0].(*ast.ReturnStmt)
			if !ok || len(result.Results) != 1 {
				continue
			}
			// Storage identities are commonly centralized in a package-local key
			// helper (for example `otpQuotaKey(phone)`).  Retain the single return
			// expression so calls to that helper cannot escape the AST gate.
			constants[function.Name.Name] = result.Results[0]
			continue
		}
		general, ok := declaration.(*ast.GenDecl)
		if !ok || (general.Tok != token.CONST && general.Tok != token.VAR) {
			continue
		}
		for _, spec := range general.Specs {
			values, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			for index, name := range values.Names {
				if index < len(values.Values) {
					constants[name.Name] = values.Values[index]
				}
			}
		}
	}
}

func scanFile(source parsedFile, constants packageConstants, seen map[reference]struct{}) {
	add := func(kind, name, access string) {
		name = strings.TrimSpace(name)
		if name != "" {
			seen[reference{Kind: kind, Name: name, Path: source.relative, Access: access}] = struct{}{}
		}
	}
	fileContainsLookup := false
	ast.Inspect(source.file, func(node ast.Node) bool {
		literal, ok := node.(*ast.BasicLit)
		if !ok || literal.Kind != token.STRING {
			return true
		}
		value, err := strconv.Unquote(literal.Value)
		if err == nil && value == "$lookup" {
			fileContainsLookup = true
		}
		return true
	})
	ast.Inspect(source.file, func(node ast.Node) bool {
		call, ok := node.(*ast.CallExpr)
		if ok {
			selector, selectorOK := call.Fun.(*ast.SelectorExpr)
			if selectorOK {
				switch selector.Sel.Name {
				case "Collection", "GetCollection":
					if len(call.Args) > 0 {
						if value, resolved := evalString(call.Args[0], constants, nil); resolved {
							add("collection", value, "read_write")
						}
					}
				case "XAdd", "XDel", "XTrimMaxLen", "XTrimMinID", "XTrimOlderThan",
					"XAck", "XAutoClaim", "XClaim", "XGroupCreate",
					"XGroupCreateMkStream", "XPending", "XPendingCount", "XRead", "XReadGroup":
					access := "read"
					if selector.Sel.Name == "XAdd" || selector.Sel.Name == "XDel" ||
						selector.Sel.Name == "XTrimMaxLen" || selector.Sel.Name == "XTrimMinID" ||
						selector.Sel.Name == "XTrimOlderThan" {
						access = "write"
					}
					for _, argument := range call.Args {
						if value, resolved := evalString(argument, constants, nil); resolved && strings.HasPrefix(value, "events.") {
							add("stream", value, access)
						}
					}
				case "Get", "GetBytes", "GetDel", "Set", "SetBytes", "SetNX", "Del", "Incr", "Expire",
					"HGet", "HSet", "HDel", "HGetAll", "HIncrByFloat",
					"SAdd", "SRem", "SMembers", "SIsMember",
					"ZAdd", "ZRangeByScore", "ZRem", "ZCard":
					for _, argument := range call.Args {
						if value, resolved := evalString(argument, constants, nil); resolved && isRedisKey(value) {
							add("redis_key", value, "read_write")
						}
					}
				}
			}
		}
		if fileContainsLookup {
			if keyValue, ok := node.(*ast.KeyValueExpr); ok {
				if key, resolved := evalString(keyValue.Key, constants, nil); resolved && key == "from" {
					if value, valueOK := evalString(keyValue.Value, constants, nil); valueOK {
						add("collection", value, "read")
					}
				}
			}
			if composite, ok := node.(*ast.CompositeLit); ok {
				fields := map[string]string{}
				for _, element := range composite.Elts {
					keyValue, ok := element.(*ast.KeyValueExpr)
					if !ok {
						continue
					}
					identifier, ok := keyValue.Key.(*ast.Ident)
					if !ok {
						continue
					}
					if value, resolved := evalString(keyValue.Value, constants, nil); resolved {
						fields[identifier.Name] = value
					}
				}
				if fields["Key"] == "from" {
					add("collection", fields["Value"], "read")
				}
			}
		}
		return true
	})
}

func evalString(expression ast.Expr, constants packageConstants, resolving map[string]bool) (string, bool) {
	switch value := expression.(type) {
	case *ast.BasicLit:
		if value.Kind != token.STRING {
			return "", false
		}
		decoded, err := strconv.Unquote(value.Value)
		return decoded, err == nil
	case *ast.ParenExpr:
		return evalString(value.X, constants, resolving)
	case *ast.BinaryExpr:
		if value.Op != token.ADD {
			return "", false
		}
		left, leftOK := evalString(value.X, constants, resolving)
		right, rightOK := evalString(value.Y, constants, resolving)
		return left + right, leftOK && rightOK
	case *ast.Ident:
		if resolving == nil {
			resolving = map[string]bool{}
		}
		if resolving[value.Name] {
			return "", false
		}
		resolved, ok := constants[value.Name]
		if !ok {
			return "", false
		}
		resolving[value.Name] = true
		result, resultOK := evalString(resolved, constants, resolving)
		delete(resolving, value.Name)
		return result, resultOK
	case *ast.CallExpr:
		if function, ok := value.Fun.(*ast.Ident); ok {
			if resolving == nil {
				resolving = map[string]bool{}
			}
			if resolving[function.Name] {
				return "", false
			}
			resolved, exists := constants[function.Name]
			if !exists {
				return "", false
			}
			resolving[function.Name] = true
			result, resultOK := evalString(resolved, constants, resolving)
			delete(resolving, function.Name)
			return result, resultOK
		}
		selector, ok := value.Fun.(*ast.SelectorExpr)
		if !ok || selector.Sel.Name != "Sprintf" || len(value.Args) == 0 {
			return "", false
		}
		packageName, ok := selector.X.(*ast.Ident)
		if !ok || packageName.Name != "fmt" {
			return "", false
		}
		format, ok := evalString(value.Args[0], constants, resolving)
		if !ok {
			return "", false
		}
		return staticFormatPrefix(format)
	default:
		return "", false
	}
}

func staticFormatPrefix(format string) (string, bool) {
	for index := 0; index < len(format); index++ {
		if format[index] != '%' {
			continue
		}
		if index+1 < len(format) && format[index+1] == '%' {
			index++
			continue
		}
		if index == 0 {
			return "", false
		}
		return format[:index], true
	}
	return format, true
}

func isRedisKey(value string) bool {
	if strings.HasPrefix(value, "http:") || strings.HasPrefix(value, "https:") {
		return false
	}
	separator := strings.IndexByte(value, ':')
	if separator < 1 {
		return false
	}
	for index, character := range value[:separator] {
		if (character >= 'a' && character <= 'z') ||
			(index > 0 && character >= '0' && character <= '9') ||
			(index > 0 && (character == '_' || character == '-')) {
			continue
		}
		return false
	}
	return true
}

func exitErr(err error) {
	fmt.Fprintln(os.Stderr, "storage-reference-scan:", err)
	os.Exit(1)
}
