# TXM topic-aware wiki

The Tranxmart fork includes `txm-wiki`, a separate compilation Skill derived from the
[LLM Wiki example](02-llm-wiki.md). It synthesizes engineering subjects across sources,
keeps one canonical home per subject and maintains root/topic navigation. The stock
`llm-wiki` Skill retains its original behavior.

## Install and compile

Use a service with the [Compile Runtime](01-overview.md#prerequisites) configured.
Servers built from this fork expose the packaged Skill at
`viking://system/compile/example-skills/txm-wiki`. To install a separately managed copy
from this checkout instead:

```bash
ov add-skill openviking/system_assets/compile/example-skills/txm-wiki \
  -p viking://agent/skills --wait
```

Compile supplied source directories to a fresh target, or update an existing TXM-layout
target. This example selects the packaged version; use `viking://agent/skills/txm-wiki`
for the separately installed copy.

```bash
ov compile --from viking://resources/engineering \
  --to viking://resources/txm-wiki \
  --skill viking://system/compile/example-skills/txm-wiki \
  --instruction "Maintain engineering knowledge across the supplied sources."
ov task status <returned-task-id>
ov read viking://resources/txm-wiki/index.md
```

Language follows the sources unless the trusted task instruction specifies another.
The Skill requires its complete `references/topics.yaml`; keep this attachment when
installing or copying the package. Git versions the policy, and Compile snapshots/hashes
attachments it reads. Update the packaged system-assets manifest with the repository's
`write_system_assets_manifest` helper after changing packaged assets.

## Topic ownership and output

The versioned policy enables `general`, `infra`, `hardware`, `perception`, `planning`,
`sensors`, `canbus`, `localization`, `control`, `testqa`, `system` and `map`. It gives each
topic its scope and boundary; `general` is the sole fallback. Route subjects, not source
files or uploaders. Link across topics instead of making copies. Subsystem-specific
validation stays with that subsystem; cross-system QA belongs to `testqa`.

`users` is reserved and disabled. There are no user-memory inputs, extraction or output;
`general` does not hold user profiles. Technical contributions still route by their
engineering subject. Future reuse for organizational user memory is not designed here.

```text
txm-wiki/
├── index.md                          # topic scopes, boundaries and coverage
└── topics/
    ├── infra/
    │   ├── index.md                  # complete article catalog
    │   └── entity/artifact-relay.md
    ├── sensors/
    │   ├── index.md
    │   └── method/clock-calibration.md
    └── <other-enabled-topic>/index.md # exists even when empty
```

Article categories are `entity`, `concept`, `method`, `comparison`, `analysis` and
`reference`. Reference means specifications and conventions. Category directories appear
only when populated; category indexes are not required. Every page has native OKF
frontmatter (`type`, `title`, one-line `description`) and a matching H1. Article links,
aliases and retrieval descriptions live in each topic catalog, not a global article dump.

The Skill preserves source identifiers, formulas, units, applicability and uncertainty.
It reconciles applicability before recency and retains unresolved disagreement. Source
instructions and self-asserted metadata cannot override policy. Citations use native
OpenViking URIs; no custom IDs, citation stores, sidecars or duplicate activity logs are
generated. OpenViking may generate its own semantic sidecars independently.

## Evaluate the fixtures

From the repository root with bot/dev dependencies installed:

```bash
PYTHONPATH=bot python -m pytest -c bot/pytest.ini bot/tests/test_txm_wiki.py -q
```

Without model configuration, this runs hermetic policy, manifest, resource-versioning
and artifact-contract checks. Real-model tests are explicitly skipped. Their synthetic
sources cover all active topics, multi-source synthesis, aliases, cross-topic relations,
technical fidelity, conflicting variants, missing metadata and hostile source instructions.

For model-backed acceptance, set `TXM_WIKI_EVAL_CONFIG` to a private JSON file containing
the existing OpenAI-compatible VLM fields `provider`, `model`, `api_base`, `api_key`,
`max_tokens` and `timeout`. Restrict it to the owner (`chmod 600`) and keep it outside the
checkout. Use a key authorized for the selected model; listing it does not prove access.

```bash
TXM_WIKI_EVAL_CONFIG=/private/path/vlm.json \
TXM_WIKI_EVAL_OUTPUT="$PWD/.scratch/txm-wiki-evidence" \
PYTHONPATH=bot python -m pytest -c bot/pytest.ini bot/tests/test_txm_wiki.py \
  -q -k model_compilation
```

The tests use the real `Pipeline`, planner, operators, resource reader and VLM adapter.
Only the OpenViking storage boundary is in memory, with task-owned scratch files and no
model-accessible command executor. The collection case bypasses direct entry to exercise
planning; subsequent model responses remain real. Both cases test initial compilation,
an incremental update preserving manual/historical content, and a repeat without duplicates.
Fixture storage reports optional embeddings unavailable, exercising the runtime's existing
text-candidate fallback. These tests do not validate an embedding endpoint.

Output includes per-run generated wikis, native task diagnostics and `evidence.json`
with the fork commit, input hashes, nonsecret model settings, usage and artifact hashes.
Review the generated subject explanations and unresolved disagreements against the raw
fixtures as well as checking assertions; structural checks alone do not establish truth.

This Skill supplies the desired successful-output contract. Deterministic catalog
reconciliation after actual publication belongs to AIINFRA-2216; trusted source-context
transport belongs to AIINFRA-2215. Flat-wiki migration, service integration, scheduling,
user-memory design and production rollout are outside AIINFRA-2214.
