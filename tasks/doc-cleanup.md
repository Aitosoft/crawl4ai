# Documentation Cleanup

**Status:** Done (2026-07-16, completed during the v0.9.2 upgrade)
**Move to done/ after the v0.9.2 deploy settles.**

## What was done (2026-07-16)

- Deleted: `azure-deployment/DEPLOYMENT_GUIDE.md`,
  `azure-deployment/V0.8.0_UPGRADE_SUMMARY.md`, `test-aitosoft/TESTING_RESULTS.md`,
  `test-aitosoft/README.md`, `test-aitosoft/TESTING_GUIDE.md`
- `CLAUDE.md`: modification inventory rewritten for v0.9.2 (also covers the
  original plan items — api.py listed, tasks/ listed, Tier 1 list current)
- `AITOSOFT_FILES.md`: fully rewritten for v0.9.2
- `TEST_SITES_REGISTRY.md`: Tier 1 corrected (caverna/accountor/solwers/jpond),
  retired sites (talgraf/vahtivuori/monidor) in explicit Retired section,
  magic references removed
- `TESTING.md`: fully rewritten (623 stale lines → lean current doc; magic
  configs and retired sites purged, v0.9.x behavior documented)
- `DEPLOYMENT_INFO.md`: updated as part of the v0.9.2 deploy

## Not done (deliberately)

- `azure-deployment/SIMPLE_AUTH_DEPLOY.md` + `TOKEN_ROTATION_GUIDE.md` infra
  refs — low priority; SIMPLE_AUTH_DEPLOY.md is now historical anyway (auth
  moved to upstream AuthGateMiddleware in v0.9.2). Revisit if token rotation
  is ever needed: verify against DEPLOYMENT_INFO.md first.
