package clock

import "time"

type Clock interface {
	Now() time.Time
}

type SystemClock struct{}

func (SystemClock) Now() time.Time {
	return time.Now().UTC()
}

func Since(c Clock, t time.Time) time.Duration {
	return Now(c).Sub(t)
}

func Until(c Clock, t time.Time) time.Duration {
	return t.Sub(Now(c))
}

func Now(c Clock) time.Time {
	if c == nil {
		return SystemClock{}.Now()
	}
	return c.Now().UTC()
}
