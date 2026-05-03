#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
DIST_DIR="${REPO_ROOT}/dist"
STAGE_DIR="${DIST_DIR}/mac_local_state_${STAMP}"
ARCHIVE_PATH="${DIST_DIR}/GenericAgent_dev_mac_local_state_${STAMP}.tar.gz"

mkdir -p "${DIST_DIR}"
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

copy_if_exists() {
  local rel="$1"
  local src="${REPO_ROOT}/${rel}"
  local dst="${STAGE_DIR}/${rel}"
  if [ -e "${src}" ]; then
    mkdir -p "$(dirname "${dst}")"
    rsync -a \
      --exclude '__pycache__/' \
      --exclude 'temp/' \
      --exclude '.DS_Store' \
      "${src}" "${dst}"
    echo "[include] ${rel}"
  else
    echo "[skip] ${rel} (not found)"
  fi
}

copy_if_exists "GenericAgent/mykey.py"
copy_if_exists "GenericAgent_LDY/mykey.py"
copy_if_exists "compare_lab/runs"
copy_if_exists "compare_lab/web/runs"

cat > "${STAGE_DIR}/README_BUNDLE.txt" <<EOF
This bundle contains local research state for GenericAgent_dev.

Included:
- GenericAgent/mykey.py (if present)
- GenericAgent_LDY/mykey.py (if present)
- compare_lab/runs/
- compare_lab/web/runs/

Excluded:
- temp/
- __pycache__/
- virtual environments
- git metadata

Apply this bundle on top of a fresh git clone on your Mac.
EOF

tar -czf "${ARCHIVE_PATH}" -C "${STAGE_DIR}" .
rm -rf "${STAGE_DIR}"

echo
echo "Created bundle:"
echo "  ${ARCHIVE_PATH}"
echo
echo "Suggested transfer:"
echo "  scp ${ARCHIVE_PATH} <mac_user>@<mac_host>:~/Downloads/"
