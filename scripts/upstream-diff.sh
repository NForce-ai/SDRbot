#!/bin/bash
#
# upstream-diff.sh - Analyze changes between upstream deepagents-cli releases
#
# Usage:
#   ./scripts/upstream-diff.sh                    # Compare 0.0.9 to latest
#   ./scripts/upstream-diff.sh 0.0.10             # Compare 0.0.9 to specific version
#   ./scripts/upstream-diff.sh 0.0.9 0.0.10       # Compare two specific versions
#
# Prerequisites:
#   git remote add upstream https://github.com/langchain-ai/deepagents.git
#   git fetch upstream --tags
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Our baseline version (what we originally forked from)
BASELINE="deepagents-cli==0.0.9"

# Parse arguments
if [ $# -eq 0 ]; then
    OLD_TAG="$BASELINE"
    # Get latest tag
    NEW_TAG=$(git tag -l 'deepagents-cli==*' | sort -V | tail -1)
elif [ $# -eq 1 ]; then
    OLD_TAG="$BASELINE"
    NEW_TAG="deepagents-cli==$1"
else
    OLD_TAG="deepagents-cli==$1"
    NEW_TAG="deepagents-cli==$2"
fi

UPSTREAM_PATH="libs/deepagents-cli/deepagents_cli"
OUTPUT_DIR="/tmp/upstream-diff-$$"

echo -e "${BOLD}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║           UPSTREAM DEEPAGENTS-CLI DIFF ANALYSIS                ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Comparing:${NC} ${OLD_TAG} → ${NEW_TAG}"
echo -e "${DIM}Upstream path: ${UPSTREAM_PATH}${NC}"
echo ""

# Verify tags exist
if ! git rev-parse "$OLD_TAG" >/dev/null 2>&1; then
    echo -e "${RED}Error: Tag '$OLD_TAG' not found. Run: git fetch upstream --tags${NC}"
    exit 1
fi

if ! git rev-parse "$NEW_TAG" >/dev/null 2>&1; then
    echo -e "${RED}Error: Tag '$NEW_TAG' not found. Run: git fetch upstream --tags${NC}"
    exit 1
fi

# Create temp directories
mkdir -p "$OUTPUT_DIR/old" "$OUTPUT_DIR/new"

# Extract both versions
echo -e "${DIM}Extracting versions...${NC}"
git archive "$OLD_TAG" "$UPSTREAM_PATH" 2>/dev/null | tar xf - -C "$OUTPUT_DIR/old" --strip-components=3
git archive "$NEW_TAG" "$UPSTREAM_PATH" 2>/dev/null | tar xf - -C "$OUTPUT_DIR/new" --strip-components=3

# Get file lists
OLD_FILES=$(cd "$OUTPUT_DIR/old" && find . -type f -name "*.py" -o -name "*.md" | sed 's|^\./||' | sort)
NEW_FILES=$(cd "$OUTPUT_DIR/new" && find . -type f -name "*.py" -o -name "*.md" | sed 's|^\./||' | sort)

# Find added, removed, and modified files
ADDED=$(comm -13 <(echo "$OLD_FILES") <(echo "$NEW_FILES"))
REMOVED=$(comm -23 <(echo "$OLD_FILES") <(echo "$NEW_FILES"))
COMMON=$(comm -12 <(echo "$OLD_FILES") <(echo "$NEW_FILES"))

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}                         SUMMARY                                 ${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"

# Added files
if [ -n "$ADDED" ]; then
    echo ""
    echo -e "${GREEN}▶ NEW FILES:${NC}"
    for f in $ADDED; do
        lines=$(wc -l < "$OUTPUT_DIR/new/$f")
        echo -e "  ${GREEN}+ $f${NC} ${DIM}($lines lines)${NC}"
    done
fi

# Removed files
if [ -n "$REMOVED" ]; then
    echo ""
    echo -e "${RED}▶ REMOVED FILES:${NC}"
    for f in $REMOVED; do
        echo -e "  ${RED}- $f${NC}"
    done
fi

# Modified files
echo ""
echo -e "${YELLOW}▶ MODIFIED FILES:${NC}"
MODIFIED_COUNT=0
for f in $COMMON; do
    if ! diff -q "$OUTPUT_DIR/old/$f" "$OUTPUT_DIR/new/$f" >/dev/null 2>&1; then
        old_lines=$(wc -l < "$OUTPUT_DIR/old/$f")
        new_lines=$(wc -l < "$OUTPUT_DIR/new/$f")
        diff_lines=$(diff "$OUTPUT_DIR/old/$f" "$OUTPUT_DIR/new/$f" | grep -c '^[<>]' || true)

        if [ "$new_lines" -gt "$old_lines" ]; then
            change="${GREEN}+$((new_lines - old_lines))${NC}"
        elif [ "$new_lines" -lt "$old_lines" ]; then
            change="${RED}$((new_lines - old_lines))${NC}"
        else
            change="${DIM}±0${NC}"
        fi

        echo -e "  ${YELLOW}~ $f${NC} ${DIM}($old_lines → $new_lines lines, $change, ~$diff_lines changes)${NC}"
        MODIFIED_COUNT=$((MODIFIED_COUNT + 1))
    fi
done

if [ "$MODIFIED_COUNT" -eq 0 ]; then
    echo -e "  ${DIM}(no modifications)${NC}"
fi

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}                      DETAILED CHANGES                           ${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"

# Detailed diff for each modified file
for f in $COMMON; do
    if ! diff -q "$OUTPUT_DIR/old/$f" "$OUTPUT_DIR/new/$f" >/dev/null 2>&1; then
        echo ""
        echo -e "${CYAN}┌──────────────────────────────────────────────────────────────┐${NC}"
        echo -e "${CYAN}│ ${BOLD}$f${NC}"
        echo -e "${CYAN}└──────────────────────────────────────────────────────────────┘${NC}"

        # Show unified diff with context
        diff -u "$OUTPUT_DIR/old/$f" "$OUTPUT_DIR/new/$f" 2>/dev/null | head -100 | while IFS= read -r line; do
            if [[ "$line" == ---* ]] || [[ "$line" == +++* ]]; then
                echo -e "${DIM}$line${NC}"
            elif [[ "$line" == @@* ]]; then
                echo -e "${CYAN}$line${NC}"
            elif [[ "$line" == +* ]]; then
                echo -e "${GREEN}$line${NC}"
            elif [[ "$line" == -* ]]; then
                echo -e "${RED}$line${NC}"
            else
                echo "$line"
            fi
        done

        # Check if diff was truncated
        total_diff_lines=$(diff -u "$OUTPUT_DIR/old/$f" "$OUTPUT_DIR/new/$f" 2>/dev/null | wc -l)
        if [ "$total_diff_lines" -gt 100 ]; then
            echo -e "${DIM}... ($((total_diff_lines - 100)) more lines, run with --full for complete diff)${NC}"
        fi
    fi
done

# Show new file contents (abbreviated)
for f in $ADDED; do
    echo ""
    echo -e "${CYAN}┌──────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}│ ${GREEN}[NEW]${NC} ${BOLD}$f${NC}"
    echo -e "${CYAN}└──────────────────────────────────────────────────────────────┘${NC}"
    head -50 "$OUTPUT_DIR/new/$f" | while IFS= read -r line; do
        echo -e "${GREEN}+ $line${NC}"
    done
    total_lines=$(wc -l < "$OUTPUT_DIR/new/$f")
    if [ "$total_lines" -gt 50 ]; then
        echo -e "${DIM}... ($((total_lines - 50)) more lines)${NC}"
    fi
done

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}                    PORTING CHECKLIST                            ${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Review each change and decide:"
echo -e "  ${GREEN}[PORT]${NC}    - Bug fix or improvement we need"
echo -e "  ${YELLOW}[ADAPT]${NC}   - Good idea, but needs modification for our architecture"
echo -e "  ${RED}[SKIP]${NC}    - Not relevant to SDRBot or conflicts with our design"
echo ""
echo -e "${DIM}Files extracted to: $OUTPUT_DIR${NC}"
echo -e "${DIM}Compare manually: diff -u $OUTPUT_DIR/old/<file> $OUTPUT_DIR/new/<file>${NC}"
echo -e "${DIM}Compare to local: diff -u $OUTPUT_DIR/new/<file> sdrbot_cli/<file>${NC}"
echo ""

# Cleanup reminder
echo -e "${DIM}To clean up: rm -rf $OUTPUT_DIR${NC}"
