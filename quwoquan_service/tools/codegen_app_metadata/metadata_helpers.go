package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode"
)

func writeFile(path string, content string) {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		exitErr(err)
	}
	fmt.Printf("generated: %s\n", path)
}

func nonEmpty(v, fallback string) string {
	if strings.TrimSpace(v) == "" {
		return fallback
	}
	return v
}

func dartStringLiteral(v string) string {
	return fmt.Sprintf("%q", v)
}

func dartStringOrNull(v string) string {
	if strings.TrimSpace(v) == "" {
		return "null"
	}
	return dartStringLiteral(v)
}

func dartDoubleLiteral(v float64, fallback float64) string {
	if v <= 0 {
		v = fallback
	}
	return strconv.FormatFloat(v, 'f', -1, 64)
}

func writeSortedMap[T ~string](b *strings.Builder, m map[string]T) {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		b.WriteString(fmt.Sprintf("    '%s': %s,\n", k, m[k]))
	}
}

func writeSortedStringMap(b *strings.Builder, m map[string]string) {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		b.WriteString(fmt.Sprintf("    '%s': '%s',\n", k, m[k]))
	}
}

func extractPathParams(path string) []string {
	start := -1
	params := []string{}
	for i, r := range path {
		switch r {
		case '{':
			start = i + 1
		case '}':
			if start > 0 && start <= i {
				params = append(params, path[start:i])
			}
			start = -1
		}
	}
	return params
}

func collectRoutePrefixes(routes []routeDef) []string {
	seen := map[string]bool{}
	prefixes := []string{}
	for _, route := range routes {
		parts := strings.Split(strings.Trim(route.Path, "/"), "/")
		if len(parts) < 2 {
			continue
		}
		prefix := "/" + parts[0] + "/" + parts[1]
		if seen[prefix] {
			continue
		}
		seen[prefix] = true
		prefixes = append(prefixes, prefix)
	}
	sort.Strings(prefixes)
	return prefixes
}

func routeSegment(path string) string {
	trimmed := strings.Trim(path, "/")
	if trimmed == "" {
		return ""
	}
	parts := strings.Split(trimmed, "/")
	return parts[len(parts)-1]
}

func toDartExportedName(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == '_' || r == '-' || r == '/' || r == ' '
	})
	var b strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		lower := strings.ToLower(part)
		b.WriteString(strings.ToUpper(lower[:1]))
		if len(lower) > 1 {
			b.WriteString(lower[1:])
		}
	}
	return b.String()
}

func lowerCamel(value string) string {
	parts := splitCamelCase(value)
	if len(parts) == 0 {
		return value
	}
	var b strings.Builder
	for idx, part := range parts {
		lower := strings.ToLower(part)
		if idx == 0 {
			b.WriteString(lower)
			continue
		}
		b.WriteString(strings.ToUpper(lower[:1]))
		if len(lower) > 1 {
			b.WriteString(lower[1:])
		}
	}
	return b.String()
}

func toDartValueName(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == '_' || r == '-' || r == '/' || r == ' ' || r == '.'
	})
	if len(parts) == 0 {
		return "value"
	}
	var b strings.Builder
	for idx, part := range parts {
		if part == "" {
			continue
		}
		lower := strings.ToLower(part)
		if idx == 0 {
			b.WriteString(lower)
			continue
		}
		b.WriteString(strings.ToUpper(lower[:1]))
		if len(lower) > 1 {
			b.WriteString(lower[1:])
		}
	}
	name := b.String()
	if name == "" {
		return "value"
	}
	first := rune(name[0])
	if first >= '0' && first <= '9' {
		return "v" + name
	}
	return name
}

func toDartFieldName(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return "field"
	}
	var b strings.Builder
	upperNext := false
	wroteAny := false
	for _, r := range trimmed {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			if !wroteAny {
				b.WriteRune(unicode.ToLower(r))
				wroteAny = true
				upperNext = false
				continue
			}
			if upperNext {
				b.WriteRune(unicode.ToUpper(r))
				upperNext = false
				continue
			}
			b.WriteRune(r)
			continue
		}
		if wroteAny {
			upperNext = true
		}
	}
	name := b.String()
	if name == "" {
		return "field"
	}
	first := rune(name[0])
	if first >= '0' && first <= '9' {
		return "f" + name
	}
	return name
}

func splitCamelCase(value string) []string {
	if value == "" {
		return nil
	}
	var parts []string
	var current strings.Builder
	for idx, r := range value {
		if idx > 0 && r >= 'A' && r <= 'Z' && current.Len() > 0 {
			parts = append(parts, current.String())
			current.Reset()
		}
		current.WriteRune(r)
	}
	if current.Len() > 0 {
		parts = append(parts, current.String())
	}
	return parts
}

func resolvePageID(domain string, operation string) string {
	if opMap, ok := sharedRequestContext.DomainOperationPageIDs[domain]; ok {
		if pageID, ok := opMap[operation]; ok {
			return pageID
		}
	}
	parts := splitCamelCase(operation)
	if len(parts) == 0 {
		return domain + "." + strings.ToLower(operation)
	}
	lowered := make([]string, 0, len(parts)+1)
	lowered = append(lowered, domain)
	for _, part := range parts {
		lowered = append(lowered, strings.ToLower(part))
	}
	return strings.Join(lowered, ".")
}

func escapeDartString(value string) string {
	return strings.ReplaceAll(value, "'", "\\'")
}

func renderStringListLiteral(items []string) string {
	if len(items) == 0 {
		return "const <String>[]"
	}
	var b strings.Builder
	b.WriteString("<String>[")
	for idx, item := range items {
		if idx > 0 {
			b.WriteString(", ")
		}
		b.WriteString(fmt.Sprintf("'%s'", escapeDartString(item)))
	}
	b.WriteString("]")
	return b.String()
}

func renderSearchNamedValuesLiteral(items []searchNamedValueDef) string {
	if len(items) == 0 {
		return "const <String>[]"
	}
	values := make([]string, 0, len(items))
	for _, item := range items {
		if strings.TrimSpace(item.ID) == "" {
			continue
		}
		values = append(values, item.ID)
	}
	return renderStringListLiteral(values)
}

func mergeUniqueStringLists(lists ...[]string) []string {
	out := make([]string, 0)
	seen := make(map[string]struct{})
	for _, list := range lists {
		for _, item := range list {
			trimmed := strings.TrimSpace(item)
			if trimmed == "" {
				continue
			}
			if _, exists := seen[trimmed]; exists {
				continue
			}
			seen[trimmed] = struct{}{}
			out = append(out, trimmed)
		}
	}
	return out
}

func renderSearchObjectTypesLiteral(items []string) string {
	if len(items) == 0 {
		return "const <SearchObjectType>[]"
	}
	var b strings.Builder
	b.WriteString("<SearchObjectType>[")
	for idx, item := range items {
		if idx > 0 {
			b.WriteString(", ")
		}
		b.WriteString(fmt.Sprintf("SearchObjectType.%s", toDartValueName(item)))
	}
	b.WriteString("]")
	return b.String()
}

// ── new cross-cutting readers ─────────────────────────────────────────────────

func toGoExportedName(s string) string {
	if s == "" {
		return ""
	}
	return strings.ToUpper(s[:1]) + s[1:]
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_app_metadata error: %v\n", err)
	os.Exit(1)
}
