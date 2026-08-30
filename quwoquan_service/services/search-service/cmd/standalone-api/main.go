package main

import (
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
	bootstrap "quwoquan_service/services/search-service/cmd/api"
)

func main() {
	servicekit.RunStandalone("search-service", func() (servicehost.Module, error) {
		return bootstrap.NewModule()
	})
}
