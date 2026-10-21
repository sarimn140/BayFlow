## What and why
<!-- One paragraph. Link the spec rows / decisions implemented, e.g. "spec 08 T13–T15, D42, D43". -->

## Changes
-

## Tests
- Catalogue IDs covered: <!-- e.g. INV-02, INV-05, SM-12 -->
- [ ] `make lint` and `make test` pass locally (spec 07 Makefile)
- [ ] Negative paths covered (403 / 404 / 409 / 422 as applicable)

## Screens / API examples
<!-- Screenshot (mobile + desktop) for UI changes; request/response for API changes. -->

## Checklist
- [ ] Specs updated first if behaviour or a decision changed (decisions → spec 17; new names → "Proposed glossary additions")
- [ ] Names match spec 18 exactly
- [ ] No secrets or real credentials; any new env var is in `.env.example` with a one-line comment
- [ ] Migrations reviewed (upgrade + downgrade); `alembic check` clean
- [ ] API changed → `make gen-api` run and the regenerated `openapi.json` + `schema.d.ts` committed
- [ ] Seed still works and demo data still shows this feature
- [ ] AI assistance used? (yes/no, where): ______ — I have read, run and understood every line and can explain it in the judges' review
