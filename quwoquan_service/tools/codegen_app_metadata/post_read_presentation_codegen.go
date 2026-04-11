package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

type readPresentationSurfacesFile struct {
	Version      int `yaml:"version"`
	DartEnumName string `yaml:"dart_enum_name"`
	Surfaces     []struct {
		DartMember  string `yaml:"dart_member"`
		Description string `yaml:"description"`
	} `yaml:"surfaces"`
}

type articleDetailWireKeysFile struct {
	Version     int    `yaml:"version"`
	DartClass   string `yaml:"dart_class"`
	Description string `yaml:"description"`
	Keys        []struct {
		ConstName string `yaml:"const_name"`
		JSONKey   string `yaml:"json_key"`
	} `yaml:"keys"`
}

type readPresentationProjectionFile struct {
	Version   int `yaml:"version"`
	DartClass string `yaml:"dart_class"`
	Fields []struct {
		Name     string `yaml:"name"`
		DartType string `yaml:"dart_type"`
		PostBase string `yaml:"post_base"`
		WireKey  string `yaml:"wire_key"`
	} `yaml:"fields"`
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
	b.WriteString("// Source: contracts/metadata/content/post/projections/read_presentation_surfaces.yaml\n")
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
	keysBytes, err := os.ReadFile(keysPath)
	if err != nil {
		return err
	}
	sourceRel := filepath.ToSlash(filepath.Join("contracts/metadata/content/post/projections", yamlName))
	out, err := renderWireKeysClassDart(keysBytes, sourceRel)
	if err != nil {
		return err
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "content", outName),
		out,
	)
	return nil
}

func writePostReadPresentationArtifacts(appDir, postProjectionsDir string) error {
	surfPath := filepath.Join(postProjectionsDir, "read_presentation_surfaces.yaml")
	surfBytes, err := os.ReadFile(surfPath)
	if err != nil {
		return err
	}
	surfOut, err := renderPostReadSurfaceIdDart(surfBytes)
	if err != nil {
		return err
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "content", "post_read_surface_id.g.dart"),
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
	if err := writeWireKeysGeneratedFile(
		appDir,
		postProjectionsDir,
		"article_card_wire_keys.yaml",
		"article_card_wire_keys.g.dart",
	); err != nil {
		return err
	}
	if err := writeWireKeysGeneratedFile(
		appDir,
		postProjectionsDir,
		"article_block_wire_keys.yaml",
		"article_block_wire_keys.g.dart",
	); err != nil {
		return err
	}
	if err := writeWireKeysGeneratedFile(
		appDir,
		postProjectionsDir,
		"content_post_immersive_wire_keys.yaml",
		"content_post_immersive_wire_keys.g.dart",
	); err != nil {
		return err
	}

	presPath := filepath.Join(postProjectionsDir, "post_read_presentation.yaml")
	presBytes, err := os.ReadFile(presPath)
	if err != nil {
		return err
	}
	presOut, err := renderPostReadPresentationDtoDart(presBytes)
	if err != nil {
		return err
	}
	writeFile(
		filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "content", "post_read_presentation.g.dart"),
		presOut,
	)
	return nil
}

func renderPostReadPresentationDtoDart(yamlBytes []byte) (string, error) {
	var f readPresentationProjectionFile
	if err := yaml.Unmarshal(yamlBytes, &f); err != nil {
		return "", err
	}
	class := f.DartClass
	if class == "" {
		class = "PostReadPresentation"
	}
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Source: contracts/metadata/content/post/projections/post_read_presentation.yaml\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")
	b.WriteString("import 'package:quwoquan_app/cloud/runtime/generated/content/article_detail_wire_keys.g.dart';\n")
	b.WriteString("import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';\n\n")
	b.WriteString("/// 帖子只读投影（字段来自 metadata + PostBaseDto；扩展项可走 wire）。\n")
	fmt.Fprintf(&b, "class %s {\n", class)
	fmt.Fprintf(&b, "  const %s({\n", class)
	for _, fld := range f.Fields {
		if fld.Name == "" {
			continue
		}
		fmt.Fprintf(&b, "    required this.%s,\n", fld.Name)
	}
	fmt.Fprintf(&b, "  });\n\n")
	for _, fld := range f.Fields {
		if fld.Name == "" {
			continue
		}
		dt := fld.DartType
		if dt == "" {
			dt = "String"
		}
		fmt.Fprintf(&b, "  final %s %s;\n", dt, fld.Name)
	}

	fmt.Fprintf(&b, "\n  factory %s.fromPostBase(\n    PostBaseDto post, {\n    Map<String, dynamic>? wire,\n  }) {\n", class)
	fmt.Fprintf(&b, "    return %s(\n", class)
	for _, fld := range f.Fields {
		if fld.Name == "" {
			continue
		}
		if fld.WireKey != "" {
			fmt.Fprintf(
				&b,
				"      %s: (wire?[%s.%s] ?? '').toString(),\n",
				fld.Name,
				"ArticleDetailWireKeys",
				fld.WireKey,
			)
			continue
		}
		if fld.PostBase == "" {
			return "", fmt.Errorf("field %q needs post_base or wire_key", fld.Name)
		}
		fmt.Fprintf(&b, "      %s: post.%s,\n", fld.Name, fld.PostBase)
	}
	fmt.Fprintf(&b, "    );\n  }\n}\n")
	return b.String(), nil
}
