package storagecontract

import (
	"fmt"
	goast "go/ast"
	"go/parser"
	"go/token"
	"strconv"
	"strings"
)

func goSourceScopes(path string, data []byte) ([]sourceScope, error) {
	fileSet := token.NewFileSet()
	parsed, err := parser.ParseFile(fileSet, path, data, parser.SkipObjectResolution)
	if err != nil {
		return nil, fmt.Errorf("parse production Go source %s: %w", path, err)
	}
	tokenFile := fileSet.File(parsed.Pos())
	if tokenFile == nil {
		return nil, fmt.Errorf("parse production Go source %s: token file missing", path)
	}
	result := make([]sourceScope, 0, len(parsed.Decls))
	for _, declaration := range parsed.Decls {
		if generated, ok := declaration.(*goast.GenDecl); ok {
			start := tokenFile.Offset(generated.Pos())
			end := tokenFile.Offset(generated.End())
			if start < 0 || end < start || end > len(data) {
				return nil, fmt.Errorf("parse production Go source %s: invalid declaration offsets", path)
			}
			text := strings.ToLower(string(data[start:end]))
			literalText := goNodeLiteralText(generated)
			for _, specification := range generated.Specs {
				value, ok := specification.(*goast.ValueSpec)
				if !ok {
					continue
				}
				for _, name := range value.Names {
					result = append(result, sourceScope{
						name: name.Name, text: text, tokens: semanticTokens(literalText),
						createsIndex: hasAnyMarker(literalText, indexCreationMarkers),
						queriesStore: hasAnyMarker(literalText, indexUsageMarkers),
						indexKeySets: extractTextIndexKeySets(literalText),
					})
				}
			}
			continue
		}
		function, ok := declaration.(*goast.FuncDecl)
		if !ok || function.Body == nil {
			continue
		}
		start := tokenFile.Offset(function.Pos())
		end := tokenFile.Offset(function.End())
		if start < 0 || end < start || end > len(data) {
			return nil, fmt.Errorf("parse production Go source %s: invalid function offsets", path)
		}
		text := strings.ToLower(string(data[start:end]))
		scope := sourceScope{
			name: function.Name.Name, text: text, tokens: map[string]struct{}{}, references: map[string]struct{}{},
			storeBindings: map[string]map[string]struct{}{},
		}
		var literalText strings.Builder
		goast.Inspect(function.Body, func(node goast.Node) bool {
			if identifier, ok := node.(*goast.Ident); ok {
				if canonical := canonicalStorageKey(identifier.Name); canonical != "" {
					scope.tokens[canonical] = struct{}{}
					scope.references[canonical] = struct{}{}
				}
			}
			if literal, ok := node.(*goast.BasicLit); ok && literal.Kind == token.STRING {
				value, unquoteErr := strconv.Unquote(literal.Value)
				if unquoteErr == nil {
					literalText.WriteString("\n")
					literalText.WriteString(strings.ToLower(value))
					mergeTokens(scope.tokens, semanticTokens(value))
				}
			}
			switch value := node.(type) {
			case *goast.AssignStmt:
				for index, right := range value.Rhs {
					storeName, found := mongoCollectionName(right)
					if !found || len(value.Lhs) == 0 {
						continue
					}
					leftIndex := index
					if leftIndex >= len(value.Lhs) {
						leftIndex = len(value.Lhs) - 1
					}
					recordStoreBinding(scope.storeBindings, storeName, goExpressionLastName(value.Lhs[leftIndex]))
				}
			case *goast.KeyValueExpr:
				if storeName, found := mongoCollectionName(value.Value); found {
					recordStoreBinding(scope.storeBindings, storeName, goExpressionLastName(value.Key))
				}
			}
			if composite, ok := node.(*goast.CompositeLit); ok {
				if keys := goMongoIndexKeys(composite); len(keys) > 0 {
					scope.indexKeySets = append(scope.indexKeySets, keys)
				}
				for _, path := range goBSONSemanticPaths(composite, "") {
					if canonical := canonicalStorageKey(path); canonical != "" {
						scope.tokens[canonical] = struct{}{}
					}
				}
			}
			call, ok := node.(*goast.CallExpr)
			if !ok {
				return true
			}
			name := strings.ToLower(goCallName(call.Fun))
			if last := callLastName(name); last != "" {
				scope.references[canonicalStorageKey(last)] = struct{}{}
			}
			if name == "setkeys" || strings.HasSuffix(name, ".setkeys") {
				if keys := goStringArguments(call.Args); len(keys) > 0 {
					scope.indexKeySets = append(scope.indexKeySets, keys)
				}
			}
			switch {
			case name == "createone", name == "createmany", name == "setkeys",
				strings.HasSuffix(name, ".createone"),
				strings.HasSuffix(name, ".createmany"),
				strings.HasSuffix(name, ".setkeys"):
				scope.createsIndex = true
			case isGoStorageQueryCall(name):
				scope.queriesStore = true
			}
			if strings.HasSuffix(name, ".ensureindexes") || name == "ensureindexes" {
				scope.ensureIndexes = true
			}
			return true
		})
		scope.createsIndex = scope.createsIndex || hasAnyMarker(literalText.String(), indexCreationMarkers)
		scope.queriesStore = scope.queriesStore || hasAnyMarker(literalText.String(), indexUsageMarkers)
		scope.indexKeySets = append(scope.indexKeySets, extractTextIndexKeySets(literalText.String())...)
		result = append(result, scope)
	}
	return result, nil
}

// goBSONSemanticPaths preserves nested Mongo field identity instead of
// treating an $elemMatch child as an unrelated top-level key. For example,
// bson.M{"items": bson.M{"$elemMatch": bson.M{"owner.id": value}}}
// yields both "items" and "items.owner.id". Mongo operators do not become
// path segments, and array alternatives keep their surrounding field prefix.
func goBSONSemanticPaths(literal *goast.CompositeLit, prefix string) []string {
	if literal == nil {
		return nil
	}
	var result []string
	for _, element := range literal.Elts {
		switch entry := element.(type) {
		case *goast.KeyValueExpr:
			key, ok := goStringLiteral(entry.Key)
			if !ok {
				// bson.D uses Key:/Value: fields inside an element literal.
				if nested, nestedOK := entry.Value.(*goast.CompositeLit); nestedOK {
					result = append(result, goBSONSemanticPaths(nested, prefix)...)
				}
				continue
			}
			nextPrefix := prefix
			if !strings.HasPrefix(strings.TrimSpace(key), "$") {
				nextPrefix = joinStoragePath(prefix, key)
				result = append(result, nextPrefix)
			}
			result = append(result, goBSONExpressionPaths(entry.Value, nextPrefix)...)
		case *goast.CompositeLit:
			if key, value, ok := goBSONDocumentElement(entry); ok {
				nextPrefix := prefix
				if !strings.HasPrefix(strings.TrimSpace(key), "$") {
					nextPrefix = joinStoragePath(prefix, key)
					result = append(result, nextPrefix)
				}
				result = append(result, goBSONExpressionPaths(value, nextPrefix)...)
				continue
			}
			result = append(result, goBSONSemanticPaths(entry, prefix)...)
		}
	}
	return result
}

func goBSONExpressionPaths(expression goast.Expr, prefix string) []string {
	switch value := expression.(type) {
	case *goast.CompositeLit:
		return goBSONSemanticPaths(value, prefix)
	case *goast.UnaryExpr:
		return goBSONExpressionPaths(value.X, prefix)
	default:
		return nil
	}
}

func goBSONDocumentElement(literal *goast.CompositeLit) (string, goast.Expr, bool) {
	var key string
	var value goast.Expr
	for _, element := range literal.Elts {
		entry, ok := element.(*goast.KeyValueExpr)
		if !ok {
			continue
		}
		switch strings.ToLower(goExpressionLastName(entry.Key)) {
		case "key":
			key, _ = goStringLiteral(entry.Value)
		case "value":
			value = entry.Value
		}
	}
	return key, value, strings.TrimSpace(key) != "" && value != nil
}

func goStringLiteral(expression goast.Expr) (string, bool) {
	literal, ok := expression.(*goast.BasicLit)
	if !ok || literal.Kind != token.STRING {
		return "", false
	}
	value, err := strconv.Unquote(literal.Value)
	return value, err == nil && strings.TrimSpace(value) != ""
}

func joinStoragePath(prefix, key string) string {
	prefix = strings.Trim(strings.TrimSpace(prefix), ".")
	key = strings.Trim(strings.TrimSpace(key), ".")
	if prefix == "" {
		return key
	}
	if key == "" {
		return prefix
	}
	return prefix + "." + key
}

func goMongoIndexKeys(indexModel *goast.CompositeLit) []string {
	for _, element := range indexModel.Elts {
		entry, ok := element.(*goast.KeyValueExpr)
		if !ok || !strings.EqualFold(goExpressionLastName(entry.Key), "Keys") {
			continue
		}
		keysLiteral, ok := entry.Value.(*goast.CompositeLit)
		if !ok {
			return nil
		}
		var keys []string
		for _, keyElement := range keysLiteral.Elts {
			keyDocument, ok := keyElement.(*goast.CompositeLit)
			if !ok {
				continue
			}
			for _, field := range keyDocument.Elts {
				keyValue, ok := field.(*goast.KeyValueExpr)
				if !ok || !strings.EqualFold(goExpressionLastName(keyValue.Key), "Key") {
					continue
				}
				literal, ok := keyValue.Value.(*goast.BasicLit)
				if !ok || literal.Kind != token.STRING {
					continue
				}
				value, err := strconv.Unquote(literal.Value)
				if err == nil && strings.TrimSpace(value) != "" {
					keys = append(keys, value)
				}
			}
		}
		return keys
	}
	return nil
}

func goStringArguments(arguments []goast.Expr) []string {
	var result []string
	for _, argument := range arguments {
		literal, ok := argument.(*goast.BasicLit)
		if !ok || literal.Kind != token.STRING {
			return nil
		}
		value, err := strconv.Unquote(literal.Value)
		if err != nil || strings.TrimSpace(value) == "" {
			return nil
		}
		result = append(result, value)
	}
	return result
}

func mongoCollectionName(expression goast.Expr) (string, bool) {
	call, ok := expression.(*goast.CallExpr)
	if !ok || !strings.HasSuffix(strings.ToLower(goCallName(call.Fun)), ".collection") || len(call.Args) != 1 {
		return "", false
	}
	literal, ok := call.Args[0].(*goast.BasicLit)
	if !ok || literal.Kind != token.STRING {
		return "", false
	}
	value, err := strconv.Unquote(literal.Value)
	if err != nil || strings.TrimSpace(value) == "" {
		return "", false
	}
	return value, true
}

func goExpressionLastName(expression goast.Expr) string {
	switch value := expression.(type) {
	case *goast.Ident:
		return value.Name
	case *goast.SelectorExpr:
		return value.Sel.Name
	default:
		return ""
	}
}

func recordStoreBinding(bindings map[string]map[string]struct{}, storeName, fieldName string) {
	store := canonicalStorageKey(storeName)
	field := canonicalStorageKey(fieldName)
	if store == "" || field == "" {
		return
	}
	if bindings[field] == nil {
		bindings[field] = map[string]struct{}{}
	}
	bindings[field][store] = struct{}{}
}

func goNodeLiteralText(node goast.Node) string {
	var result strings.Builder
	goast.Inspect(node, func(candidate goast.Node) bool {
		literal, ok := candidate.(*goast.BasicLit)
		if !ok || literal.Kind != token.STRING {
			return true
		}
		value, err := strconv.Unquote(literal.Value)
		if err == nil {
			result.WriteString("\n")
			result.WriteString(strings.ToLower(value))
		}
		return true
	})
	return result.String()
}

func callLastName(name string) string {
	parts := strings.Split(name, ".")
	return parts[len(parts)-1]
}

func goCallName(expression goast.Expr) string {
	switch value := expression.(type) {
	case *goast.Ident:
		return value.Name
	case *goast.SelectorExpr:
		prefix := goCallName(value.X)
		if prefix == "" {
			return value.Sel.Name
		}
		return prefix + "." + value.Sel.Name
	case *goast.CallExpr:
		return goCallName(value.Fun)
	case *goast.IndexExpr:
		return goCallName(value.X)
	case *goast.IndexListExpr:
		return goCallName(value.X)
	default:
		return ""
	}
}

func isGoStorageQueryCall(name string) bool {
	for _, suffix := range []string{
		"find", "findone", "findoneandupdate", "aggregate", "countdocuments", "distinct",
		"updateone", "updatemany", "replaceone", "deleteone", "deletemany",
		"query", "queryrow", "queryrowx", "select", "get", "exec",
	} {
		if name == suffix || strings.HasSuffix(name, "."+suffix) {
			return true
		}
	}
	return false
}
