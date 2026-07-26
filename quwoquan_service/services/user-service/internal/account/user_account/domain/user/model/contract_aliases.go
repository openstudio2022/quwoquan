package model

import (
	accountcontract "quwoquan_service/services/user-service/generated/account/user_account/contract/user"
	personacontract "quwoquan_service/services/user-service/generated/persona_management/persona/contract/user"
)

// Object-local generated contracts are surfaced through the existing domain
// package so handwritten rules never have to depend on persistence packages.
type UserAccount = accountcontract.UserAccount
type UserProfile = accountcontract.UserAccount
type AnonymousDeviceBinding = accountcontract.AnonymousDeviceBinding
type ConsentRecord = accountcontract.ConsentRecord
type ProfileQrToken = accountcontract.ProfileQrToken
type UserAuth = accountcontract.UserAuth
type Persona = personacontract.Persona
