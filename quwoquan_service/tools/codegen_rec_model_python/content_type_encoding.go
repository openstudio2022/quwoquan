package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

// modelOrdinal 拒绝 YAML 对 bool、字符串和浮点数的隐式数值转换。
type modelOrdinal int

func (value *modelOrdinal) UnmarshalYAML(node *yaml.Node) error {
	if node.Kind != yaml.ScalarNode || node.Tag != "!!int" {
		return fmt.Errorf("CONTRACT.MODEL_ENCODING.INVALID: ordinal must be an integer")
	}
	var ordinal int
	if err := node.Decode(&ordinal); err != nil {
		return err
	}
	if ordinal < 0 {
		return fmt.Errorf("CONTRACT.MODEL_ENCODING.INVALID: negative ordinal")
	}
	*value = modelOrdinal(ordinal)
	return nil
}

// renderContentTypeEncoding 只读取字段的显式模型编码；合法值全集仍来自 enum_ref。
// 编码不取 enum 列表下标，避免共享枚举重排悄悄改变现有模型输入。
func renderContentTypeEncoding(source *contractcodegen.Source, owner string) (string, error) {
	path := filepath.ToSlash(filepath.Join(owner, "fields.yaml"))
	var declaration struct {
		Types map[string]struct {
			Fields []struct {
				Name     string                  `yaml:"name"`
				Type     string                  `yaml:"type"`
				EnumRef  string                  `yaml:"enum_ref"`
				Encoding map[string]modelOrdinal `yaml:"model_encoding"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	if err := source.Decode(path, &declaration); err != nil {
		return "", err
	}
	fields, err := loadFields(source, path)
	if err != nil {
		return "", err
	}
	var encoding map[string]modelOrdinal
	matches := 0
	for _, field := range declaration.Types["CandidateInput"].Fields {
		if field.Name != "contentType" {
			continue
		}
		matches++
		if field.Type != "enum" || field.EnumRef != "ContentType" {
			return "", fmt.Errorf("CONTRACT.MODEL_ENCODING.INVALID: CandidateInput.contentType must reference ContentType")
		}
		encoding = field.Encoding
	}
	values := fields.Enums["ContentType"]
	if matches != 1 || len(values) == 0 || len(encoding) != len(values) {
		return "", fmt.Errorf("CONTRACT.MODEL_ENCODING.INVALID: explicit encoding must exactly cover ContentType")
	}
	if err := validateModelOrdinals(values, encoding); err != nil {
		return "", err
	}
	ordered := append([]string(nil), values...)
	sort.Slice(ordered, func(i, j int) bool { return encoding[ordered[i]] < encoding[ordered[j]] })
	var output strings.Builder
	output.WriteString(genHeader + "# Source: " + path + "#types.CandidateInput.contentType\n")
	output.WriteString("# Legal values: _shared/types.yaml#enums.ContentType\n\nfrom types import MappingProxyType\n\n")
	output.WriteString("CONTENT_TYPE_MAP = MappingProxyType({\n")
	for _, value := range ordered {
		fmt.Fprintf(&output, "    %q: %d,\n", value, encoding[value])
	}
	output.WriteString("})\n")
	return output.String(), nil
}

func validateModelOrdinals(values []string, encoding map[string]modelOrdinal) error {
	seenValues, seenCodes := map[string]bool{}, map[modelOrdinal]bool{}
	for _, value := range values {
		code, exists := encoding[value]
		if !exists || seenValues[value] || seenCodes[code] || int(code) >= len(values) {
			return fmt.Errorf("CONTRACT.MODEL_ENCODING.INVALID: duplicate, missing or out-of-range ordinal for %s", value)
		}
		seenValues[value], seenCodes[code] = true, true
	}
	return nil
}

// writeContentTypeEncoding 由 canonical run 调用；checkGenerated 复用 run 自动核验此文件。
func writeContentTypeEncoding(source *contractcodegen.Source, owner, outputDir string) error {
	body, err := renderContentTypeEncoding(source, owner)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(outputDir, "content_type_encoding.py"), []byte(body), 0644)
}
