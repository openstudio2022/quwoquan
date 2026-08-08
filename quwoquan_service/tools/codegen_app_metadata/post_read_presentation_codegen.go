package main

import (
	"fmt"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

type readPresentationSurfacesFile struct {
	Version      int    `yaml:"version"`
	DartEnumName string `yaml:"dart_enum_name"`
	Surfaces     []struct {
		DartMember  string `yaml:"dart_member"`
		Description string `yaml:"description"`
	} `yaml:"surfaces"`
}

type articleDetailWireKeysFile struct {
	Version     int    `yaml:"version"`
	DartClass   string `yaml:"wire_keys_class"`
	Description string `yaml:"description"`
	Keys        []struct {
		ConstName string `yaml:"const_name"`
		JSONKey   string `yaml:"json_key"`
	} `yaml:"keys"`
}

func renderPostReadSurfaceIdDart(yamlBytes []byte) (string, error) {
	var f readPresentationSurfacesFile
	if err := yaml.Unmarshal(yamlBytes, &f); err != nil {
		return "", err
	}
	enumName := f.DartEnumName
	if enumName == "" {
		enumName = "PostReadSurfaceId"
	}
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Source: services/content-service/contracts/content/post/projections/read_presentation_surfaces.yaml\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")
	b.WriteString("/// 帖子只读投影所挂靠的 UI 表面（与 post-projection-pipeline-inventory / gap 清单一致）。\n")
	fmt.Fprintf(&b, "enum %s {\n", enumName)
	for _, s := range f.Surfaces {
		if s.DartMember == "" {
			continue
		}
		if s.Description != "" {
			fmt.Fprintf(&b, "  /// %s\n", strings.TrimSpace(s.Description))
		}
		fmt.Fprintf(&b, "  %s,\n", s.DartMember)
	}
	b.WriteString("}\n")
	return b.String(), nil
}

func renderWireKeysClassDart(yamlBytes []byte, sourceRelPath string) (string, error) {
	var f articleDetailWireKeysFile
	if err := yaml.Unmarshal(yamlBytes, &f); err != nil {
		return "", err
	}
	class := f.DartClass
	if class == "" {
		class = "ArticleDetailWireKeys"
	}
	desc := strings.TrimSpace(f.Description)
	if desc == "" {
		desc = "Wire JSON 键名 SSOT（metadata projections）。"
	}
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	fmt.Fprintf(&b, "// Source: %s\n", sourceRelPath)
	b.WriteString("// Regenerate: make codegen-app\n\n")
	fmt.Fprintf(&b, "/// %s\n", desc)
	fmt.Fprintf(&b, "abstract final class %s {\n", class)
	fmt.Fprintf(&b, "  const %s._();\n", class)
	for _, k := range f.Keys {
		if k.ConstName == "" || k.JSONKey == "" {
			continue
		}
		fmt.Fprintf(&b, "\n  static const String %s = '%s';\n", k.ConstName, k.JSONKey)
	}
	b.WriteString("}\n")
	return b.String(), nil
}

func writeWireKeysGeneratedFile(appDir, postProjectionsDir, yamlName, outName string) error {
	keysPath := filepath.Join(postProjectionsDir, yamlName)
	keysBytes, err := readMetadataDocument(keysPath)
	if err != nil {
		return err
	}
	sourceRel := filepath.ToSlash(filepath.Join("services/content-service/contracts/content/post/projections", yamlName))
	out, err := renderWireKeysClassDart(keysBytes, sourceRel)
	if err != nil {
		return err
	}
	writeFile(
		contentPostAdaptersOutputPath(appDir, outName),
		out,
	)
	return nil
}

func readWireKeysFile(postProjectionsDir, yamlName string) (*articleDetailWireKeysFile, error) {
	keysBytes, err := readMetadataDocument(filepath.Join(postProjectionsDir, yamlName))
	if err != nil {
		return nil, err
	}
	var file articleDetailWireKeysFile
	if err := yaml.Unmarshal(keysBytes, &file); err != nil {
		return nil, err
	}
	return &file, nil
}

func requiredWireKey(
	file *articleDetailWireKeysFile,
	constName string,
) (string, error) {
	for _, key := range file.Keys {
		if key.ConstName == constName && strings.TrimSpace(key.JSONKey) != "" {
			return strings.TrimSpace(key.JSONKey), nil
		}
	}
	return "", fmt.Errorf(
		"wire key %q is required by the Content Media public seam",
		constName,
	)
}

func writeContentMediaPostProjectionKeys(
	appDir,
	postProjectionsDir string,
) error {
	articleKeys, err := readWireKeysFile(
		postProjectionsDir,
		"article_detail_wire_keys.yaml",
	)
	if err != nil {
		return err
	}
	immersiveKeys, err := readWireKeysFile(
		postProjectionsDir,
		"content_post_immersive_wire_keys.yaml",
	)
	if err != nil {
		return err
	}
	required := []struct {
		member string
		source *articleDetailWireKeysFile
	}{
		{member: "articleMarkdown", source: articleKeys},
		{member: "coverUrl", source: articleKeys},
		{member: "description", source: immersiveKeys},
		{member: "content", source: immersiveKeys},
		{member: "caption", source: immersiveKeys},
		{member: "visibility", source: immersiveKeys},
	}
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Sources: content/post/projections/article_detail_wire_keys.yaml, content_post_immersive_wire_keys.yaml\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")
	b.WriteString("/// Media Asset 消费 Post 投影时使用的最小稳定键集合。\n")
	b.WriteString("abstract final class ContentMediaPostProjectionKeys {\n")
	b.WriteString("  const ContentMediaPostProjectionKeys._();\n")
	for _, key := range required {
		value, err := requiredWireKey(key.source, key.member)
		if err != nil {
			return err
		}
		fmt.Fprintf(
			&b,
			"\n  static const String %s = '%s';\n",
			key.member,
			value,
		)
	}
	b.WriteString("}\n")
	writeFile(
		contentPostPublicGeneratedOutputPath(
			appDir,
			"content_media_post_projection_keys.g.dart",
		),
		b.String(),
	)
	return nil
}

func writePostReadPresentationArtifacts(appDir, postProjectionsDir string) error {
	surfPath := filepath.Join(postProjectionsDir, "read_presentation_surfaces.yaml")
	surfBytes, err := readMetadataDocument(surfPath)
	if err != nil {
		return err
	}
	surfOut, err := renderPostReadSurfaceIdDart(surfBytes)
	if err != nil {
		return err
	}
	writeFile(
		contentPostPresentationOutputPath(
			appDir,
			"post_read_surface_id.g.dart",
		),
		surfOut,
	)

	if err := writeWireKeysGeneratedFile(
		appDir,
		postProjectionsDir,
		"article_detail_wire_keys.yaml",
		"article_detail_wire_keys.g.dart",
	); err != nil {
		return err
	}
	if err := writeContentMediaPostProjectionKeys(
		appDir,
		postProjectionsDir,
	); err != nil {
		return err
	}

	return nil
}
