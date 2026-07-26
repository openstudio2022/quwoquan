package main

import (
	"strings"
	"testing"
)

func TestLinkTemplateCodegenFillsCanonicalBraceRouteParameters(t *testing.T) {
	rendered := renderLinkTemplatesDart(
		&linkTemplatesFile{},
		&appRoutesFile{},
	)

	if !strings.Contains(
		rendered,
		`out = out.replaceAll('{$key}', Uri.encodeComponent(value));`,
	) {
		t.Fatalf("generated route filler does not replace canonical brace parameters:\n%s", rendered)
	}
	if strings.Contains(
		rendered,
		`out = out.replaceAll(':$key', Uri.encodeComponent(value));`,
	) {
		t.Fatalf("generated route filler retained unsupported colon parameter syntax")
	}
}

func TestLinkTemplateCodegenGeneratesServerCitationAllowlist(t *testing.T) {
	rendered := renderCitationDestinationsGo(&linkTemplatesFile{
		CitationDestinations: linkTemplatesCitationDestinations{
			Internal: []linkTemplatesCitationInternalDestination{
				{ObjectType: "content.post", Entity: "post"},
			},
			External: linkTemplatesCitationExternalDestinations{
				AllowedSchemes: []string{"https"},
			},
		},
	})

	for _, required := range []string{
		`"content.post": {}`,
		"func IsRegisteredInternalCitationObjectType",
		`case "https":`,
	} {
		if !strings.Contains(rendered, required) {
			t.Fatalf("generated citation registry missing %q:\n%s", required, rendered)
		}
	}
}
