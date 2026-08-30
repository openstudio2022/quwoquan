package main

import (
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
	bootstrap "quwoquan_service/services/tag-service/cmd/api"
)

func main() {
	servicekit.RunStandalone("tag-service", func() (servicehost.Module, error) {
		module, err := bootstrap.NewModule()
		if err != nil {
			return nil, err
		}
		return module, nil
	})
}
