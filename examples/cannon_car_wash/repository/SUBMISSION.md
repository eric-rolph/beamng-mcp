# Cannon Car Wash Repository submission

This directory contains operator-facing material for the BeamNG Repository form. Nothing here is
packed into `cannon_car_wash_ericrolph.zip`.

## Overview

Drive a Gavril D-Series through a detailed automated car wash on Gridmap V2. Entering the wash
starts five animated brushes and twelve inward-facing spray misters. Once the truck is fully
contained in the exit bay, the system holds it for a 3-2-1-GO countdown and launches it at
360 km/h toward a concrete crash target. The rigid 14,875 kg structure is also available in the
vehicle selector under Props.

## Installation and use

1. Subscribe through the Repository, or place the downloaded ZIP in the BeamNG user folder's
   `mods` directory.
2. Open Scenarios and select **Cannon Car Wash** to run the complete wash-and-launch trap.
3. Open the vehicle selector's Props category to place the rigid car-wash structure by itself.

## v1.3.0 notes

- Prepared the archive for official Repository review.
- Added the author-qualified `ericrolph_cannon_car_wash` runtime namespace.
- Removed README, local metadata, manifests, and handoff evidence from the upload.
- Moved gameplay Lua into BeamNG's scenario-owned load/unload lifecycle, eliminating the deprecated
  global modScript bootstrap and its console warning.
- Added a same-basename scenario preview and two source-side gallery images.
- Preserved and revalidated brush animation, twelve spray misters, full-containment launch,
  rigid JBeam behavior, crash telemetry, and clean Lua logs.

## Manual upload checklist

- Upload the stable `cannon_car_wash_ericrolph.zip` artifact; do not rename it on future updates.
- Use the dedicated 96x96 `repository/icon.jpg` as the resource icon.
- Upload both images under `repository/images` through the Repository image uploader.
- Paste the overview above; do not add a README to the ZIP.
- Confirm the submitting BeamNG account and author display name are correct.
- Confirm the archive was tested alone from `USER_FOLDER/mods` on BeamNG.drive 0.38.6.
- Confirm the uploaded file is exactly 1,863,665 bytes with SHA-256
  `9c479f49dfc7fe5db7442f75ff059ea51e1023bff631563fa115ed6dcaa3fa1b`.
- Review `PROVENANCE.md`, the automated distribution gates, and the latest live telemetry.
- Check the in-game console for new warnings or errors before submitting for moderator review.
