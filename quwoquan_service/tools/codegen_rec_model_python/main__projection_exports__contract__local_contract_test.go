package main

import (
	"strings"
	"testing"
)

func TestGenerateModelsInitProjectionExports(t *testing.T) {
	t.Run("empty projections do not import retired models", func(t *testing.T) {
		generated := generateModelsInit(nil)
		if strings.Contains(generated, "from .projections") {
			t.Fatalf("empty projection metadata must not emit projection imports:\n%s", generated)
		}
	})

	t.Run("current projections define the exported classes", func(t *testing.T) {
		generated := generateModelsInit([]projectionSpec{
			{ReadModel: "ModelRegistry"},
			{ReadModel: "TrainingSamples"},
		})
		for _, expected := range []string{"ModelRegistryEntry", "TrainingSample"} {
			if !strings.Contains(generated, expected) {
				t.Fatalf("generated exports missing %q:\n%s", expected, generated)
			}
		}
	})
}
