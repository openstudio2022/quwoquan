# Travel Homepage Family

This reusable family produces one entity homepage per selected target. It has
no province, date, entity, batch, or execution instance values.

Use the repository `content-production` Skill as the only workflow guide. The
AI prepares a confirmed carrier-demand JSON whose `familyRef` is
`content/travel/homepage/homepage` and an immutable candidate-bindings JSON,
then initializes the work package with:

```bash
python3 quwoquan_data/scripts/cli.py task init \
  --carrier-demand <carrier-demand.json> \
  --candidate-bindings <immutable-candidate-bindings.json>
```

For each stage in the Skill's fixed order, submit the exact input refs with
`task stage-open`, write and self-check the business artifacts required by the
stage contract, then submit the result refs, typed issues, verdict, and real
verifier facts with `task stage-close`.

The same `executionId` may only replay byte-identical initialization inputs. A
blocked attempt starts a new `executionId`; its carrier demand sets `retryOf`
to the earlier execution. Credentials remain external inputs and must never be
written to commands, manifests, receipts, or artifacts.
