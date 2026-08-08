package main

import (
	"fmt"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

// ── content behaviors/features codegen ───────────────────────────────────────

type featureDef struct {
	Name        string `yaml:"name"`
	Type        string `yaml:"type"`
	PythonType  string `yaml:"python_type"`
	Nullable    bool   `yaml:"nullable"`
	Description string `yaml:"description"`
}

type recommendFeatures struct {
	FeatureGroup string       `yaml:"feature_group"`
	PythonClass  string       `yaml:"python_class"`
	Features     []featureDef `yaml:"features"`
}

type signalDef struct {
	Type      string `yaml:"type"`
	Condition string `yaml:"condition"`
	Weight    int    `yaml:"weight"`
}

type contextFieldDef struct {
	Name string `yaml:"name"`
	Type string `yaml:"type"`
}

type trainingSampleDef struct {
	PythonClass     string            `yaml:"python_class"`
	LabelField      string            `yaml:"label_field"`
	LabelType       string            `yaml:"label_type"`
	PositiveSignals []signalDef       `yaml:"positive_signals"`
	NegativeSignals []signalDef       `yaml:"negative_signals"`
	ContextFields   []contextFieldDef `yaml:"context_fields"`
	ItemFeaturesRef string            `yaml:"item_features_ref"`
}

type behaviorsYAML struct {
	RecommendFeatures recommendFeatures `yaml:"recommend_features"`
	TrainingSample    trainingSampleDef `yaml:"training_sample"`
}

func loadBehaviors(
	source *contractcodegen.Source,
	path string,
) (*behaviorsYAML, error) {
	var b behaviorsYAML
	return &b, source.Decode(path, &b)
}

func generateContentFeaturesPy(beh *behaviorsYAML) string {
	var sb strings.Builder
	sb.WriteString(genHeader)
	sb.WriteString("\nfrom __future__ import annotations\n\n")
	sb.WriteString("from typing import Optional\n\n")
	sb.WriteString("from pydantic import BaseModel\n\n\n")

	rf := beh.RecommendFeatures
	sb.WriteString(fmt.Sprintf("class %s(BaseModel):\n", rf.PythonClass))
	sb.WriteString(fmt.Sprintf("    \"\"\"Content item features for recommendation. Feature group: %s.\"\"\"\n\n", rf.FeatureGroup))

	for _, f := range rf.Features {
		pt := f.PythonType
		if pt == "" {
			pt = "str"
		}
		defVal := ""
		if f.Nullable || strings.Contains(pt, "Optional") {
			defVal = " = None"
		}
		comment := ""
		if f.Description != "" {
			comment = fmt.Sprintf("  # %s", f.Description)
		}
		sb.WriteString(fmt.Sprintf("    %s: %s%s%s\n", f.Name, pt, defVal, comment))
	}
	return sb.String()
}

func generateTrainingSamplePy(beh *behaviorsYAML) string {
	var sb strings.Builder
	sb.WriteString(genHeader)
	sb.WriteString("\nfrom __future__ import annotations\n\n")
	sb.WriteString("from typing import Optional\n\n")
	sb.WriteString("from pydantic import BaseModel, ConfigDict, Field\n\n")
	sb.WriteString(fmt.Sprintf("from .content_features import %s\n\n\n", beh.RecommendFeatures.PythonClass))

	ts := beh.TrainingSample
	sb.WriteString(fmt.Sprintf("class %s(BaseModel):\n", ts.PythonClass))
	sb.WriteString("    \"\"\"Training sample for content recommendation model.\"\"\"\n\n")

	// context fields
	for _, cf := range ts.ContextFields {
		pt := cf.Type
		if pt == "" {
			pt = "str"
		}
		sb.WriteString(fmt.Sprintf("    %s: %s\n", cf.Name, pt))
	}

	// item features reference
	if ts.ItemFeaturesRef != "" && beh.RecommendFeatures.PythonClass != "" {
		sb.WriteString(fmt.Sprintf("    item_features: %s\n", beh.RecommendFeatures.PythonClass))
	}

	// label
	labelType := ts.LabelType
	if labelType == "" {
		labelType = "int"
	}
	sb.WriteString(fmt.Sprintf("    %s: %s = Field(..., description=\"1=positive, 0=negative\")\n", ts.LabelField, labelType))

	// signal metadata as class-level docs
	if len(ts.PositiveSignals) > 0 || len(ts.NegativeSignals) > 0 {
		sb.WriteString("\n    model_config = ConfigDict(\n")
		sb.WriteString("        json_schema_extra={\n")
		sb.WriteString("            \"positive_signals\": [\n")
		for _, s := range ts.PositiveSignals {
			sb.WriteString(fmt.Sprintf("                {\"type\": \"%s\", \"weight\": %d},\n", s.Type, s.Weight))
		}
		sb.WriteString("            ],\n")
		sb.WriteString("            \"negative_signals\": [\n")
		for _, s := range ts.NegativeSignals {
			sb.WriteString(fmt.Sprintf("                {\"type\": \"%s\", \"weight\": %d},\n", s.Type, s.Weight))
		}
		sb.WriteString("            ],\n")
		sb.WriteString("        },\n")
		sb.WriteString("    )\n")
	}

	return sb.String()
}
