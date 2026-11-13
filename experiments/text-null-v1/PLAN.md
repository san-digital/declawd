# Null calibration

This registered CPU study checks two published testing components and a simple corpus lower bound under declared synthetic nulls. It measures CountScan's all-interval count bound and the token-weighted e-BH rule used by BELL. It does not reproduce BELL's adaptive allocation or either paper's model experiments.

## Inputs

Use Python 3.11's standard library and the single fixed seed 20261113. Commit this plan, `study.py` and `test_study.py` before creating a hash registration. Commit the registration before generating any experiment pivots. The runner refuses an existing result. Reproduction recomputes the same registered draw and compares all outcomes.

Generate 100 independent documents of 64 pivots for each of three conditions: independent uniform nulls, one central 32-position marked segment with pivots U cubed, and a deliberately invalid null in which all 64 positions repeat one uniform draw. Draw fresh independent streams for each document. Record every document, pivot, interval count, block decision and false count, including zero detections and errors. The repeated condition deliberately violates conditional super-uniformity and supplies no validity claim.

## Components

For CountScan, use the fixed nonincreasing calibrator f(p)=1/(2 sqrt(p)), whose uniform expectation is one. Allocate alpha=0.05 uniformly over 64 starts. Each interval uses threshold log(64/alpha). Subtract the largest positive log contributions in turn, reporting the number of rejected count hypotheses as its lower bound. Check every interval against the known retained marked count and retain all violations. This implements the trimming construction in CountScan sections 3 and 4, without proxy-entropy optimisation.

For BELL's decision component, split each document into four fixed blocks of 16 positions, score all positions once and apply the token-weighted e-BH threshold N/(alpha times cumulative selected token mass), with alpha=0.05. Record rejected blocks, false selected tokens and token-weighted false-discovery proportions. This is a fixed-budget component check, without BELL's adaptive allocation. The error criterion differs from CountScan's simultaneous count coverage.

For prevalence sensitivity, independently generate Bernoulli detection indicators for a wholly null corpus at true positive rates 0.05 and 0.06. Use ten replicates at corpus sizes 2,000 and 100,000, with a separate calibration sample of 20,000 indicators in every replicate. A threshold-only lower bound is max(0,(observed rate minus audit margin minus null upper bound)/(1 minus null upper bound)). Use Hoeffding margins sqrt(log(2/0.05)/(2n)), with the second margin for the independently calibrated null. Compare the exact-null assumption q=0.05 with the calibrated null upper bound. The true origin share is zero in every corpus, so every positive lower bound is a false exclusion. This is a calibration illustration motivated by the prevalence paper, without its mechanism-specific power envelope or upper bound.

## Decisions

Report all-interval overclaims, detection counts, exact per-document false-discovery proportions and all prevalence lower bounds. Report observed Monte Carlo frequencies with their finite denominators. Do not tune thresholds, replace the seed or discard repeated-null failures after seeing results. Numerical or execution failures remain in the record and need a new registration before a changed run.

## Limits

Synthetic pivots supply no result for natural language, a human corpus, key reuse, a production provider or the existing r2 profile. A matching null model is an assumption. These component checks do not validate the papers' complete implementations, registrations or claimed model results. Existing experiments and site thresholds retain their original bytes.

## Sources

[CountScan v1](https://arxiv.org/abs/2611.07888v1), published 5 November 2026, [BELL v2](https://arxiv.org/abs/2611.02030v2), revised 3 November, and [Prevalence Bounds v1](https://arxiv.org/abs/2611.17035v1), published 12 November, were read on 13 November. This independent implementation copies no third-party code. The prevalence repository supplies no root licence in the captured revision, so its code is not incorporated.
