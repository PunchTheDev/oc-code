## Agent submission

**Handle:** <!-- your submission handle (dirname under agent/submissions/) -->
**SHA-256 (commit-reveal):** <!-- output of: gitminer hash agent/submissions/<handle>/agent.py -->
**Model:** <!-- exact model ID, must be in benchmark/harness/allowed_models.txt -->

## Approach
<!-- Describe your scaffolding: observe→plan→act loop, memory, tools, retries, reflection. -->

## Results (local eval)
<!-- Paste output from: gitminer eval agent/submissions/<handle>/agent.py --no-sandbox -->

## Checklist
- [ ] Agent inherits `BaseAgent` and implements `solve(problem: Problem) -> Patch`
- [ ] Model is listed in `benchmark/harness/allowed_models.txt`
- [ ] SHA-256 above matches `gitminer hash agent/submissions/<handle>/agent.py`
- [ ] Ran `gitminer eval` locally with no errors
