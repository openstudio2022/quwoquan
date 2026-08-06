package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validatePrivacyGovernance(contractGraph *graph.ContractGraph) []Issue {
	objects := make(map[string]ast.Object, len(contractGraph.Objects))
	for _, object := range contractGraph.Objects {
		objects[object.ID] = object
	}
	rootFields := map[string]map[string]ast.FieldDefinition{}
	for _, field := range contractGraph.Governance.Fields {
		object, exists := objects[field.ObjectID]
		if !exists || field.Entity != object.Name {
			continue
		}
		if rootFields[field.ObjectID] == nil {
			rootFields[field.ObjectID] = map[string]ast.FieldDefinition{}
		}
		rootFields[field.ObjectID][field.Name] = field
	}

	var issues []Issue
	for _, packet := range contractGraph.Governance.Objects {
		privacy := packet.Privacy
		if privacy == nil {
			continue
		}
		object, exists := objects[packet.ObjectID]
		if !exists {
			continue
		}
		if privacy.ObjectID != packet.ObjectID {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.IDENTITY_MISMATCH",
				privacy.SourcePath,
				"privacy identity %q must be derived as owning object %q",
				privacy.ObjectID,
				packet.ObjectID,
			))
		}
		document := privacy.Document
		if strings.TrimSpace(document.Description) == "" {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.MISSING_DESCRIPTION",
				privacy.SourcePath,
				"privacy %s must describe its object-local policy",
				object.ID,
			))
		}

		issues = append(issues, validatePrivacyAppLogPolicy(
			object,
			privacy.SourcePath,
			rootFields[packet.ObjectID],
			document.AppLogPolicy,
		)...)
		issues = append(issues, validatePrivacyVisibility(
			object,
			privacy.SourcePath,
			rootFields[packet.ObjectID],
			document.FieldVisibility,
		)...)
		issues = append(issues, validatePrivacyLifecycle(
			object,
			privacy.SourcePath,
			rootFields[packet.ObjectID],
			objects,
			document.DataLifecycle,
		)...)
	}
	return issues
}

func validatePrivacyAppLogPolicy(
	object ast.Object,
	sourcePath string,
	fields map[string]ast.FieldDefinition,
	policies []ast.PrivacyAppLogPolicy,
) []Issue {
	var issues []Issue
	seen := map[string]struct{}{}
	for _, policy := range policies {
		fieldName := strings.TrimSpace(policy.Field)
		if _, duplicate := seen[fieldName]; duplicate {
			issues = append(issues, duplicatePrivacyFieldIssue(
				sourcePath, "app_log_policy", fieldName,
			))
			continue
		}
		seen[fieldName] = struct{}{}
		field, exists := fields[fieldName]
		if !exists {
			issues = append(issues, unknownPrivacyFieldIssue(
				object.ID, sourcePath, "app_log_policy", fieldName,
			))
			continue
		}

		if !isPrivacyClassification(policy.Classification) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.INVALID_CLASSIFICATION",
				sourcePath,
				"privacy %s app_log_policy field %q has unknown classification %q",
				object.ID,
				fieldName,
				policy.Classification,
			))
		} else if !privacyClassificationCovers(field.Classification, policy.Classification) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.CLASSIFICATION_DOWNGRADE",
				sourcePath,
				"privacy %s app_log_policy field %q classification %q is not at least as restrictive as fields.yaml classification %q",
				object.ID,
				fieldName,
				policy.Classification,
				field.Classification,
			))
		}

		if !fieldLogPolicyAllowsPrivacyAction(field.LogPolicy, policy.AppLog) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.LOG_POLICY_WIDENED",
				sourcePath,
				"privacy %s app_log_policy field %q action %q is more permissive than fields.yaml log_policy %q",
				object.ID,
				fieldName,
				policy.AppLog,
				field.LogPolicy,
			))
		}
		if !classificationAllowsPrivacyAction(policy.Classification, policy.AppLog) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.UNSAFE_APP_LOG_ACTION",
				sourcePath,
				"privacy %s app_log_policy field %q classification %q forbids action %q",
				object.ID,
				fieldName,
				policy.Classification,
				policy.AppLog,
			))
		}
		if !validAppLogParameters(policy) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.INVALID_APP_LOG_PARAMETERS",
				sourcePath,
				"privacy %s app_log_policy field %q action %q has incompatible mask/truncate parameters",
				object.ID,
				fieldName,
				policy.AppLog,
			))
		}
	}
	return issues
}

func validatePrivacyVisibility(
	object ast.Object,
	sourcePath string,
	fields map[string]ast.FieldDefinition,
	policies []ast.PrivacyFieldVisibility,
) []Issue {
	var issues []Issue
	seenFields := map[string]struct{}{}
	for _, policy := range policies {
		fieldName := strings.TrimSpace(policy.Field)
		if _, duplicate := seenFields[fieldName]; duplicate {
			issues = append(issues, duplicatePrivacyFieldIssue(
				sourcePath, "field_visibility", fieldName,
			))
			continue
		}
		seenFields[fieldName] = struct{}{}
		if _, exists := fields[fieldName]; !exists {
			issues = append(issues, unknownPrivacyFieldIssue(
				object.ID, sourcePath, "field_visibility", fieldName,
			))
		}
		visibilitySeen := map[string]struct{}{}
		for _, consumer := range policy.Visibility {
			consumer = strings.TrimSpace(consumer)
			if _, duplicate := visibilitySeen[consumer]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.PRIVACY.DUPLICATE_VISIBILITY",
					sourcePath,
					"privacy %s field_visibility field %q repeats consumer %q",
					object.ID,
					fieldName,
					consumer,
				))
				continue
			}
			visibilitySeen[consumer] = struct{}{}
			if !isPrivacyVisibility(consumer) {
				issues = append(issues, issue(
					"CONTRACT.PRIVACY.UNKNOWN_VISIBILITY",
					sourcePath,
					"privacy %s field_visibility field %q has unknown consumer %q",
					object.ID,
					fieldName,
					consumer,
				))
			}
		}
		if len(policy.Visibility) == 0 ||
			(len(policy.Visibility) > 1 &&
				(privacyContainsString(policy.Visibility, "all") ||
					privacyContainsString(policy.Visibility, "never_expose"))) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.INVALID_VISIBILITY_SET",
				sourcePath,
				"privacy %s field_visibility field %q must have a non-empty consumer set and all/never_expose must be exclusive",
				object.ID,
				fieldName,
			))
		}
	}
	return issues
}

func validatePrivacyLifecycle(
	object ast.Object,
	sourcePath string,
	fields map[string]ast.FieldDefinition,
	objects map[string]ast.Object,
	lifecycle *ast.PrivacyDataLifecycle,
) []Issue {
	if lifecycle == nil {
		return nil
	}
	var issues []Issue
	if lifecycle.RetentionDays == nil || *lifecycle.RetentionDays < 0 {
		issues = append(issues, issue(
			"CONTRACT.PRIVACY.INVALID_RETENTION",
			sourcePath,
			"privacy %s data_lifecycle requires non-negative retention_days",
			object.ID,
		))
	}
	if lifecycle.DeletionOnUserRequest == nil {
		issues = append(issues, issue(
			"CONTRACT.PRIVACY.MISSING_DELETION_DECISION",
			sourcePath,
			"privacy %s data_lifecycle must explicitly decide deletion_on_user_request",
			object.ID,
		))
	} else if !*lifecycle.DeletionOnUserRequest &&
		(len(lifecycle.DeletionCascade) > 0 || len(lifecycle.AnonymizationOnDelete) > 0) {
		issues = append(issues, issue(
			"CONTRACT.PRIVACY.INACTIVE_DELETION_POLICY",
			sourcePath,
			"privacy %s declares deletion/anonymization work while deletion_on_user_request is false",
			object.ID,
		))
	}

	seenTargets := map[string]struct{}{}
	for _, target := range lifecycle.DeletionCascade {
		targetID := strings.TrimSpace(target.ObjectID)
		if _, duplicate := seenTargets[targetID]; duplicate {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.DUPLICATE_DELETION_TARGET",
				sourcePath,
				"privacy %s references deletion target %q more than once",
				object.ID,
				targetID,
			))
			continue
		}
		seenTargets[targetID] = struct{}{}
		if _, exists := objects[targetID]; !exists {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.UNKNOWN_DELETION_TARGET",
				sourcePath,
				"privacy %s references unknown canonical object %q",
				object.ID,
				targetID,
			))
		}
		if !validDeletionStrategy(target) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.INVALID_DELETION_STRATEGY",
				sourcePath,
				"privacy %s deletion target %q has invalid strategy parameters",
				object.ID,
				targetID,
			))
		}
	}

	seenFields := map[string]struct{}{}
	for _, policy := range lifecycle.AnonymizationOnDelete {
		fieldName := strings.TrimSpace(policy.Field)
		if _, duplicate := seenFields[fieldName]; duplicate {
			issues = append(issues, duplicatePrivacyFieldIssue(
				sourcePath, "anonymization_on_delete", fieldName,
			))
			continue
		}
		seenFields[fieldName] = struct{}{}
		if _, exists := fields[fieldName]; !exists {
			issues = append(issues, unknownPrivacyFieldIssue(
				object.ID, sourcePath, "anonymization_on_delete", fieldName,
			))
		}
		if !validAnonymization(policy) {
			issues = append(issues, issue(
				"CONTRACT.PRIVACY.INVALID_ANONYMIZATION_STRATEGY",
				sourcePath,
				"privacy %s anonymization field %q has invalid strategy parameters",
				object.ID,
				fieldName,
			))
		}
	}
	return issues
}

func duplicatePrivacyFieldIssue(sourcePath string, kind string, field string) Issue {
	return issue(
		"CONTRACT.PRIVACY.DUPLICATE_FIELD_REFERENCE",
		sourcePath,
		"privacy %s references field %q more than once",
		kind,
		field,
	)
}

func unknownPrivacyFieldIssue(
	objectID string,
	sourcePath string,
	kind string,
	field string,
) Issue {
	return issue(
		"CONTRACT.PRIVACY.UNKNOWN_FIELD",
		sourcePath,
		"privacy %s %s references unknown root field %q",
		objectID,
		kind,
		field,
	)
}

func isPrivacyClassification(value ast.PrivacyClassification) bool {
	switch value {
	case ast.PrivacyClassificationPublic,
		ast.PrivacyClassificationInternal,
		ast.PrivacyClassificationPII,
		ast.PrivacyClassificationSensitive,
		ast.PrivacyClassificationSecret:
		return true
	default:
		return false
	}
}

func privacyClassificationCovers(
	fieldClassification string,
	effective ast.PrivacyClassification,
) bool {
	switch strings.TrimSpace(fieldClassification) {
	case "PUBLIC":
		return isPrivacyClassification(effective)
	case "INTERNAL":
		return effective == ast.PrivacyClassificationInternal ||
			effective == ast.PrivacyClassificationPII ||
			effective == ast.PrivacyClassificationSensitive ||
			effective == ast.PrivacyClassificationSecret
	case "PII":
		return effective == ast.PrivacyClassificationPII ||
			effective == ast.PrivacyClassificationSecret
	case "SENSITIVE":
		return effective == ast.PrivacyClassificationSensitive ||
			effective == ast.PrivacyClassificationSecret
	case "SECRET":
		return effective == ast.PrivacyClassificationSecret
	default:
		return false
	}
}

func fieldLogPolicyAllowsPrivacyAction(
	fieldPolicy string,
	action ast.PrivacyAppLogAction,
) bool {
	switch strings.TrimSpace(fieldPolicy) {
	case "allow":
		return isPrivacyAppLogAction(action)
	case "mask":
		return action == ast.PrivacyAppLogMask ||
			action == ast.PrivacyAppLogDrop ||
			action == ast.PrivacyAppLogCountOnly
	case "drop":
		return action == ast.PrivacyAppLogDrop
	case "metadata_only":
		return action == ast.PrivacyAppLogDrop ||
			action == ast.PrivacyAppLogCountOnly
	default:
		return false
	}
}

func classificationAllowsPrivacyAction(
	classification ast.PrivacyClassification,
	action ast.PrivacyAppLogAction,
) bool {
	switch classification {
	case ast.PrivacyClassificationPublic:
		return isPrivacyAppLogAction(action)
	case ast.PrivacyClassificationInternal:
		return action == ast.PrivacyAppLogMask ||
			action == ast.PrivacyAppLogDrop ||
			action == ast.PrivacyAppLogCountOnly
	case ast.PrivacyClassificationPII:
		return action == ast.PrivacyAppLogMask ||
			action == ast.PrivacyAppLogDrop ||
			action == ast.PrivacyAppLogCountOnly
	case ast.PrivacyClassificationSensitive:
		return action == ast.PrivacyAppLogDrop ||
			action == ast.PrivacyAppLogCountOnly
	case ast.PrivacyClassificationSecret:
		return action == ast.PrivacyAppLogDrop
	default:
		return false
	}
}

func isPrivacyAppLogAction(action ast.PrivacyAppLogAction) bool {
	switch action {
	case ast.PrivacyAppLogAllow,
		ast.PrivacyAppLogMask,
		ast.PrivacyAppLogDrop,
		ast.PrivacyAppLogTruncate,
		ast.PrivacyAppLogCountOnly,
		ast.PrivacyAppLogDropIfTooLong:
		return true
	default:
		return false
	}
}

func validAppLogParameters(policy ast.PrivacyAppLogPolicy) bool {
	switch policy.AppLog {
	case ast.PrivacyAppLogMask:
		return (policy.MaskStrategy == "city_level_only" ||
			policy.MaskStrategy == "strip_detail") && policy.TruncateChars == nil
	case ast.PrivacyAppLogTruncate:
		return policy.MaskStrategy == "" &&
			policy.TruncateChars != nil && *policy.TruncateChars > 0
	case ast.PrivacyAppLogAllow,
		ast.PrivacyAppLogDrop,
		ast.PrivacyAppLogCountOnly,
		ast.PrivacyAppLogDropIfTooLong:
		return policy.MaskStrategy == "" && policy.TruncateChars == nil
	default:
		return false
	}
}

func isPrivacyVisibility(value string) bool {
	switch value {
	case "never_expose", "all", "app", "self", "platform-ops",
		"content-service-internal", "user-service-internal":
		return true
	default:
		return false
	}
}

func validDeletionStrategy(policy ast.PrivacyDeletionCascade) bool {
	switch policy.Strategy {
	case ast.PrivacyDeletionHardDelete, ast.PrivacyDeletionSoftDelete:
		return policy.SoftDeleteFirst == nil && policy.CDNPurgeDelayHours == nil
	case ast.PrivacyDeletionSoftDeleteThenCDNPurge:
		return policy.SoftDeleteFirst != nil && *policy.SoftDeleteFirst &&
			policy.CDNPurgeDelayHours != nil && *policy.CDNPurgeDelayHours > 0
	case ast.PrivacyDeletionScrub:
		// Schema requires scrub to keep the row and overwrite personal data;
		// description must state the retention justification and scrubbed fields.
		return policy.SoftDeleteFirst == nil &&
			policy.CDNPurgeDelayHours == nil &&
			strings.TrimSpace(policy.Description) != ""
	default:
		return false
	}
}

func validAnonymization(policy ast.PrivacyAnonymization) bool {
	switch policy.Strategy {
	case ast.PrivacyAnonymizationReplaceWithPlaceholder:
		return strings.TrimSpace(policy.Placeholder) != ""
	case ast.PrivacyAnonymizationDrop:
		return policy.Placeholder == ""
	default:
		return false
	}
}

func privacyContainsString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}
