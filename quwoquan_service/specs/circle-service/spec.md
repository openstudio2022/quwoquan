# circle-service

## Purpose

云侧圈子服务：圈子 CRUD、活动流、成员、权限、圈子内推荐与圈子行为反馈。

---

## ADDED Requirements

### Requirement: 圈子 CRUD

系统 MUST 提供圈子创建、读取、更新、删除接口。

#### Scenario: 圈子列表拉取

- **WHEN** 客户端请求 `GET /v1/circles?category=&page=1&limit=20`
- **THEN** 系统返回圈子列表，含 id、名称、封面、成员数、活动数等

#### Scenario: 圈子详情

- **WHEN** 客户端请求 `GET /v1/circles/{circleId}`
- **THEN** 系统返回圈子详情，含配置、成员列表概要、主频道等

### Requirement: 圈子活动流

系统 MUST 提供圈子活动流接口，支持分页与圈子内推荐排序。

#### Scenario: 活动流拉取

- **WHEN** 客户端请求 `GET /v1/circles/{circleId}/activities?page=1&limit=20`
- **THEN** 系统返回该圈子内活动列表

#### Scenario: 圈子内推荐

- **WHEN** 请求含 `sort=recommend` 且用户已加入圈子
- **THEN** 系统按用户在该圈子的行为进行个性化排序

### Requirement: 圈子成员与权限

系统 MUST 提供成员管理接口，支持加入、退出、角色与权限校验。

#### Scenario: 加入圈子

- **WHEN** 客户端请求 `POST /v1/circles/{circleId}/members` 携带 userId
- **THEN** 系统将用户加入圈子并返回 201

#### Scenario: 权限校验

- **WHEN** 客户端请求需权限的操作（如发布、管理）
- **THEN** 系统校验用户在该圈子的角色与权限

### Requirement: 圈子行为上报

系统 MUST 提供圈子内行为上报接口，支持访问、点击、停留、互动等，eventType 至少包含：impression、click、dwell、like、favorite、dislike、report、share。

#### Scenario: 行为上报

- **WHEN** 客户端请求 `POST /v1/circles/behaviors` 携带 circleId、activityId、eventType、timestamp、durationMs
- **THEN** 系统落库并返回 204

#### Scenario: 圈子行为驱动推荐优化

- **WHEN** 圈子行为落库后
- **THEN** 圈子内推荐可将行为纳入排序与策略更新
