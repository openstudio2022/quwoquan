package application

import "testing"

func TestProductionDependenciesFailFastWhenMissing(t *testing.T) {
	tests := []struct {
		name string
		run  func()
	}{
		{
			name: "event publisher",
			run: func() {
				requireEventPublisher(nil)
			},
		},
		{
			name: "group avatar scheduler",
			run: func() {
				requireGroupAvatarTaskScheduler(nil)
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			deferred := false
			defer func() {
				if recover() == nil {
					t.Fatal("missing production dependency must fail during composition")
				}
				deferred = true
			}()
			test.run()
			if deferred {
				t.Fatal("dependency validation returned unexpectedly")
			}
		})
	}
}
