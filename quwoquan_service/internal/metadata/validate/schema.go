package validate

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

var metadataSchemaByFilename = map[string]string{
	"context.yaml":    "context.schema.json",
	"object.yaml":     "object.schema.json",
	"fields.yaml":     "fields.schema.json",
	"operations.yaml": "operations.schema.json",
	"storage.yaml":    "storage.schema.json",
	"events.yaml":     "events.schema.json",
	"errors.yaml":     "errors.schema.json",
	"privacy.yaml":    "privacy.schema.json",
}

// MetadataSchemas 使用仓库内唯一 JSON Schema 校验商用 metadata 文档。
// compiler 不读取旧格式，也不保留版本目录或迁移兼容分支。
func MetadataSchemas(metadataDir string) ([]Issue, error) {
	compiled, err := compileMetadataSchemas(metadataDir)
	if err != nil {
		return nil, err
	}

	var issues []Issue
	err = filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if path == metadataDir {
				return nil
			}
			name := entry.Name()
			if name == ".git" || name == "test_fixtures" || strings.HasPrefix(name, "_") {
				return filepath.SkipDir
			}
			return nil
		}

		schemaName, ok := metadataSchemaByFilename[entry.Name()]
		if !ok {
			return nil
		}
		// Object packet files are schemas only inside an actual object root. A
		// same-named helper/type document elsewhere must not become a second
		// implicit object registration.
		if entry.Name() != "context.yaml" && entry.Name() != "object.yaml" {
			if _, statErr := os.Stat(filepath.Join(filepath.Dir(path), "object.yaml")); statErr != nil {
				return nil
			}
		}
		instance, decodeErr := decodeYAMLAsJSON(path)
		if decodeErr != nil {
			return decodeErr
		}
		if validateErr := compiled[schemaName].Validate(instance); validateErr != nil {
			sourcePath := relativeMetadataPath(metadataDir, path)
			issues = append(issues, schemaValidationIssues(sourcePath, validateErr)...)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	redisIssues, err := storageRedisSceneIssues(metadataDir)
	if err != nil {
		return nil, err
	}
	issues = append(issues, redisIssues...)
	sortIssues(issues)
	return issues, nil
}

// ContractGraphSchema 反证 compiler 输出仍符合 canonical graph schema。
func ContractGraphSchema(metadataDir string, contractGraph any) error {
	schemaPath := filepath.Join(metadataDir, "_schemas", "contract_graph.schema.json")
	compiler := jsonschema.NewCompiler()
	schema, err := compiler.Compile(schemaPath)
	if err != nil {
		return fmt.Errorf("compile ContractGraph schema: %w", err)
	}
	instance, err := normalizeJSONValue(contractGraph)
	if err != nil {
		return fmt.Errorf("normalize ContractGraph: %w", err)
	}
	if err := schema.Validate(instance); err != nil {
		return fmt.Errorf("validate ContractGraph schema: %w", err)
	}
	return nil
}

func compileMetadataSchemas(metadataDir string) (map[string]*jsonschema.Schema, error) {
	result := make(map[string]*jsonschema.Schema, len(metadataSchemaByFilename))
	schemaRoot := filepath.Join(metadataDir, "_schemas")
	for _, schemaName := range metadataSchemaByFilename {
		if _, exists := result[schemaName]; exists {
			continue
		}
		schemaPath := filepath.Join(schemaRoot, schemaName)
		compiler := jsonschema.NewCompiler()
		schema, err := compiler.Compile(schemaPath)
		if err != nil {
			return nil, fmt.Errorf("compile metadata schema %s: %w", schemaName, err)
		}
		result[schemaName] = schema
	}
	return result, nil
}

func decodeYAMLAsJSON(path string) (any, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var value any
	if err := yaml.Unmarshal(data, &value); err != nil {
		return nil, fmt.Errorf("%s: decode YAML: %w", path, err)
	}
	normalized, err := normalizeJSONValue(value)
	if err != nil {
		return nil, fmt.Errorf("%s: normalize YAML as JSON: %w", path, err)
	}
	return normalized, nil
}

func normalizeJSONValue(value any) (any, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var normalized any
	if err := json.Unmarshal(data, &normalized); err != nil {
		return nil, err
	}
	return normalized, nil
}

func schemaValidationIssues(sourcePath string, validationErr error) []Issue {
	var root *jsonschema.ValidationError
	if !errors.As(validationErr, &root) {
		return []Issue{issue(
			"CONTRACT.SCHEMA.INVALID",
			sourcePath,
			"%s", validationErr,
		)}
	}

	leaves := validationLeaves(root)
	issues := make([]Issue, 0, len(leaves))
	for _, leaf := range leaves {
		location := "/"
		if len(leaf.InstanceLocation) > 0 {
			location += strings.Join(leaf.InstanceLocation, "/")
		}
		detail := "schema validation failed"
		if output := leaf.BasicOutput(); output.Error != nil {
			detail = output.Error.String()
		}
		issues = append(issues, issue(
			"CONTRACT.SCHEMA.INVALID",
			sourcePath,
			"%s: %s", location, detail,
		))
	}
	return issues
}

func validationLeaves(root *jsonschema.ValidationError) []*jsonschema.ValidationError {
	if len(root.Causes) == 0 {
		return []*jsonschema.ValidationError{root}
	}
	var leaves []*jsonschema.ValidationError
	for _, cause := range root.Causes {
		leaves = append(leaves, validationLeaves(cause)...)
	}
	return leaves
}

func relativeMetadataPath(root, path string) string {
	relative, err := filepath.Rel(root, path)
	if err != nil {
		return filepath.ToSlash(path)
	}
	return filepath.ToSlash(relative)
}

func sortIssues(issues []Issue) {
	sort.Slice(issues, func(i, j int) bool {
		if issues[i].Code != issues[j].Code {
			return issues[i].Code < issues[j].Code
		}
		if issues[i].SourcePath != issues[j].SourcePath {
			return issues[i].SourcePath < issues[j].SourcePath
		}
		return issues[i].Message < issues[j].Message
	})
}
