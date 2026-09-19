// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestSearchCirclePresentationContractAuthoringGeneratesTypedRequests(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		_, issues, validationErr := compiler.Validate(metadataDir, validate.ProfileBaseline)
		t.Fatalf("%v; compiler issues=%+v; validation error=%v", err, issues, validationErr)
	}
	graphOperations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(graphOperations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatal(err)
	}
	wanted := map[string]string{
		"search.search_index_view.Search":              "CanonicalSearchQuery",
		"circle.circle.GetCircleFeed":                  "CircleFeedQuery",
		"gateway.persisted_query_execution.SearchPage": "SearchPageInput",
	}
	lock := appContractLock{}
	for index, operation := range operations {
		op := graphOperations[index]
		requestType, selected := wanted[op.ID]
		if !selected {
			continue
		}
		operation.CanonicalOperationID, operation.LocalOperationID = op.ID, op.LocalID
		if operation.ClientContract == nil || operation.RequestEntity != requestType {
			t.Fatalf("%s lost canonical typed request %s", op.ID, requestType)
		}
		if op.ID == "circle.circle.GetCircleFeed" {
			found := false
			for _, binding := range op.RequestBindings.Query {
				if binding.Field != "clientPresentationContract" {
					continue
				}
				found = true
				if binding.Name != binding.Field || binding.Encoding != "json" || binding.MaxBytes != 8192 || binding.Required == nil || *binding.Required {
					t.Fatalf("Circle capability binding drift: %+v", binding)
				}
			}
			if !found {
				t.Fatal("Circle capability JSON query binding missing")
			}
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if len(lock.AppExposedOperations) != len(wanted) {
		t.Fatalf("selected operations=%d want=%d", len(lock.AppExposedOperations), len(wanted))
	}
	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := writeGeneratedOperationRequests(appDir, lock, provided); err != nil {
		t.Fatal(err)
	}
	for _, domain := range []string{"search", "circle", "gateway"} {
		root := filepath.Join(appDir, "packages/quwoquan_cloud_contracts/lib/src", domain)
		var generated strings.Builder
		if err := filepath.WalkDir(root, func(path string, entry os.DirEntry, err error) error {
			if err != nil || entry.IsDir() {
				return err
			}
			data, err := os.ReadFile(path)
			generated.Write(data)
			return err
		}); err != nil {
			t.Fatal(err)
		}
		text := generated.String()
		if !strings.Contains(text, "final ClientContentPresentationContract? clientPresentationContract;") {
			t.Fatalf("%s lost nullable shared capability type", domain)
		}
		if strings.Contains(text, "final class ClientContentPresentationContract {") {
			t.Fatalf("%s introduced a duplicate shared capability DTO", domain)
		}
		if !strings.Contains(text, "clientPresentationContract.toWire()") && !strings.Contains(text, "clientPresentationContract!.toWire()") {
			t.Fatalf("%s dropped typed capability serialization", domain)
		}
		if domain == "circle" && !strings.Contains(text, "_encodeGeneratedJSONQuery(request.clientPresentationContract.toWire(), 8192)") && !strings.Contains(text, "_encodeGeneratedJSONQuery(request.clientPresentationContract!.toWire(), 8192)") {
			t.Fatal("Circle request did not compile to bounded JSON query")
		}
	}
}
