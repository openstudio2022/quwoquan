package main

import (
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
	bootstrap "quwoquan_service/services/assistant-service/cmd/api"
)

func main() {
	servicekit.RunStandalone("assistant-service", func() (servicehost.Module, error) {
		return bootstrap.NewModule()
	})
}
