package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

type assistantEnumCatalog struct {
	Enums []assistantEnumDef `yaml:"enums"`
}

type assistantEnumDef struct {
	Name   string                  `yaml:"name"`
	Values []assistantEnumValueDef `yaml:"values"`
}

type assistantEnumValueDef struct {
	Name            string   `yaml:"name"`
	Wire            string   `yaml:"wire"`
	Aliases         []string `yaml:"aliases"`
	FastConvergence bool     `yaml:"fast_convergence"`
}

type assistantFieldDef struct {
	Name     string `yaml:"name"`
	DartType string `yaml:"dart_type"`
	JSONKey  string `yaml:"json_key"`
	Default  string `yaml:"default"`
}

type assistantLabeledEnumDef struct {
	Name   string                         `yaml:"name"`
	Values []assistantLabeledEnumValueDef `yaml:"values"`
}

type assistantLabeledEnumValueDef struct {
	Name    string   `yaml:"name"`
	Wire    string   `yaml:"wire"`
	Label   string   `yaml:"label"`
	Aliases []string `yaml:"aliases"`
}

type assistantSubagentPlanDefaults struct {
	Mode              string  `yaml:"mode"`
	TimeoutMs         int     `yaml:"timeoutMs"`
	MaxIterations     int     `yaml:"maxIterations"`
	ToolBudget        int     `yaml:"toolBudget"`
	StopPolicy        string  `yaml:"stopPolicy"`
	SearchIntensity   string  `yaml:"searchIntensity"`
	ProviderPolicy    string  `yaml:"providerPolicy"`
	FreshnessHoursMax int     `yaml:"freshnessHoursMax"`
	AnswerThreshold   float64 `yaml:"answerThreshold"`
}

type assistantSubagentPlanSchema struct {
	DartClass  string                        `yaml:"dart_class"`
	OutputPath string                        `yaml:"output_path"`
	Defaults   assistantSubagentPlanDefaults `yaml:"defaults"`
	Fields     []assistantFieldDef           `yaml:"fields"`
}

type assistantSimpleSchema struct {
	DartClass  string              `yaml:"dart_class"`
	OutputPath string              `yaml:"output_path"`
	Fields     []assistantFieldDef `yaml:"fields"`
}

type assistantContractHeader struct {
	DartClass  string `yaml:"dart_class"`
	OutputPath string `yaml:"output_path"`
}

type assistantRecallResultDefaults struct {
	RecallMethod    string `yaml:"recallMethod"`
	TotalCandidates int    `yaml:"totalCandidates"`
}

type assistantRecallResultSchema struct {
	DartClass       string                        `yaml:"dart_class"`
	OutputPath      string                        `yaml:"output_path"`
	CandidateClass  string                        `yaml:"candidate_class"`
	Defaults        assistantRecallResultDefaults `yaml:"defaults"`
	Fields          []assistantFieldDef           `yaml:"fields"`
	CandidateFields []assistantFieldDef           `yaml:"candidate_fields"`
}

func generateAssistantRuntimeArtifacts(metadataDir, appDir string) error {
	baseDir := filepath.Join(metadataDir, "assistant")
	enumsPath := filepath.Join(baseDir, "_shared", "enums.yaml")
	enumCatalog, err := readAssistantEnumCatalog(enumsPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	contractIndex, err := loadAssistantContractIndex(metadataDir)
	if err != nil {
		return err
	}

	writeFile(
		filepath.Join(appDir, "lib", "assistant", "generated", "enums", "assistant_runtime_enums.g.dart"),
		renderAssistantRuntimeEnumsDart(enumCatalog),
	)

	subagentPlanSchema, err := readAssistantSubagentPlanSchema(filepath.Join(baseDir, "subagent_plan", "schema.yaml"))
	if err == nil {
		writeFile(filepath.Join(appDir, "lib", subagentPlanSchema.OutputPath), renderSubagentPlanDart(subagentPlanSchema))
	} else if !os.IsNotExist(err) {
		return err
	}

	preferenceFactSchema, err := readAssistantSimpleSchema(filepath.Join(baseDir, "preference_fact", "schema.yaml"))
	if err == nil {
		writeFile(filepath.Join(appDir, "lib", preferenceFactSchema.OutputPath), renderPreferenceFactDart(preferenceFactSchema))
	} else if !os.IsNotExist(err) {
		return err
	}

	skillRunSchema, err := readAssistantSimpleSchema(filepath.Join(baseDir, "skill_run", "schema.yaml"))
	if err == nil {
		writeFile(filepath.Join(appDir, "lib", skillRunSchema.OutputPath), renderSkillRunDart(skillRunSchema))
	} else if !os.IsNotExist(err) {
		return err
	}

	recallResultSchema, err := readAssistantRecallResultSchema(filepath.Join(baseDir, "recall_result", "schema.yaml"))
	if err == nil {
		writeFile(filepath.Join(appDir, "lib", recallResultSchema.OutputPath), renderRecallResultDart(recallResultSchema))
	} else if !os.IsNotExist(err) {
		return err
	}

	assistantTurnSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "assistant_turn", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", assistantTurnSchema.OutputPath),
			renderAssistantSchemaDrivenContract(assistantTurnSchema, contractIndex, "assistant/assistant_turn/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	conversationStateDecisionSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "conversation_state_decision", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", conversationStateDecisionSchema.OutputPath),
			renderAssistantSchemaDrivenContract(conversationStateDecisionSchema, contractIndex, "assistant/conversation_state_decision/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	aggregationStateSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "aggregation_state", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", aggregationStateSchema.OutputPath),
			renderAssistantSchemaDrivenContract(aggregationStateSchema, contractIndex, "assistant/aggregation_state/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	assistantJourneySchema, err := readAssistantContractSchema(filepath.Join(baseDir, "assistant_journey", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", assistantJourneySchema.OutputPath),
			renderAssistantSchemaDrivenContract(assistantJourneySchema, contractIndex, "assistant/assistant_journey/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	answerBoundaryPolicySchema, err := readAssistantContractSchema(filepath.Join(baseDir, "answer_boundary_policy", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", answerBoundaryPolicySchema.OutputPath),
			renderAssistantSchemaDrivenContract(answerBoundaryPolicySchema, contractIndex, "assistant/answer_boundary_policy/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	toolAssessmentSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "tool_assessment", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", toolAssessmentSchema.OutputPath),
			renderAssistantSchemaDrivenContract(toolAssessmentSchema, contractIndex, "assistant/tool_assessment/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	slotSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "slot_schema", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", slotSchema.OutputPath),
			renderAssistantSchemaDrivenContract(slotSchema, contractIndex, "assistant/slot_schema/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	reactObservationSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "react_observation", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", reactObservationSchema.OutputPath),
			renderAssistantSchemaDrivenContract(reactObservationSchema, contractIndex, "assistant/react_observation/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	dialogueRoundScriptSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "dialogue_round_script", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", dialogueRoundScriptSchema.OutputPath),
			renderAssistantSchemaDrivenContract(dialogueRoundScriptSchema, contractIndex, "assistant/dialogue_round_script/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	runArtifactsSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "run_artifacts", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", runArtifactsSchema.OutputPath),
			renderAssistantSchemaDrivenContract(runArtifactsSchema, contractIndex, "assistant/run_artifacts/schema.yaml"),
		)
		if keysDart := renderRunArtifactsMapStableKeysDart(runArtifactsSchema, "assistant/run_artifacts/schema.yaml"); keysDart != "" {
			writeFile(
				filepath.Join(appDir, "lib", "assistant", "generated", "contracts", "run_artifacts_map_stable_keys.g.dart"),
				keysDart,
			)
		}
	} else if !os.IsNotExist(err) {
		return err
	}

	structuredResponseWireSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "assistant_structured_response_wire", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", structuredResponseWireSchema.OutputPath),
			renderAssistantSchemaDrivenContract(structuredResponseWireSchema, contractIndex, "assistant/assistant_structured_response_wire/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	contextFillTaskSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "context_fill_task", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", contextFillTaskSchema.OutputPath),
			renderAssistantSchemaDrivenContract(contextFillTaskSchema, contractIndex, "assistant/context_fill_task/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	plannerContractsSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "planner_contracts", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", plannerContractsSchema.OutputPath),
			renderAssistantSchemaDrivenContract(plannerContractsSchema, contractIndex, "assistant/planner_contracts/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	contextContinuityPolicySchema, err := readAssistantContractSchema(filepath.Join(baseDir, "context_continuity_policy", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", contextContinuityPolicySchema.OutputPath),
			renderAssistantSchemaDrivenContract(contextContinuityPolicySchema, contractIndex, "assistant/context_continuity_policy/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	contextAssemblyResultSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "context_assembly_result", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", contextAssemblyResultSchema.OutputPath),
			renderAssistantSchemaDrivenContract(contextAssemblyResultSchema, contractIndex, "assistant/context_assembly_result/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	synthesisReadinessResultSchema, err := readAssistantContractSchema(filepath.Join(baseDir, "synthesis_readiness_result", "schema.yaml"))
	if err == nil {
		writeFile(
			filepath.Join(appDir, "lib", synthesisReadinessResultSchema.OutputPath),
			renderAssistantSchemaDrivenContract(synthesisReadinessResultSchema, contractIndex, "assistant/synthesis_readiness_result/schema.yaml"),
		)
	} else if !os.IsNotExist(err) {
		return err
	}

	return nil
}

func readAssistantEnumCatalog(path string) (*assistantEnumCatalog, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed assistantEnumCatalog
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readAssistantSubagentPlanSchema(path string) (*assistantSubagentPlanSchema, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed assistantSubagentPlanSchema
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readAssistantSimpleSchema(path string) (*assistantSimpleSchema, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed assistantSimpleSchema
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readAssistantContractHeader(path string) (*assistantContractHeader, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed assistantContractHeader
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readAssistantRecallResultSchema(path string) (*assistantRecallResultSchema, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed assistantRecallResultSchema
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func writeAssistantTemplateContract(appDir, outputPath, templateName, sourceMeta string) error {
	templatePath := filepath.Join("tools", "codegen_app_metadata", "templates", templateName)
	data, err := os.ReadFile(templatePath)
	if err != nil {
		return err
	}
	header := fmt.Sprintf("// Code generated by tools/codegen_app_metadata from %s. DO NOT EDIT.\n\n", sourceMeta)
	writeFile(filepath.Join(appDir, "lib", outputPath), header+string(data))
	return nil
}

func renderAssistantRuntimeEnumsDart(catalog *assistantEnumCatalog) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from assistant/_shared/enums.yaml. DO NOT EDIT.\n\n")
	for _, enumDef := range catalog.Enums {
		b.WriteString(fmt.Sprintf("enum %s {\n", enumDef.Name))
		for _, value := range enumDef.Values {
			b.WriteString(fmt.Sprintf("  %s,\n", value.Name))
		}
		b.WriteString("}\n\n")

		b.WriteString(fmt.Sprintf("%s parse%s(String raw) {\n", enumDef.Name, enumDef.Name))
		b.WriteString("  switch (raw.trim()) {\n")
		defaultName := assistantEnumDefault(enumDef.Name)
		for _, value := range enumDef.Values {
			if value.Wire != "" {
				b.WriteString(fmt.Sprintf("    case %q:\n", value.Wire))
			}
			for _, alias := range value.Aliases {
				b.WriteString(fmt.Sprintf("    case %q:\n", alias))
			}
			if value.Wire == "" && len(value.Aliases) == 0 {
				continue
			}
			b.WriteString(fmt.Sprintf("      return %s.%s;\n", enumDef.Name, value.Name))
		}
		b.WriteString("    default:\n")
		b.WriteString(fmt.Sprintf("      return %s.%s;\n", enumDef.Name, defaultName))
		b.WriteString("  }\n")
		b.WriteString("}\n\n")

		b.WriteString(fmt.Sprintf("extension %sX on %s {\n", enumDef.Name, enumDef.Name))
		b.WriteString("  String get wireName {\n")
		b.WriteString("    switch (this) {\n")
		for _, value := range enumDef.Values {
			b.WriteString(fmt.Sprintf("      case %s.%s:\n", enumDef.Name, value.Name))
			b.WriteString(fmt.Sprintf("        return %q;\n", value.Wire))
		}
		b.WriteString("    }\n")
		b.WriteString("  }\n")
		if enumDef.Name == "ProblemClass" {
			b.WriteString("\n  bool get isFastConvergence {\n")
			b.WriteString("    switch (this) {\n")
			for _, value := range enumDef.Values {
				b.WriteString(fmt.Sprintf("      case %s.%s:\n", enumDef.Name, value.Name))
				b.WriteString(fmt.Sprintf("        return %t;\n", value.FastConvergence))
			}
			b.WriteString("    }\n")
			b.WriteString("  }\n")
		}
		b.WriteString("}\n\n")
	}
	return b.String()
}

func assistantSubagentPlanExtraFields(schema *assistantSubagentPlanSchema) []assistantFieldDef {
	builtins := map[string]bool{
		"subagentId":        true,
		"domainId":          true,
		"problemClass":      true,
		"goal":              true,
		"mode":              true,
		"timeoutMs":         true,
		"maxIterations":     true,
		"toolBudget":        true,
		"toolWhitelist":     true,
		"stopPolicy":        true,
		"searchIntensity":   true,
		"providerPolicy":    true,
		"freshnessHoursMax": true,
		"answerThreshold":   true,
		"dependencies":      true,
	}
	fields := make([]assistantFieldDef, 0, len(schema.Fields))
	for _, field := range schema.Fields {
		if builtins[field.Name] {
			continue
		}
		fields = append(fields, field)
	}
	return fields
}

func assistantSubagentPlanFieldDefaultValue(field assistantFieldDef) string {
	switch field.DartType {
	case "String":
		raw := strings.TrimSpace(field.Default)
		if raw == "" {
			return "''"
		}
		if (strings.HasPrefix(raw, "'") && strings.HasSuffix(raw, "'")) ||
			(strings.HasPrefix(raw, "\"") && strings.HasSuffix(raw, "\"")) {
			return raw
		}
		return fmt.Sprintf("%q", raw)
	case "int":
		raw := strings.TrimSpace(field.Default)
		if raw != "" {
			return raw
		}
		return "0"
	case "double":
		raw := strings.TrimSpace(field.Default)
		if raw != "" {
			return raw
		}
		return "0.0"
	case "bool":
		raw := strings.TrimSpace(field.Default)
		if raw != "" {
			return raw
		}
		return "false"
	case "List<String>":
		raw := strings.TrimSpace(field.Default)
		if raw != "" {
			return raw
		}
		return "const <String>[]"
	default:
		raw := strings.TrimSpace(field.Default)
		if raw != "" {
			return raw
		}
		return "null"
	}
}

func assistantRenderSubagentPlanFromJsonValue(field assistantFieldDef) string {
	switch field.DartType {
	case "String":
		return fmt.Sprintf("(json['%s'] as String?)?.trim() ?? %s", field.JSONKey, assistantSubagentPlanFieldDefaultValue(field))
	case "int":
		return fmt.Sprintf("(json['%s'] as num?)?.toInt() ?? %s", field.JSONKey, assistantSubagentPlanFieldDefaultValue(field))
	case "double":
		return fmt.Sprintf("(json['%s'] as num?)?.toDouble() ?? %s", field.JSONKey, assistantSubagentPlanFieldDefaultValue(field))
	case "bool":
		if assistantSubagentPlanFieldDefaultValue(field) == "true" {
			return fmt.Sprintf("json['%s'] != false", field.JSONKey)
		}
		return fmt.Sprintf("json['%s'] == true", field.JSONKey)
	case "List<String>":
		return fmt.Sprintf("_stringList(json['%s'])", field.JSONKey)
	default:
		return fmt.Sprintf("json['%s'] as %s? ?? %s", field.JSONKey, field.DartType, assistantSubagentPlanFieldDefaultValue(field))
	}
}

func assistantRenderSubagentPlanToJsonLine(field assistantFieldDef) string {
	switch field.DartType {
	case "String":
		return fmt.Sprintf("        if (%s.trim().isNotEmpty) '%s': %s,\n", field.Name, field.JSONKey, field.Name)
	case "int":
		return fmt.Sprintf("        if (%s > 0) '%s': %s,\n", field.Name, field.JSONKey, field.Name)
	case "double":
		return fmt.Sprintf("        if (%s > 0) '%s': %s,\n", field.Name, field.JSONKey, field.Name)
	case "bool":
		if assistantSubagentPlanFieldDefaultValue(field) == "true" {
			return fmt.Sprintf("        if (!%s) '%s': %s,\n", field.Name, field.JSONKey, field.Name)
		}
		return fmt.Sprintf("        if (%s) '%s': %s,\n", field.Name, field.JSONKey, field.Name)
	case "List<String>":
		return fmt.Sprintf("        if (%s.isNotEmpty) '%s': %s,\n", field.Name, field.JSONKey, field.Name)
	default:
		return fmt.Sprintf("        '%s': %s,\n", field.JSONKey, field.Name)
	}
}

func renderSubagentPlanDart(schema *assistantSubagentPlanSchema) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from assistant/subagent_plan/schema.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")
	b.WriteString("import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';\n\n")
	b.WriteString(fmt.Sprintf("class %s {\n", schema.DartClass))
	b.WriteString("  const SubagentPlan({\n")
	b.WriteString("    required this.subagentId,\n")
	b.WriteString("    required this.domainId,\n")
	b.WriteString("    required this.problemClass,\n")
	b.WriteString("    required this.goal,\n")
	for _, field := range assistantSubagentPlanExtraFields(schema) {
		b.WriteString(fmt.Sprintf("    this.%s = %s,\n", field.Name, assistantSubagentPlanFieldDefaultValue(field)))
	}
	b.WriteString(fmt.Sprintf("    this.mode = %q,\n", schema.Defaults.Mode))
	b.WriteString(fmt.Sprintf("    this.timeoutMs = %d,\n", schema.Defaults.TimeoutMs))
	b.WriteString(fmt.Sprintf("    this.maxIterations = %d,\n", schema.Defaults.MaxIterations))
	b.WriteString(fmt.Sprintf("    this.toolBudget = %d,\n", schema.Defaults.ToolBudget))
	b.WriteString("    this.toolWhitelist = const <String>[],\n")
	b.WriteString(fmt.Sprintf("    this.stopPolicy = %q,\n", schema.Defaults.StopPolicy))
	b.WriteString(fmt.Sprintf("    this.searchIntensity = %q,\n", schema.Defaults.SearchIntensity))
	b.WriteString(fmt.Sprintf("    this.providerPolicy = %q,\n", schema.Defaults.ProviderPolicy))
	b.WriteString(fmt.Sprintf("    this.freshnessHoursMax = %d,\n", schema.Defaults.FreshnessHoursMax))
	b.WriteString(fmt.Sprintf("    this.answerThreshold = %g,\n", schema.Defaults.AnswerThreshold))
	b.WriteString("    this.dependencies = const <String>[],\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String subagentId;\n  final String domainId;\n  final String problemClass;\n  final String goal;\n")
	for _, field := range assistantSubagentPlanExtraFields(schema) {
		b.WriteString(fmt.Sprintf("  final %s %s;\n", field.DartType, field.Name))
	}
	b.WriteString("\n")
	b.WriteString("  final String mode;\n  final int timeoutMs;\n  final int maxIterations;\n  final int toolBudget;\n")
	b.WriteString("  final List<String> toolWhitelist;\n  final String stopPolicy;\n  final String searchIntensity;\n")
	b.WriteString("  final String providerPolicy;\n  final int freshnessHoursMax;\n  final double answerThreshold;\n  final List<String> dependencies;\n\n")
	b.WriteString("  ProblemClass get problemClassType => parseProblemClass(problemClass);\n\n")
	b.WriteString("  SkillMode get modeType => parseSkillMode(mode);\n\n")
	b.WriteString("  StopPolicy get stopPolicyType => parseStopPolicy(stopPolicy);\n\n")
	b.WriteString("  SearchIntensity get searchIntensityType =>\n      parseSearchIntensity(searchIntensity);\n\n")
	b.WriteString("  ProviderPolicy get providerPolicyType =>\n      parseProviderPolicy(providerPolicy);\n\n")
	b.WriteString("  Map<String, dynamic> toJson() => <String, dynamic>{\n")
	b.WriteString("    'subagentId': subagentId,\n    'domainId': domainId,\n    'problemClass': problemClass,\n")
	b.WriteString("    'goal': goal,\n")
	for _, field := range assistantSubagentPlanExtraFields(schema) {
		b.WriteString(assistantRenderSubagentPlanToJsonLine(field))
	}
	b.WriteString("    'mode': mode,\n    'timeoutMs': timeoutMs,\n    'maxIterations': maxIterations,\n")
	b.WriteString("    'toolBudget': toolBudget,\n    'toolWhitelist': toolWhitelist,\n    'stopPolicy': stopPolicy,\n")
	b.WriteString("    'searchIntensity': searchIntensity,\n    'providerPolicy': providerPolicy,\n")
	b.WriteString("    'freshnessHoursMax': freshnessHoursMax,\n    'answerThreshold': answerThreshold,\n    'dependencies': dependencies,\n  };\n\n")
	b.WriteString("  factory SubagentPlan.fromJson(Map<String, dynamic> json) {\n")
	b.WriteString("    return SubagentPlan(\n")
	b.WriteString("      subagentId: (json['subagentId'] as String?)?.trim() ?? '',\n")
	b.WriteString("      domainId: (json['domainId'] as String?)?.trim() ?? '',\n")
	b.WriteString("      problemClass: (json['problemClass'] as String?)?.trim() ?? '',\n")
	b.WriteString("      goal: (json['goal'] as String?)?.trim() ?? '',\n")
	for _, field := range assistantSubagentPlanExtraFields(schema) {
		b.WriteString(fmt.Sprintf("      %s: %s,\n", field.Name, assistantRenderSubagentPlanFromJsonValue(field)))
	}
	b.WriteString(fmt.Sprintf("      mode: (json['mode'] as String?)?.trim() ?? %q,\n", schema.Defaults.Mode))
	b.WriteString(fmt.Sprintf("      timeoutMs: _positiveInt(json['timeoutMs'], fallback: %d),\n", schema.Defaults.TimeoutMs))
	b.WriteString(fmt.Sprintf("      maxIterations: _positiveInt(json['maxIterations'], fallback: %d),\n", schema.Defaults.MaxIterations))
	b.WriteString(fmt.Sprintf("      toolBudget: _positiveInt(json['toolBudget'], fallback: %d),\n", schema.Defaults.ToolBudget))
	b.WriteString("      toolWhitelist:\n")
	b.WriteString("          (json['toolWhitelist'] as List?)\n")
	b.WriteString("              ?.whereType<String>()\n")
	b.WriteString("              .map((item) => item.trim())\n")
	b.WriteString("              .where((item) => item.isNotEmpty)\n")
	b.WriteString("              .toList(growable: false) ??\n")
	b.WriteString("          const <String>[],\n")
	b.WriteString(fmt.Sprintf("      stopPolicy: (json['stopPolicy'] as String?)?.trim() ?? %q,\n", schema.Defaults.StopPolicy))
	b.WriteString(fmt.Sprintf("      searchIntensity: (json['searchIntensity'] as String?)?.trim() ?? %q,\n", schema.Defaults.SearchIntensity))
	b.WriteString(fmt.Sprintf("      providerPolicy: (json['providerPolicy'] as String?)?.trim() ?? %q,\n", schema.Defaults.ProviderPolicy))
	b.WriteString(fmt.Sprintf("      freshnessHoursMax: _nonNegativeInt(json['freshnessHoursMax'], fallback: %d),\n", schema.Defaults.FreshnessHoursMax))
	b.WriteString("      answerThreshold: _normalizedThreshold(json['answerThreshold']),\n")
	b.WriteString("      dependencies:\n")
	b.WriteString("          (json['dependencies'] as List?)\n")
	b.WriteString("              ?.whereType<String>()\n")
	b.WriteString("              .map((item) => item.trim())\n")
	b.WriteString("              .where((item) => item.isNotEmpty)\n")
	b.WriteString("              .toList(growable: false) ??\n")
	b.WriteString("          const <String>[],\n")
	b.WriteString("    );\n")
	b.WriteString("  }\n\n")
	b.WriteString("  static List<String> _stringList(Object? raw) {\n")
	b.WriteString("    if (raw is List) {\n")
	b.WriteString("      return raw\n")
	b.WriteString("          .map((item) => item.toString().trim())\n")
	b.WriteString("          .where((item) => item.isNotEmpty)\n")
	b.WriteString("          .toList(growable: false);\n")
	b.WriteString("    }\n")
	b.WriteString("    if (raw is String && raw.trim().isNotEmpty) {\n")
	b.WriteString("      return raw\n")
	b.WriteString("          .split(RegExp(r'[\\s,]+'))\n")
	b.WriteString("          .map((item) => item.trim())\n")
	b.WriteString("          .where((item) => item.isNotEmpty)\n")
	b.WriteString("          .toList(growable: false);\n")
	b.WriteString("    }\n")
	b.WriteString("    return const <String>[];\n")
	b.WriteString("  }\n\n")
	b.WriteString("  static int _positiveInt(Object? value, {required int fallback}) {\n")
	b.WriteString("    if (value is int && value > 0) return value;\n")
	b.WriteString("    final parsed = int.tryParse(value?.toString() ?? '');\n")
	b.WriteString("    if (parsed != null && parsed > 0) return parsed;\n")
	b.WriteString("    return fallback;\n")
	b.WriteString("  }\n\n")
	b.WriteString("  static int _nonNegativeInt(Object? value, {required int fallback}) {\n")
	b.WriteString("    if (value is int && value >= 0) return value;\n")
	b.WriteString("    final parsed = int.tryParse(value?.toString() ?? '');\n")
	b.WriteString("    if (parsed != null && parsed >= 0) return parsed;\n")
	b.WriteString("    return fallback;\n")
	b.WriteString("  }\n\n")
	b.WriteString("  static double _normalizedThreshold(Object? value) {\n")
	b.WriteString("    final parsed =\n")
	b.WriteString("        (value as num?)?.toDouble() ??\n")
	b.WriteString("        double.tryParse(value?.toString() ?? '') ??\n")
	b.WriteString("        0.0;\n")
	b.WriteString("    if (parsed.isNaN) return 0.0;\n")
	b.WriteString("    if (parsed < 0) return 0.0;\n")
	b.WriteString("    if (parsed > 1) return 1.0;\n")
	b.WriteString("    return parsed;\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func renderSkillRunDart(schema *assistantSimpleSchema) string {
	_ = schema
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from assistant/skill_run/schema.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")
	b.WriteString("class SkillRun {\n")
	b.WriteString("  const SkillRun({\n")
	b.WriteString("    required this.runId,\n    required this.domainId,\n    required this.goal,\n    required this.problemClass,\n")
	b.WriteString("    this.shell = const <String, dynamic>{},\n    this.slotState = const <String, dynamic>{},\n")
	b.WriteString("    this.answerReady = false,\n    this.stopReason = '',\n")
	b.WriteString("    this.references = const <Map<String, dynamic>>[],\n    this.resultSummary = '',\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String runId;\n  final String domainId;\n  final String goal;\n  final String problemClass;\n")
	b.WriteString("  final Map<String, dynamic> shell;\n  final Map<String, dynamic> slotState;\n")
	b.WriteString("  final bool answerReady;\n  final String stopReason;\n")
	b.WriteString("  final List<Map<String, dynamic>> references;\n  final String resultSummary;\n\n")
	b.WriteString("  Map<String, dynamic> toJson() => <String, dynamic>{\n")
	b.WriteString("    'runId': runId,\n    'domainId': domainId,\n    'goal': goal,\n    'problemClass': problemClass,\n")
	b.WriteString("    'shell': shell,\n    'slotState': slotState,\n    'answerReady': answerReady,\n")
	b.WriteString("    'stopReason': stopReason,\n    'references': references,\n    'resultSummary': resultSummary,\n")
	b.WriteString("  };\n\n")
	b.WriteString("  factory SkillRun.fromJson(Map<String, dynamic> json) {\n")
	b.WriteString("    return SkillRun(\n")
	b.WriteString("      runId: (json['runId'] as String?)?.trim() ?? '',\n")
	b.WriteString("      domainId: (json['domainId'] as String?)?.trim() ?? '',\n")
	b.WriteString("      goal: (json['goal'] as String?)?.trim() ?? '',\n")
	b.WriteString("      problemClass: (json['problemClass'] as String?)?.trim() ?? '',\n")
	b.WriteString("      shell: (json['shell'] as Map?)?.cast<String, dynamic>() ??\n")
	b.WriteString("          const <String, dynamic>{},\n")
	b.WriteString("      slotState:\n")
	b.WriteString("          (json['slotState'] as Map?)?.cast<String, dynamic>() ??\n")
	b.WriteString("          const <String, dynamic>{},\n")
	b.WriteString("      answerReady: json['answerReady'] == true,\n")
	b.WriteString("      stopReason: (json['stopReason'] as String?)?.trim() ?? '',\n")
	b.WriteString("      references: (json['references'] as List?)\n")
	b.WriteString("              ?.whereType<Map>()\n")
	b.WriteString("              .map((item) => item.cast<String, dynamic>())\n")
	b.WriteString("              .toList(growable: false) ??\n")
	b.WriteString("          const <Map<String, dynamic>>[],\n")
	b.WriteString("      resultSummary: (json['resultSummary'] as String?)?.trim() ?? '',\n")
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func renderPreferenceFactDart(schema *assistantSimpleSchema) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from assistant/preference_fact/schema.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")
	b.WriteString("class PreferenceFact {\n")
	b.WriteString("  const PreferenceFact({\n")
	b.WriteString("    required this.factId,\n    required this.scope,\n    required this.key,\n    required this.value,\n")
	b.WriteString("    this.source = '',\n    this.createdAt = '',\n    this.revoked = false,\n  });\n\n")
	b.WriteString("  final String factId;\n  final String scope;\n  final String key;\n  final String value;\n")
	b.WriteString("  final String source;\n  final String createdAt;\n  final bool revoked;\n\n")
	b.WriteString("  Map<String, dynamic> toJson() => <String, dynamic>{\n")
	b.WriteString("    'factId': factId,\n    'scope': scope,\n    'key': key,\n    'value': value,\n")
	b.WriteString("    'source': source,\n    'createdAt': createdAt,\n    'revoked': revoked,\n  };\n\n")
	b.WriteString("  factory PreferenceFact.fromJson(Map<String, dynamic> json) {\n")
	b.WriteString("    return PreferenceFact(\n")
	b.WriteString("      factId: (json['factId'] as String?)?.trim() ?? '',\n")
	b.WriteString("      scope: (json['scope'] as String?)?.trim() ?? '',\n")
	b.WriteString("      key: (json['key'] as String?)?.trim() ?? '',\n")
	b.WriteString("      value: (json['value'] as String?)?.trim() ?? '',\n")
	b.WriteString("      source: (json['source'] as String?)?.trim() ?? '',\n")
	b.WriteString("      createdAt: (json['createdAt'] as String?)?.trim() ?? '',\n")
	b.WriteString("      revoked: json['revoked'] == true,\n")
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func renderRecallResultDart(schema *assistantRecallResultSchema) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from assistant/recall_result/schema.yaml. DO NOT EDIT.\n")
	b.WriteString("// ignore_for_file: prefer_const_constructors\n\n")
	b.WriteString("class RecallResult {\n")
	b.WriteString("  const RecallResult({\n")
	b.WriteString(fmt.Sprintf("    required this.topK,\n    this.recallMethod = %q,\n", schema.Defaults.RecallMethod))
	b.WriteString(fmt.Sprintf("    this.totalCandidates = %d,\n", schema.Defaults.TotalCandidates))
	b.WriteString("    this.scores = const <String, double>{},\n  });\n\n")
	b.WriteString("  final List<RecallCandidate> topK;\n  final String recallMethod;\n  final int totalCandidates;\n  final Map<String, double> scores;\n\n")
	b.WriteString("  bool get isEmpty => topK.isEmpty;\n\n")
	b.WriteString("  String toPromptSnippet() {\n")
	b.WriteString("    if (topK.isEmpty) return '（无匹配技能，使用默认通用能力）';\n")
	b.WriteString("    final buf = StringBuffer();\n")
	b.WriteString("    for (final c in topK) {\n")
	b.WriteString("      buf.writeln('- ${c.domainId}: ${c.description} [mode=${c.mode}]');\n")
	b.WriteString("    }\n")
	b.WriteString("    return buf.toString().trimRight();\n")
	b.WriteString("  }\n\n")
	b.WriteString("  Map<String, dynamic> toJson() => <String, dynamic>{\n")
	b.WriteString("        'topK': topK.map((c) => c.toJson()).toList(growable: false),\n")
	b.WriteString("        'recallMethod': recallMethod,\n")
	b.WriteString("        'totalCandidates': totalCandidates,\n")
	b.WriteString("        'scores': scores,\n")
	b.WriteString("      };\n\n")
	b.WriteString("  factory RecallResult.fromJson(Map<String, dynamic> json) {\n")
	b.WriteString("    return RecallResult(\n")
	b.WriteString("      topK: (json['topK'] as List?)\n")
	b.WriteString("              ?.whereType<Map>()\n")
	b.WriteString("              .map((m) => RecallCandidate.fromJson(m.cast<String, dynamic>()))\n")
	b.WriteString("              .toList(growable: false) ??\n")
	b.WriteString("          const <RecallCandidate>[],\n")
	b.WriteString(fmt.Sprintf("      recallMethod: (json['recallMethod'] as String?)?.trim() ?? %q,\n", schema.Defaults.RecallMethod))
	b.WriteString("      totalCandidates: (json['totalCandidates'] as num?)?.toInt() ?? 0,\n")
	b.WriteString("      scores: (json['scores'] as Map?)\n")
	b.WriteString("              ?.map((k, v) => MapEntry(k.toString(), (v as num).toDouble())) ??\n")
	b.WriteString("          const <String, double>{},\n")
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")
	b.WriteString("class RecallCandidate {\n")
	b.WriteString("  const RecallCandidate({\n")
	b.WriteString("    required this.domainId,\n    required this.description,\n    this.mode = 'qa',\n    this.score = 0.0,\n    this.matchReason = '',\n  });\n\n")
	b.WriteString("  final String domainId;\n  final String description;\n  final String mode;\n  final double score;\n  final String matchReason;\n\n")
	b.WriteString("  Map<String, dynamic> toJson() => <String, dynamic>{\n")
	b.WriteString("        'domainId': domainId,\n        'description': description,\n        'mode': mode,\n        'score': score,\n        'matchReason': matchReason,\n      };\n\n")
	b.WriteString("  factory RecallCandidate.fromJson(Map<String, dynamic> json) {\n")
	b.WriteString("    return RecallCandidate(\n")
	b.WriteString("      domainId: (json['domainId'] as String?)?.trim() ?? '',\n")
	b.WriteString("      description: (json['description'] as String?)?.trim() ?? '',\n")
	b.WriteString("      mode: (json['mode'] as String?)?.trim() ?? 'qa',\n")
	b.WriteString("      score: (json['score'] as num?)?.toDouble() ?? 0.0,\n")
	b.WriteString("      matchReason: (json['matchReason'] as String?)?.trim() ?? '',\n")
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func assistantEnumDefault(name string) string {
	switch name {
	case "ProblemClass":
		return "general"
	case "QueryIntent":
		return "unspecified"
	case "AnswerShape":
		return "unspecified"
	case "FreshnessNeed":
		return "unspecified"
	case "SkillMode":
		return "qa"
	case "ProviderPolicy":
		return "inherit"
	case "SearchIntensity":
		return "medium"
	case "StopPolicy":
		return "balanced"
	case "FinalAnswerMode":
		return "blocked"
	case "AnswerEligibility":
		return "unknown"
	case "ProblemShape":
		return "unknown"
	case "EvidenceSourceTier":
		return "unknown"
	case "SkillExecutionTarget":
		return "unknown"
	case "AssistantNextAction":
		return "unknown"
	case "AssistantMessageKind":
		return "unknown"
	case "TraceVisibility":
		return "userVisible"
	case "SlotValueStatus":
		return "inferred"
	case "SlotFillAction":
		return "unknown"
	case "SlotSource":
		return "unknown"
	case "PlannerPhaseId":
		return "unknown"
	case "PlannerActionCode":
		return "unknown"
	case "PlannerReasonCode":
		return "unknownReason"
	case "AssessmentType":
		return "unknown"
	case "QueryNormalizationIssue":
		return "unknown"
	case "EvidenceStatus":
		return "unknown"
	default:
		return "unknown"
	}
}
