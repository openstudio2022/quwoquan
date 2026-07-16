//go:build mongo_integration

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
			panic(
				"content-service import contract requires a real MongoDB; " +
					"set QWQ_TEST_MONGO_URI/TEST_MONGO_URI or start Docker: " +
					runErr.Error(),
			)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		testMongoURI = uri + "&directConnection=true"
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
	c, err = mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	return
}
