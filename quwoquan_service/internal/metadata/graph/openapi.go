package graph

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

type OpenAPITransport struct {
	Method     string
	Path       string
	SourcePath string
}

// OpenAPITransports 从图内嵌 OpenAPI 快照提取公开 transport。
func (g *ContractGraph) OpenAPITransports() ([]OpenAPITransport, error) {
	var transports []OpenAPITransport
	for _, document := range g.Documents {
		if !strings.HasSuffix(document.Path, "/openapi.yaml") ||
			strings.HasPrefix(document.Path, "_shared/") {
			continue
		}
		var snapshot struct {
			Paths map[string]map[string]json.RawMessage `json:"paths"`
		}
		if err := json.Unmarshal(document.Content, &snapshot); err != nil {
			return nil, fmt.Errorf(
				"decode OpenAPI snapshot %s: %w",
				document.Path,
				err,
			)
		}
		for path, operations := range snapshot.Paths {
			for method := range operations {
				normalizedMethod := strings.ToUpper(method)
				if !isOpenAPIMethod(normalizedMethod) {
					continue
				}
				transports = append(transports, OpenAPITransport{
					Method:     normalizedMethod,
					Path:       path,
					SourcePath: document.Path,
				})
			}
		}
	}
	sort.Slice(transports, func(i, j int) bool {
		left := transports[i].Method + " " + transports[i].Path
		right := transports[j].Method + " " + transports[j].Path
		if left == right {
			return transports[i].SourcePath < transports[j].SourcePath
		}
		return left < right
	})
	return transports, nil
}

func isOpenAPIMethod(method string) bool {
	switch method {
	case "GET", "POST", "PUT", "PATCH", "DELETE":
		return true
	default:
		return false
	}
}
