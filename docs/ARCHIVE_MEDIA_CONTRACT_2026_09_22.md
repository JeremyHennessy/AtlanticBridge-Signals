# Evidence archive HTTP media contract

The initial isolated retention run 35799586965 and pilot-proof run 35799586947 both failed while downloading an accepted Actions artifact with HTTP 415. Diagnostic artifact 10725431659 has independently verified SHA-256 d97e1bcb3d59b2788b0640d0c258fb81e9905d61ade3391a1a8f3074ebac610d and records the failed attempt; no production state was changed.

GitHub's artifact-download endpoint returns a signed redirect and documents Accept: application/vnd.github+json. Release-asset byte downloads use application/octet-stream. The new client incorrectly applied the latter to both endpoints. The repair changes only Accept selection: octet-stream on /releases/assets/, GitHub JSON elsewhere, including the draft privacy check. It does not change token scopes, redirect credential stripping, checksum/size validation, upload semantics or failure handling.

Official endpoint contract: https://docs.github.com/en/rest/actions/artifacts#download-an-artifact . A new regression checks all three endpoint shapes. All 17 archive unit tests pass locally; production archival still requires fresh exact-head real upload/download/private-access and checkpoint recovery proof, independent artifact review, and a successful production run after merge.
