# Frictional heating in a robot gearbox

Predict the next minute of lubricant-temperature change from measured friction power and thermal boundaries. A thermal resistance network competes with a speed-dependent mixing hypothesis; no future control measurements are inputs.

## Scientific contract

Source identification runs train except 1.4137 rad/s dev; every source validation run is test. Nonoverlapping 60-second windows; instantaneous start-state inputs only. Single robot joint.

- Lumped thermal balance with measured instantaneous torque and speed
- Housing, environment and friction power are held locally constant over 60 seconds; later controls are never supplied
- Capacity and conductances are effective quantities; one joint, no independent-machine validation
- Convection proxy, not direct measurement of lubricant circulation

Source: https://doi.org/10.18419/DARUS-5015

Terms: CC BY 4.0

The pack-level builder reconstructs this version. Native source hashes and row lineage are recorded. Test targets remain in the separate evaluator vault. Known equation families are disclosed priors.
