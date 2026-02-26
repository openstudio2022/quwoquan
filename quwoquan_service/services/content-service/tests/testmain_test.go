package tests

import (
	"net/http"
	"os"
	"testing"

	"github.com/alicebob/miniredis/v2"

	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/testinfra"
	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

var (
	testHandler http.Handler
	eventSpy    *testinfra.EventSpy
	// postStore is exported within-package to allow per-test state setup.
	// MongoDB migration pending: PostStore is currently in-memory.
	// When persistence.MongoPostStore is added, replace this with a
	// testcontainers mongo:7 instance via testinfra.NewSuite.
	postStore *persistence.PostStore
)

func TestMain(m *testing.M) {
	eventSpy = testinfra.NewEventSpy()

	// Use miniredis.Run() which does not require *testing.T so it works in TestMain.
	mr, err := miniredis.Run()
	if err != nil {
		panic("failed to start miniredis: " + err.Error())
	}

	// Wire real Redis client pointing at miniredis for the hot-path.
	redis := recinfra.NewRedisClientAdapter(mr.Addr(), "", 0)
	hotPath := rtrec.NewHotPath(redis)

	// Empty store — does NOT call DefaultSeedPosts() to comply with L2 rule.
	// Tests create the data they need via the HTTP API.
	postStore = persistence.NewPostStore(nil)
	source := recinfra.NewPostRepositorySource(postStore)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := application.NewFeedService(engine, source)
	postService := application.NewPostService(postStore)
	behaviorService := application.NewBehaviorService(hotPath, postStore)
	testHandler = contenhttp.NewContentHandler(feedService, postService, behaviorService).Routes()

	code := m.Run()
	mr.Close()
	os.Exit(code)
}
