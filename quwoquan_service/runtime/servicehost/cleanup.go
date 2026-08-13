package servicehost

// ChainCleanup captures the current cleanup callback before prepending the next
// action. Capturing by value prevents recursive closure chains when modules
// register several resources during construction.
func ChainCleanup(previous func(), action func()) func() {
	return func() {
		action()
		previous()
	}
}
