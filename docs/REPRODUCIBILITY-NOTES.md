# Compare a study with the article

Check the comparison contract before interpreting a difference in success or cost. A modern run, a teaching demonstration and a published observation are different evidence sources.

- **Main study:** 16×16 empty maps, 20/40/60/80-agent rosters, four settings, FoV 5/7/9, initial tokens 5, standard commitment for the main comparisons. The original article used 100 scenarios and five stochastic repetitions; any subset must state its selection rule and independent units.
- **Appendix:** 32×32 maps with 0/10/20% obstacle density and 25 80-agent scenarios per map. The main study's path-length/generation assumptions are not imposed on the appendix merely because they appeared in an old Java branch.
- **Centralized budget:** the article reports 60 seconds per scenario. The software permits an explicit budget up to **600 seconds**. Record the chosen budget and label any 60-second sensitivity analysis; a 600-second success rate is not an exact same-budget reproduction.
- **Decentralized deadline:** 60 seconds per bilateral negotiation, distinct from a whole-episode or batch cap. An agreement does not prove an alternate path exists under every prior commitment.
- **Method identity:** native EECBS/CBSH2-RTC profiles carry binary/source identity. The simplified Python focal CBS under the legacy `EECBS` identifier is not substituted for an article baseline.
- **Cost:** state actions/ticks and the exact reference/cohort. Common-solved quality comparisons cannot use the success-rate denominator blindly; failed trajectories have no solved-path cost.
- **Uncertainty:** scenario/source-file dependence is retained across methods/settings. Historical aggregates without matched repeated observations support descriptive differences, not a fabricated historical significance test.

A deficit can reflect a bug, a method/setting difference, selection or stochastic effects. Lack of a failing invariant is not proof that the deficit is scientifically unavoidable. Keep unexplained differences unresolved until the evidence identifies their cause.

Next: follow [the full reproducibility contract](../REPRODUCIBILITY.md) and [experiment workflow](EXPERIMENTS.md).
