// spec_ref: specs/feature-tree/discovery-content/content-service-cloud-production/remote-content-delivery/spec.md#gwt-001
package main

import (
	"sort"
	"strings"
	"testing"
)

func TestValidateDetailBundleRequiresExactPerContentTypeAssembly(t *testing.T) {
	t.Parallel()
	binding := detailBundleBindingFixture()
	plan, err := validateDetailBundle([]bundleSliceInput{
		bundleSlice("ContentPostDetailBase", binding, "postId", "contentType", "title"),
		bundleSlice("ContentPostDetailArticle", extensionBinding(binding, "article"), "articleAssetManifestSummary", "articleAssets"),
	}, []string{"postId", "contentType", "title", "articleAssetManifest"}, detailProjectionID)
	if err != nil {
		t.Fatalf("validateDetailBundle: %v", err)
	}
	if plan.Base.OperationName != "ContentPostDetailBase" || len(plan.Extensions) != 1 {
		t.Fatalf("plan=%+v", plan)
	}
}

func TestValidateDetailBundleRejectsCrossRailOrIncompleteBindings(t *testing.T) {
	t.Parallel()
	base := detailBundleBindingFixture()
	for _, test := range []struct {
		name   string
		slices []bundleSliceInput
		fields []string
		want   string
	}{
		{
			name: "two base",
			slices: []bundleSliceInput{
				bundleSlice("BaseOne", base, "postId", "contentType"),
				bundleSlice("BaseTwo", base, "title"),
			},
			fields: []string{"postId", "contentType", "title"}, want: "exactly one base",
		},
		{
			name: "extension outside closed content types",
			slices: []bundleSliceInput{
				bundleSlice("Base", base, "postId", "contentType", "title"),
				bundleSlice("Video", extensionBinding(base, "video"), "articleAssetManifestSummary", "articleAssets"),
			},
			fields: []string{"postId", "contentType", "title", "articleAssetManifest"}, want: "outside base supportedContentTypes",
		},
		{
			name: "partial mapping source",
			slices: []bundleSliceInput{
				bundleSlice("Base", base, "postId", "contentType", "title"),
				bundleSlice("Article", extensionBinding(base, "article"), "articleAssetManifestSummary"),
			},
			fields: []string{"postId", "contentType", "title", "articleAssetManifest"}, want: "assembly source articleAssets is absent",
		},
		{
			name: "signed selected fields differ from AST",
			slices: []bundleSliceInput{
				func() bundleSliceInput {
					slice := bundleSlice("Base", base, "postId", "contentType", "title")
					slice.Binding.SelectedFields = []string{"contentType", "postId"}
					return slice
				}(),
			},
			fields: []string{"postId", "contentType", "title"}, want: "AST selected fields differ",
		},
	} {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			_, err := validateDetailBundle(test.slices, test.fields, detailProjectionID)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error=%v want=%q", err, test.want)
			}
		})
	}
}

func detailBundleBindingFixture() appClientBundleBinding {
	return appClientBundleBinding{
		BundleID: detailBundleID, Role: "base",
		SupportedContentTypes: []string{"article"},
		AssemblyMappings:      []assemblyMapping{},
	}
}

func extensionBinding(base appClientBundleBinding, contentTypes ...string) appClientBundleBinding {
	base.Role = "extension"
	base.SupportedContentTypes = nil
	base.RequiredForContentTypes = append([]string(nil), contentTypes...)
	base.AssemblyMappings = []assemblyMapping{{
		TargetField: "articleAssetManifest", PresenceSourceField: "articleAssetManifestSummary",
		Sources: []assemblySource{
			{SourceField: "articleAssetManifestSummary", Strategy: "merge_object"},
			{SourceField: "articleAssets", Strategy: "assign_key", TargetKey: "assets"},
		},
	}}
	return base
}

func bundleSlice(operationName string, binding appClientBundleBinding, fields ...string) bundleSliceInput {
	sort.Strings(fields)
	binding.SelectedFields = append([]string(nil), fields...)
	return bundleSliceInput{
		OperationName: operationName, Binding: binding,
		SelectedFields: append([]string(nil), fields...),
	}
}
