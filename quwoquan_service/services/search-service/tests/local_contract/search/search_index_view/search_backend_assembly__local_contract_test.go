package local_contract

import (
	"testing"

	searchbackend "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/searchbackend"
)

func TestBuildRejectsMissingRecallBackend(t *testing.T) {
	if _, err := searchbackend.Build(searchbackend.ESConfig{}); err == nil {
		t.Fatal("disabled Elasticsearch must fail")
	}
	if _, err := searchbackend.Build(searchbackend.ESConfig{Enabled: true}); err == nil {
		t.Fatal("enabled Elasticsearch without endpoints must fail")
	}
}
