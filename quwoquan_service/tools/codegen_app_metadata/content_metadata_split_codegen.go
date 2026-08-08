package main

import (
	"fmt"
	"sort"
	"strings"
)

func writeCanonicalContentMetadata(
	appDir string,
	feedCategoryToRequestType map[string]string,
	contentTypes []string,
	postSnapshotFieldByteLimits map[string]int,
) error {
	if err := validateCanonicalContentMetadata(
		feedCategoryToRequestType,
		contentTypes,
		postSnapshotFieldByteLimits,
	); err != nil {
		return err
	}
	writeFile(
		contentPostApplicationOutputPath(
			appDir,
			"content_feed_category_policy.g.dart",
		),
		renderContentFeedCategoryPolicyDart(feedCategoryToRequestType),
	)
	writeFile(
		contentPostPublicGeneratedOutputPath(
			appDir,
			"content_feed_delivery_category_policy.g.dart",
		),
		renderContentFeedDeliveryCategoryPolicyDart(feedCategoryToRequestType),
	)
	writeFile(
		contentPostDomainOutputPath(
			appDir,
			"content_post_snapshot_policy.g.dart",
		),
		renderContentPostSnapshotPolicyDart(postSnapshotFieldByteLimits),
	)
	return nil
}

func validateCanonicalContentMetadata(
	feedCategoryToRequestType map[string]string,
	contentTypes []string,
	postSnapshotFieldByteLimits map[string]int,
) error {
	if len(feedCategoryToRequestType) == 0 {
		return fmt.Errorf("canonical Content feed category policy is empty")
	}
	allowedRequestTypes := make(map[string]struct{}, len(contentTypes))
	for _, contentType := range contentTypes {
		contentType = strings.TrimSpace(contentType)
		if contentType == "" {
			return fmt.Errorf("canonical ContentType contains an empty value")
		}
		allowedRequestTypes[contentType] = struct{}{}
	}
	if len(allowedRequestTypes) == 0 {
		return fmt.Errorf("canonical ContentType vocabulary is empty")
	}
	for category, requestType := range feedCategoryToRequestType {
		if strings.TrimSpace(category) == "" || strings.TrimSpace(requestType) == "" {
			return fmt.Errorf(
				"canonical Content feed category policy contains an empty key or value",
			)
		}
		if _, ok := allowedRequestTypes[strings.TrimSpace(requestType)]; !ok {
			return fmt.Errorf(
				"canonical Content feed category %q references unknown ContentType %q",
				category,
				requestType,
			)
		}
	}
	// 空限额表意味着 App 本地 QuerySnapshot 的逐字段 byte admission 完全失效，
	// 只剩整页预算兜底。生成期直接 fail-closed，不允许再退化成空 map。
	if len(postSnapshotFieldByteLimits) == 0 {
		return fmt.Errorf("canonical Content post snapshot policy has no field byte limits")
	}
	for field, limit := range postSnapshotFieldByteLimits {
		if strings.TrimSpace(field) == "" || limit <= 0 {
			return fmt.Errorf(
				"canonical Content post snapshot policy has invalid limit %q=%d",
				field,
				limit,
			)
		}
	}
	return nil
}

func renderContentFeedCategoryPolicyDart(values map[string]string) string {
	var b strings.Builder
	b.WriteString("// Code generated from canonical Content metadata. DO NOT EDIT.\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("final class ContentFeedCategoryPolicy {\n")
	b.WriteString("  const ContentFeedCategoryPolicy._();\n\n")
	b.WriteString("  static const Map<String, String> feedCategoryToRequestType =\n")
	b.WriteString("      <String, String>{\n")
	writeSortedStringMap(&b, values)
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

func renderContentFeedDeliveryCategoryPolicyDart(values map[string]string) string {
	var b strings.Builder
	b.WriteString("// Code generated from canonical Content metadata. DO NOT EDIT.\n\n")
	b.WriteString("/// Feed Delivery 消费 Post 分类映射时使用的稳定公开边界。\n")
	b.WriteString("abstract final class ContentFeedDeliveryCategoryPolicy {\n")
	b.WriteString("  const ContentFeedDeliveryCategoryPolicy._();\n\n")
	b.WriteString("  static const Map<String, String> requestTypeByCategory =\n")
	b.WriteString("      <String, String>{\n")
	writeSortedStringMap(&b, values)
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

func renderContentPostSnapshotPolicyDart(values map[string]int) string {
	var b strings.Builder
	b.WriteString("// Code generated from canonical Content metadata. DO NOT EDIT.\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("final class ContentPostSnapshotPolicy {\n")
	b.WriteString("  const ContentPostSnapshotPolicy._();\n\n")
	b.WriteString("  static const Map<String, int> postSnapshotFieldByteLimits =\n")
	b.WriteString("      <String, int>{\n")
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		b.WriteString(fmt.Sprintf("    '%s': %d,\n", key, values[key]))
	}
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}
