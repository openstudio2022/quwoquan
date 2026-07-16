package application

import "testing"

func TestProductionDependenciesFailFastWhenMissing(t *testing.T) {
	tests := []struct {
		name string
		run  func()
	}{
		{
			name: "user event publisher",
			run: func() {
				requireUserEventPublisher(nil)
			},
		},
		{
			name: "conversation gateway",
			run: func() {
				requireConversationGateway(nil)
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			defer func() {
				if recover() == nil {
					t.Fatal("missing production dependency must fail during composition")
				}
			}()
			test.run()
		})
	}
}
