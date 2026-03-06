# Personal Assistant Skill Policy Playbook V1

## Scope
This document defines the unified default policy model for the personal assistant:
- 1 global always-on policy
- 19 domain skill policies (`skill.policy.md`)

## Global Always-On Policy
- File: `quwoquan_app/assets/personal_assistant/prompts/global/stack.global_policy.md`
- Purpose:
  - enforce Markdown-only user output
  - enforce language/i18n baseline
  - enforce safety and reflection checks

## Runtime Injection
- Runtime entry: `quwoquan_app/lib/personal_assistant/engine/agent_loop.dart`
- Behavior:
  - load global policy markdown
  - load `SKILL.md`
  - load per-domain `scripts/skill.policy.md`
  - merge and inject into `domainSkillInstruction`

## Domain Policy Files (19)

| Domain | Policy File |
|---|---|
| weather | `quwoquan_app/assets/personal_assistant/skills/weather/scripts/skill.policy.md` |
| travel_transport | `quwoquan_app/assets/personal_assistant/skills/travel_transport/scripts/skill.policy.md` |
| travel_planning | `quwoquan_app/assets/personal_assistant/skills/travel_planning/scripts/skill.policy.md` |
| local_life | `quwoquan_app/assets/personal_assistant/skills/local_life/scripts/skill.policy.md` |
| calendar_task | `quwoquan_app/assets/personal_assistant/skills/calendar_task/scripts/skill.policy.md` |
| knowledge_general | `quwoquan_app/assets/personal_assistant/skills/knowledge_general/scripts/skill.policy.md` |
| finance_consumer | `quwoquan_app/assets/personal_assistant/skills/finance_consumer/scripts/skill.policy.md` |
| health_wellness | `quwoquan_app/assets/personal_assistant/skills/health_wellness/scripts/skill.policy.md` |
| education_learning | `quwoquan_app/assets/personal_assistant/skills/education_learning/scripts/skill.policy.md` |
| work_productivity | `quwoquan_app/assets/personal_assistant/skills/work_productivity/scripts/skill.policy.md` |
| shopping_decision | `quwoquan_app/assets/personal_assistant/skills/shopping_decision/scripts/skill.policy.md` |
| policy_public_service | `quwoquan_app/assets/personal_assistant/skills/policy_public_service/scripts/skill.policy.md` |
| emotion_companion | `quwoquan_app/assets/personal_assistant/skills/emotion_companion/scripts/skill.policy.md` |
| social_companion_chat | `quwoquan_app/assets/personal_assistant/skills/social_companion_chat/scripts/skill.policy.md` |
| relationship_matchmaking | `quwoquan_app/assets/personal_assistant/skills/relationship_matchmaking/scripts/skill.policy.md` |
| divination_fortune | `quwoquan_app/assets/personal_assistant/skills/divination_fortune/scripts/skill.policy.md` |
| astrology_constellation | `quwoquan_app/assets/personal_assistant/skills/astrology_constellation/scripts/skill.policy.md` |
| family_parenting | `quwoquan_app/assets/personal_assistant/skills/family_parenting/scripts/skill.policy.md` |
| fallback_general_search | `quwoquan_app/assets/personal_assistant/skills/fallback_general_search/scripts/skill.policy.md` |

## Policy Authoring Convention (Markdown First)
- Keep policy in natural language markdown.
- Each skill policy should include:
  1. persona
  2. tone
  3. language strategy
  4. domain boundaries
  5. required output sections

## Rollout Notes
- The current version is skeleton-first.
- Next iteration can enrich each domain policy with:
  - locale-specific unit style
  - taboo trigger conditions
  - stronger retrieval-quality downgrade messages
