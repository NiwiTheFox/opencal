# VAGEDCSuite GPL source provenance

Source: https://github.com/skaldamramra/VAGEDCSuite
Revision: 9689a8527f55659fa0e51cede724f4c9fb57ace4
Project license: GNU GPL version 3, retained unchanged in LICENSE.
Copyright: VAGEDCSuite contributors; original sources retained unchanged.

OpenCal adapts the EDC15PTuner.DisableEGRMap strategy (8500 raw fresh-air request)
and checks its final little-endian output convention against
Tools.savedatatobinary / reverseEndian. OpenCal adds software/layout guards,
explicit EGR diagnostic selection, atomic previews, undo and exact-original
restoration. No executable code, proprietary map packs or brand assets from the
provided VAG EDC+ Suite binary are incorporated.

This source routine does not establish applicability to every ECU or prove
vehicle operation. The initial OpenCal profile is bounded to the independently
inspected standard FJ / SG 1376 layout. Private firmware and reference packs
are excluded from public distributions.
