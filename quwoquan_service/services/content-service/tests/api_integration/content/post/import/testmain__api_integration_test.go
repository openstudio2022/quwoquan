//go:build mongo_integration

package api_integration

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
)

var testMongoURI string

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(context.Background(), 3*time.Minute)
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		testinfra.UniqueDatabaseName("content_post_import_api_integration"),
	)
	startupCancel()
	if err != nil {
		panic("content-service import contract requires a real MongoDB replica set: " + err.Error())
	}

	if mongoRuntime.Source == testinfra.DependencySourceExternal {
		testMongoURI = strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
		if testMongoURI == "" {
			testMongoURI = strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI"))
		}
	} else {
		testMongoURI = fmt.Sprintf(
			"mongodb://%s/?replicaSet=%s&directConnection=true",
			mongoRuntime.Endpoint,
			mongoRuntime.ReplicaSet,
		)
	}

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = mongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}
