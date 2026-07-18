package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

func readShared(path string) (*sharedTypes, error) {
	var parsed sharedTypes
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readFields(path string) (*fieldsFile, error) {
	var parsed fieldsFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readService(path string) (*serviceFile, error) {
	var parsed serviceFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readIntegrationLocationService(path string) (*integrationLocationServiceFile, error) {
	var parsed integrationLocationServiceFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readProjection(path string) (*projectionFile, error) {
	var parsed projectionFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return &parsed, err
	}
	if externalPath := strings.TrimSpace(parsed.ClientProjection.ExternalDartPath); externalPath != "" {
		if strings.TrimSpace(parsed.ClientProjection.DartClass) == "" {
			return &parsed, fmt.Errorf(
				"%s client_projection.external_dart_path requires dart_class",
				path,
			)
		}
		return &parsed, nil
	}
	if len(parsed.ClientProjection.Fields) == 0 {
		parsed.ClientProjection.Fields = append(
			[]projectionFieldDef(nil),
			parsed.Fields...,
		)
		for index := range parsed.ClientProjection.Fields {
			field := &parsed.ClientProjection.Fields[index]
			field.Source = field.Name
			if strings.TrimSpace(field.DartType) == "" {
				dartType, err := projectionWireTypeToDart(field.WireType)
				if err != nil {
					return &parsed, fmt.Errorf(
						"%s field %s: %w",
						path,
						field.Name,
						err,
					)
				}
				field.DartType = dartType
			}
		}
	}
	return &parsed, nil
}

func readProjectionBinding(path string) (*projectionBinding, error) {
	var parsed projectionBinding
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return &parsed, err
	}
	if externalPath := strings.TrimSpace(parsed.ClientProjection.ExternalDartPath); externalPath != "" &&
		strings.TrimSpace(parsed.ClientProjection.DartClass) == "" {
		return &parsed, fmt.Errorf(
			"%s client_projection.external_dart_path requires dart_class",
			path,
		)
	}
	return &parsed, nil
}

func projectionWireTypeToDart(raw string) (string, error) {
	switch strings.TrimSpace(raw) {
	case "string", "enum", "date", "time", "tag_ref":
		return "String", nil
	case "timestamp", "datetime":
		return "DateTime", nil
	case "int", "int32", "int64":
		return "int", nil
	case "float", "double", "number":
		return "double", nil
	case "bool", "boolean":
		return "bool", nil
	case "[]string", "string[]":
		return "List<String>", nil
	case "map", "json", "object":
		return "Map<String, dynamic>", nil
	default:
		return "", fmt.Errorf("unsupported projection wire type %q", raw)
	}
}

// collectProjectionReadModelDartClass 建立 projection read_model -> client_projection.dart_class
// 的全仓索引（跨域可见），供 operation response_body 解析其端侧 DTO 类名。
// 同时把 dart_class 自身登记为键，兼容 response_body 直接写 dart_class 的情况。
func collectProjectionReadModelDartClass(metadataDir string) (map[string]string, error) {
	index := map[string]string{}
	for _, path := range metadataDocumentPaths("", ".yaml") {
		if filepath.Base(filepath.Dir(path)) != "projections" {
			continue
		}
		p, readErr := readProjectionBinding(path)
		if readErr != nil {
			continue
		}
		dartClass := strings.TrimSpace(p.ClientProjection.DartClass)
		if dartClass == "" {
			continue
		}
		if rm := strings.TrimSpace(p.ReadModel); rm != "" {
			index[rm] = dartClass
		}
		index[dartClass] = dartClass
	}
	return index, nil
}

// ── builders ──────────────────────────────────────────────────────────────────

func collectDomainServiceRoutes(metadataDir string) (map[string][]routeDef, error) {
	grouped := map[string][]routeDef{}
	seen := map[string]bool{}
	for _, path := range metadataDocumentPaths("", "/service.yaml") {
		service, readErr := readService(path)
		if readErr != nil {
			return nil, readErr
		}
		domain := strings.TrimSpace(service.Service.Domain)
		if domain == "" {
			continue
		}
		for _, route := range service.APIRoutes {
			if strings.TrimSpace(route.Operation) == "" || strings.TrimSpace(route.Path) == "" {
				continue
			}
			key := domain + ":" + route.Operation
			if seen[key] {
				continue
			}
			seen[key] = true
			grouped[domain] = append(grouped[domain], route)
		}
	}
	for domain := range grouped {
		sort.Slice(grouped[domain], func(i, j int) bool {
			return grouped[domain][i].Operation < grouped[domain][j].Operation
		})
	}
	return grouped, nil
}

func readErrors(path string) (*errorsFile, error) {
	var parsed errorsFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readMergedErrors(paths []string) (*errorsFile, error) {
	merged := &errorsFile{}
	for _, path := range paths {
		ef, err := readErrors(path)
		if err != nil {
			return nil, err
		}
		if merged.Domain == "" {
			merged.Domain = ef.Domain
		}
		merged.Errors = append(merged.Errors, ef.Errors...)
	}
	return merged, nil
}

func readUserDomainErrors(metadataDir string) (*errorsFile, error) {
	root := filepath.Join(metadataDir, "user")
	paths := metadataDocumentPaths("user", "/errors.yaml")
	sort.Strings(paths)
	if len(paths) == 0 {
		return nil, fmt.Errorf("no user errors metadata found under %s", root)
	}
	return readMergedErrors(paths)
}

func readBehaviors(path string) (*behaviorsFile, error) {
	var parsed behaviorsFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readPrivacy(path string) (*privacyFile, error) {
	var parsed privacyFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readUIConfig(path string) (*uiConfigFile, error) {
	var parsed uiConfigFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readRequestContext(path string) (*requestContextFile, error) {
	var parsed requestContextFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readAppRoutes(path string) (*appRoutesFile, error) {
	var parsed appRoutesFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readUISurfaces(path string) (*uiSurfacesFile, error) {
	var parsed uiSurfacesFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readAppPages(path string) (*appPagesFile, error) {
	var parsed appPagesFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readTelemetryEventCatalog(path string) (*telemetryEventCatalogFile, error) {
	var parsed telemetryEventCatalogFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readSearchContract(path string) (*searchContractFile, error) {
	var parsed searchContractFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readSearchObjects(path string) (*searchObjectsFile, error) {
	var parsed searchObjectsFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

// ── new cross-cutting renderers ───────────────────────────────────────────────
