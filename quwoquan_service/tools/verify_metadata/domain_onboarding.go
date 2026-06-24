package main

import (
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

func (v *validator) validateDomainOnboardingMetadata() {
	schemaPath := filepath.Join(v.metadataDir, "_control_plane", "domain_onboarding_schema.yaml")
	if !fileExists(schemaPath) {
		v.warnf("_control_plane/domain_onboarding_schema.yaml: not found, skip domain onboarding validation")
		return
	}

	data, ok := v.readYAMLFile(schemaPath)
	if !ok {
		return
	}

	var schema domainOnboardingSchema
	if err := yaml.Unmarshal(data, &schema); err != nil {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: parse error: %v", err)
		return
	}
	if len(schema.Schema.AcceptanceStatuses) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.acceptance_statuses cannot be empty")
	}
	if len(schema.Schema.TemplateRoles) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.template_roles cannot be empty")
	}
	if len(schema.Schema.RolloutGroups) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.rollout_groups cannot be empty")
	}
	if len(schema.Schema.RequiredControlPlaneKeys) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_control_plane_keys cannot be empty")
	}
	if len(schema.Schema.RequiredTestLayers) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_test_layers cannot be empty")
	}
	if len(schema.Schema.RequiredCodegenTargets) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_codegen_targets cannot be empty")
	}
	if len(schema.Schema.RequiredSections) == 0 {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_sections cannot be empty")
	}
	for _, section := range schema.Schema.RequiredSections {
		if strings.TrimSpace(section) == "" {
			v.errorf("_control_plane/domain_onboarding_schema.yaml: schema.required_sections cannot contain empty values")
		}
	}
	for status, rule := range schema.Schema.StatusRules {
		if !contains(schema.Schema.AcceptanceStatuses, status) {
			v.errorf("_control_plane/domain_onboarding_schema.yaml: status_rules.%s references unknown acceptance_status", status)
		}
		for _, layer := range rule.MinTestLayers {
			if !contains(schema.Schema.RequiredTestLayers, layer) {
				v.errorf("_control_plane/domain_onboarding_schema.yaml: status_rules.%s.min_test_layers contains unknown layer %q", status, layer)
			}
		}
	}
	if schema.MinimumPackage.TemplateDomain == "" {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: minimum_package.template_domain is required")
	}
	if schema.MinimumPackage.RequiredDeploySources.Current == "" || schema.MinimumPackage.RequiredDeploySources.PlaneAware == "" {
		v.errorf("_control_plane/domain_onboarding_schema.yaml: minimum_package.required_deploy_sources.{current,plane_aware} are required")
	}

	domainsDir := filepath.Join(v.metadataDir, "_control_plane", "domains")
	entries, err := os.ReadDir(domainsDir)
	if err != nil {
		v.errorf("_control_plane/domains: %v", err)
		return
	}

	allowedStatuses := sliceToSet(schema.Schema.AcceptanceStatuses)
	allowedTemplateRoles := sliceToSet(schema.Schema.TemplateRoles)
	allowedRolloutGroups := sliceToSet(schema.Schema.RolloutGroups)
	allowedCodegenTargets := sliceToSet(schema.Schema.RequiredCodegenTargets)
	allowedLayers := sliceToSet(schema.Schema.RequiredTestLayers)
	requiredControlPlaneKeys := sliceToSet(schema.Schema.RequiredControlPlaneKeys)
	statusRules := schema.Schema.StatusRules
	statusRank := map[string]int{}
	for idx, status := range schema.Schema.AcceptanceStatuses {
		statusRank[status] = idx
	}

	seenDomains := map[string]bool{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".yaml") {
			continue
		}
		path := filepath.Join(domainsDir, entry.Name())
		raw, ok := v.readYAMLFile(path)
		if !ok {
			continue
		}

		var rawDoc map[string]any
		if err := yaml.Unmarshal(raw, &rawDoc); err != nil {
			v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
			continue
		}
		for _, section := range schema.Schema.RequiredSections {
			if _, ok := rawDoc[section]; !ok {
				v.errorf("%s: missing required section %q", pathRelative(v.metadataDir, path), section)
			}
		}

		var parsed domainOnboardingFile
		if err := yaml.Unmarshal(raw, &parsed); err != nil {
			v.errorf("%s: parse error: %v", pathRelative(v.metadataDir, path), err)
			continue
		}
		if parsed.Domain == "" {
			v.errorf("%s: domain is required", pathRelative(v.metadataDir, path))
			continue
		}
		if seenDomains[parsed.Domain] {
			v.errorf("%s: duplicate domain %q", pathRelative(v.metadataDir, path), parsed.Domain)
			continue
		}
		seenDomains[parsed.Domain] = true

		if parsed.DisplayName == "" {
			v.errorf("%s: display_name is required", pathRelative(v.metadataDir, path))
		}
		if !allowedTemplateRoles[parsed.TemplateRole] {
			v.errorf("%s: template_role %q is invalid", pathRelative(v.metadataDir, path), parsed.TemplateRole)
		}
		if !allowedRolloutGroups[parsed.RolloutGroup] {
			v.errorf("%s: rollout_group %q is invalid", pathRelative(v.metadataDir, path), parsed.RolloutGroup)
		}
		if !allowedStatuses[parsed.AcceptanceStatus] {
			v.errorf("%s: acceptance_status %q is invalid", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
		}
		if len(parsed.MetadataPaths) == 0 {
			v.errorf("%s: metadata_paths cannot be empty", pathRelative(v.metadataDir, path))
		}
		for _, metadataPath := range parsed.MetadataPaths {
			if !fileExists(filepath.Join(v.metadataDir, metadataPath)) {
				v.errorf("%s: metadata_paths entry %q does not exist", pathRelative(v.metadataDir, path), metadataPath)
			}
		}
		if len(parsed.ServiceNames) == 0 {
			v.errorf("%s: service_names cannot be empty", pathRelative(v.metadataDir, path))
		}
		for key := range requiredControlPlaneKeys {
			controlPlane, ok := parsed.ControlPlanes[key]
			if !ok {
				v.errorf("%s: missing control_planes.%s", pathRelative(v.metadataDir, path), key)
				continue
			}
			if controlPlane.Enabled {
				if len(controlPlane.ObjectTypes) == 0 {
					v.errorf("%s: control_planes.%s.object_types cannot be empty when enabled", pathRelative(v.metadataDir, path), key)
				}
				if len(controlPlane.ConfigPrefixes) == 0 {
					v.errorf("%s: control_planes.%s.config_prefixes cannot be empty when enabled", pathRelative(v.metadataDir, path), key)
				}
			}
		}
		missingCodegenTargets := missingItems(parsed.MinimumPackage.CodegenTargets, schema.Schema.RequiredCodegenTargets)
		for _, target := range parsed.MinimumPackage.CodegenTargets {
			if !allowedCodegenTargets[target] {
				v.errorf("%s: codegen_targets entry %q is invalid", pathRelative(v.metadataDir, path), target)
			}
		}
		if len(parsed.MinimumPackage.CodegenTargets) == 0 {
			v.errorf("%s: minimum_package.codegen_targets cannot be empty", pathRelative(v.metadataDir, path))
		}
		if len(missingCodegenTargets) > 0 {
			v.errorf("%s: minimum_package.codegen_targets missing required targets %q", pathRelative(v.metadataDir, path), strings.Join(missingCodegenTargets, ", "))
		}
		for _, filePath := range parsed.MinimumPackage.MetadataFiles {
			if !fileExists(filepath.Join(v.repoRoot(), filePath)) {
				v.errorf("%s: metadata_files entry %q does not exist", pathRelative(v.metadataDir, path), filePath)
			}
		}
		if len(parsed.MinimumPackage.MetadataFiles) == 0 {
			v.errorf("%s: minimum_package.metadata_files cannot be empty", pathRelative(v.metadataDir, path))
		}
		for layer := range allowedLayers {
			files := parsed.MinimumPackage.TestEvidence[layer]
			if files == nil {
				v.errorf("%s: missing minimum_package.test_evidence.%s", pathRelative(v.metadataDir, path), layer)
				continue
			}
			for _, filePath := range files {
				if !fileExists(filepath.Join(v.repoRoot(), filePath)) {
					v.errorf("%s: test_evidence.%s entry %q does not exist", pathRelative(v.metadataDir, path), layer, filePath)
				}
			}
		}
		if parsed.Deployment.PlaneBindingDomain == "" || parsed.Deployment.PlaneBindingSource == "" || parsed.Deployment.CurrentBindingSource == "" {
			v.errorf("%s: deployment plane binding fields are required", pathRelative(v.metadataDir, path))
		}
		if parsed.Deployment.PlaneBindingDomain != parsed.Domain {
			v.errorf("%s: deployment.plane_binding_domain must equal domain", pathRelative(v.metadataDir, path))
		}
		if parsed.Deployment.PlaneBindingSource != schema.MinimumPackage.RequiredDeploySources.PlaneAware {
			v.errorf("%s: deployment.plane_binding_source must equal %q", pathRelative(v.metadataDir, path), schema.MinimumPackage.RequiredDeploySources.PlaneAware)
		}
		if parsed.Deployment.CurrentBindingSource != schema.MinimumPackage.RequiredDeploySources.Current {
			v.errorf("%s: deployment.current_binding_source must equal %q", pathRelative(v.metadataDir, path), schema.MinimumPackage.RequiredDeploySources.Current)
		}
		if parsed.TemplateRole == "template_seed" && parsed.Replication.SourceTemplate != parsed.Domain {
			v.errorf("%s: template_seed domain must self-reference replication.source_template", pathRelative(v.metadataDir, path))
		}
		if rule, ok := statusRules[parsed.AcceptanceStatus]; ok {
			for _, layer := range rule.MinTestLayers {
				if len(parsed.MinimumPackage.TestEvidence[layer]) == 0 {
					v.errorf("%s: %s requires non-empty %s evidence", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus, layer)
				}
			}
			if rule.RequireAllCodegenTargets && len(missingCodegenTargets) > 0 {
				v.errorf("%s: %s requires all required codegen targets", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
			}
			if rule.RequirePlaneBinding {
				if parsed.Deployment.PlaneBindingDomain == "" || parsed.Deployment.PlaneBindingSource == "" || parsed.Deployment.CurrentBindingSource == "" {
					v.errorf("%s: %s requires deployment plane binding fields", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
				}
			}
			if rule.RequireBlockingGapsCleared && len(parsed.BlockingGaps) > 0 {
				v.errorf("%s: %s requires blocking_gaps to be empty", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
			}
		}
		if threshold, ok := statusRank["integration_pass_with_gaps"]; ok && statusRank[parsed.AcceptanceStatus] >= threshold && len(parsed.MinimumPackage.TestEvidence["t3"]) == 0 {
			v.errorf("%s: %s requires non-empty t3 evidence", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
		}
		if threshold, ok := statusRank["deploy_bound"]; ok && statusRank[parsed.AcceptanceStatus] >= threshold && len(parsed.MinimumPackage.TestEvidence["t1"]) == 0 {
			v.errorf("%s: %s requires non-empty t1 evidence", pathRelative(v.metadataDir, path), parsed.AcceptanceStatus)
		}
	}

	if !seenDomains[schema.MinimumPackage.TemplateDomain] {
		v.errorf("_control_plane/domains: template domain %q not found", schema.MinimumPackage.TemplateDomain)
	}
	for _, domain := range schema.MinimumPackage.FirstWaveReplicaDomains {
		if !seenDomains[domain] {
			v.errorf("_control_plane/domains: first-wave replica domain %q not found", domain)
		}
	}
}
