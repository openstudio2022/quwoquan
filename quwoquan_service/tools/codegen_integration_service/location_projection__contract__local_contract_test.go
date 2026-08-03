package main

import (
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestLocationMetadataUsesCanonicalProjectionFields(t *testing.T) {
	var projection locationProjectionFile
	if err := yaml.Unmarshal([]byte(`
read_model: LocationPoi
fields:
- name: id
- name: latitude
`), &projection); err != nil {
		t.Fatal(err)
	}
	routes := serviceRoutesFile{ResponseListKey: "items"}
	routes.APIRoutes = []apiRoute{
		{Operation: "GetNearbyLocations", Path: "/integration/location/nearby"},
		{Operation: "SearchLocations", Path: "/integration/location/search"},
	}
	generated := renderLocationMetadata(
		routes,
		projection,
		"operations.yaml",
		"projections/location_poi.yaml",
	)
	for _, expected := range []string{
		`const FieldKeyId = "id"`,
		`const FieldKeyLatitude = "latitude"`,
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("canonical projection field missing from generated metadata: %s", generated)
		}
	}
	if strings.Contains(generated, "client_projection") {
		t.Fatal("generator must not restore the retired client_projection truth source")
	}
}
