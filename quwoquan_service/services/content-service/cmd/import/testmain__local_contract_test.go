package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
)

var testMongoURI string

func TestMain(m *testing.M) {
	ctx := context.Background()
	testMongoURI = strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI"))
	if testMongoURI == "" {
		testMongoURI = strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	}

	var mongoContainer *mongomod.MongoDBContainer
	if testMongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(
				os.Stderr,
				"\n[L2] WARN: Docker unavailable, skipping content-service cmd/import mongo tests.\n"+
					"  Set QWQ_TEST_MONGO_URI or TEST_MONGO_URI to run without Docker.\n"+
					"  Error: %v\n\n",
				runErr,
			)
			os.Exit(0)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		testMongoURI = uri
	}

	code := m.Run()

	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	os.Exit(code)
}

func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy")
	return
}
