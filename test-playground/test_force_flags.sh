#!/bin/bash
#
# Test script for force flags behavior
#
# This script tests the three force flags:
# 1. --force (triggers both plexdata and metadata)
# 2. --force-plexdata (Plex verification only)
# 3. --force-metadata (video metadata only)
#
# Usage:
#     ./test_force_flags.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================"
echo "FORCE FLAGS BEHAVIOR TEST"
echo "========================================"
echo ""

# Test 1: Verify --force-plexdata flag is recognized
echo "Test 1: Verify --force-plexdata flag is recognized"
echo "----------------------------------------"
if my-plex --help | grep -q "force-plexdata"; then
    echo "✓ --force-plexdata flag found in help"
else
    echo "✗ --force-plexdata flag NOT found in help"
    exit 1
fi
echo ""

# Test 2: Verify --force-metadata flag is recognized
echo "Test 2: Verify --force-metadata flag is recognized"
echo "----------------------------------------"
if my-plex --help | grep -q "force-metadata"; then
    echo "✓ --force-metadata flag found in help"
else
    echo "✗ --force-metadata flag NOT found in help"
    exit 1
fi
echo ""

# Test 3: Verify --force flag mentions both
echo "Test 3: Verify --force flag documentation"
echo "----------------------------------------"
if my-plex --help | grep -A 2 "^  --force " | grep -q "BOTH"; then
    echo "✓ --force documentation mentions triggering BOTH flags"
else
    echo "✗ --force documentation does NOT mention BOTH flags"
    exit 1
fi
echo ""

# Test 4: Test flag parsing with dry-run check
echo "Test 4: Check FORCE_PLEXDATA variable with --force-plexdata"
echo "----------------------------------------"
# We'll use a small Python script to check if the variables are set correctly
PROJECT_DIR="$PROJECT_DIR" python3 << 'EOF'
import sys
import os

# Get project directory from environment variable
project_dir = os.environ.get('PROJECT_DIR', '/Users/MINE/data/src/,py/prj/my-plex')

# Check if we can parse the main script to verify variable usage
main_script = os.path.join(project_dir, '52')
with open(main_script, 'r') as f:
    content = f.read()

    # Check for FORCE_PLEXDATA variable
    if 'FORCE_PLEXDATA' in content:
        print("✓ FORCE_PLEXDATA variable found in main script")
    else:
        print("✗ FORCE_PLEXDATA variable NOT found")
        sys.exit(1)

    # Check for FORCE_METADATA variable
    if 'FORCE_METADATA' in content:
        print("✓ FORCE_METADATA variable found in main script")
    else:
        print("✗ FORCE_METADATA variable NOT found")
        sys.exit(1)

    # Check that old FORCE_REBUILD is gone
    if 'FORCE_REBUILD' in content:
        # Count occurrences - should only be in comments/strings
        import re
        # Look for actual variable usage (not in comments)
        rebuild_matches = re.findall(r'(?<!#).*FORCE_REBUILD', content)
        # Filter out comment lines
        rebuild_matches = [m for m in rebuild_matches if not m.strip().startswith('#')]
        if rebuild_matches:
            print(f"⚠ Warning: Found {len(rebuild_matches)} non-comment references to FORCE_REBUILD")
            for match in rebuild_matches[:3]:  # Show first 3
                print(f"  {match.strip()[:80]}")
        else:
            print("✓ FORCE_REBUILD only appears in comments (acceptable)")
    else:
        print("✓ FORCE_REBUILD completely removed")

    # Check for flag logic that triggers both
    if 'args.force or args.force_plexdata' in content:
        print("✓ --force triggers --force-plexdata logic found")
    else:
        print("✗ --force trigger logic for plexdata NOT found")
        sys.exit(1)

    if 'args.force or args.force_metadata' in content:
        print("✓ --force triggers --force-metadata logic found")
    else:
        print("✗ --force trigger logic for metadata NOT found")
        sys.exit(1)

print("\n✓ All variable checks passed")
EOF
echo ""

# Test 5: Verify documentation file exists
echo "Test 5: Verify FORCE_FLAGS_USAGE.md exists"
echo "----------------------------------------"
if [ -f "$SCRIPT_DIR/FORCE_FLAGS_USAGE.md" ]; then
    echo "✓ FORCE_FLAGS_USAGE.md found"

    # Check key sections exist
    if grep -q "Flag Hierarchy" "$SCRIPT_DIR/FORCE_FLAGS_USAGE.md"; then
        echo "✓ Contains 'Flag Hierarchy' section"
    else
        echo "✗ Missing 'Flag Hierarchy' section"
        exit 1
    fi

    if grep -q "Performance Comparison" "$SCRIPT_DIR/FORCE_FLAGS_USAGE.md"; then
        echo "✓ Contains 'Performance Comparison' section"
    else
        echo "✗ Missing 'Performance Comparison' section"
        exit 1
    fi

    if grep -q "Decision Tree" "$SCRIPT_DIR/FORCE_FLAGS_USAGE.md"; then
        echo "✓ Contains 'Decision Tree' section"
    else
        echo "✗ Missing 'Decision Tree' section"
        exit 1
    fi
else
    echo "✗ FORCE_FLAGS_USAGE.md NOT found"
    exit 1
fi
echo ""

# Test 6: Check actual runtime behavior (minimal test)
echo "Test 6: Runtime behavior check (info command)"
echo "----------------------------------------"
echo "Running: my-plex --info (to verify script still works)"
if my-plex --info > /dev/null 2>&1; then
    echo "✓ my-plex --info runs successfully"
else
    echo "✗ my-plex --info failed"
    exit 1
fi
echo ""

echo "========================================"
echo "✓ ALL TESTS PASSED"
echo "========================================"
echo ""
echo "Summary:"
echo "  ✓ --force-plexdata flag recognized"
echo "  ✓ --force-metadata flag recognized"
echo "  ✓ --force documentation correct"
echo "  ✓ Variable usage verified in code"
echo "  ✓ Documentation file complete"
echo "  ✓ Script runs without errors"
echo ""
echo "Next steps:"
echo "  - Test actual --update-cache with each flag"
echo "  - Verify FORCE_PLEXDATA triggers lib.refresh()"
echo "  - Verify FORCE_METADATA collects video metadata"
echo "  - Verify --force triggers both behaviors"
