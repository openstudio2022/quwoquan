package main

import (
	"strings"
	"testing"
)

func TestRenderWireKeysClassUsesNonProjectionIdentity(t *testing.T) {
	t.Parallel()

	generated, err := renderWireKeysClassDart([]byte(`
wire_keys_class: ContentPostImmersiveWireKeys
description: canonical raw wire keys
keys:
- const_name: visibility
  json_key: visibility
`), "content/content/post/projections/content_post_immersive_wire_keys.yaml")
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"abstract final class ContentPostImmersiveWireKeys",
		"static const String visibility = 'visibility';",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("generated wire keys are missing %q:\n%s", expected, generated)
		}
	}
}
