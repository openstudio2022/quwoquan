package main

import (
	"strings"
	"testing"
)

func TestRenderContentMediaUploadPolicyDartPreservesPerTypeLimits(t *testing.T) {
	t.Parallel()

	rendered := renderContentMediaUploadPolicyDart(&contentMediaUploadPolicyFile{
		StreamingRequired: true,
		MediaTypes: map[string]contentMediaUploadTypeDef{
			"image": {
				MaxFileSizeBytes:    50,
				AllowedContentTypes: []string{"image/jpeg"},
			},
			"video": {
				MaxFileSizeBytes:    60,
				AllowedContentTypes: []string{"video/mp4"},
			},
			"audio": {
				MaxFileSizeBytes:    10,
				AllowedContentTypes: []string{"audio/aac"},
			},
			"file": {
				MaxFileSizeBytes:    100,
				AllowedContentTypes: []string{"*/*"},
			},
		},
		Errors: contentMediaUploadErrorDef{
			FileTooLarge:    "CONTENT.USER.media_file_too_large",
			UnsupportedType: "CONTENT.USER.media_type_unsupported",
		},
	})

	for _, expected := range []string{
		"final class ContentMediaUploadTypePolicy",
		"static const Map<String, ContentMediaUploadTypePolicy> mediaTypes",
		`"image": ContentMediaUploadTypePolicy(`,
		"maxFileSizeBytes: 50",
		`"video": ContentMediaUploadTypePolicy(`,
		"maxFileSizeBytes: 60",
		`"audio": ContentMediaUploadTypePolicy(`,
		"maxFileSizeBytes: 10",
		`"file": ContentMediaUploadTypePolicy(`,
		"maxFileSizeBytes: 100",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated Dart missing %q:\n%s", expected, rendered)
		}
	}
	if strings.Contains(rendered, "static const int maxFileSizeBytes =") {
		t.Fatalf("generated Dart must not collapse per-type limits:\n%s", rendered)
	}
}
