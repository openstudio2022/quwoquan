package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestContentAppConfigHasNoStandaloneDecoderEmitter(t *testing.T) {
	mainSource, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatalf("read codegen entrypoint: %v", err)
	}
	for _, retired := range []string{
		"writeContent" + "AppConfigClientDart",
		"content_app_config_client" + "_dto.g.dart",
		"content_" + "dtos.dart",
	} {
		if strings.Contains(string(mainSource), retired) {
			t.Fatalf("codegen entrypoint still emits retired AppConfig decoder %q", retired)
		}
	}

	for _, generator := range []string{
		"content_app_config_client_codegen.go",
		"content_dtos_barrel_codegen.go",
	} {
		matches, err := filepath.Glob(generator)
		if err != nil {
			t.Fatalf("scan retired Content generator %s: %v", generator, err)
		}
		if len(matches) != 0 {
			t.Fatalf("retired standalone Content generator still exists: %v", matches)
		}
	}
}
