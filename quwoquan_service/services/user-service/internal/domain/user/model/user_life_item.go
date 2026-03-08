package model

import "time"

type UserLifeItem struct {
	ID        string    `json:"id" db:"id"`
	UserID    string    `json:"userId" db:"user_id"`
	Category  string    `json:"category" db:"category"`
	Title     string    `json:"title" db:"title"`
	Subtitle  string    `json:"subtitle" db:"subtitle"`
	ImageURL  string    `json:"imageUrl" db:"image_url"`
	RefID     string    `json:"refId" db:"ref_id"`
	SortOrder int       `json:"sortOrder" db:"sort_order"`
	CreatedAt time.Time `json:"createdAt" db:"created_at"`
	UpdatedAt time.Time `json:"updatedAt" db:"updated_at"`
}
