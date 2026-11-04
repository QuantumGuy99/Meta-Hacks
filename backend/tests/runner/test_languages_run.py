"""Java, C++ and C through LocalRunner on real problems (PLAN §10.3, §12): every hidden test, and the ways a
compiled run fails. Skipped where the compilers aren't installed (they are in the Modal image)."""

import shutil

import pytest

from crucible.coding.languages import starter
from crucible.coding.problems import ProblemBank
from crucible.coding.tests import request
from crucible.contracts.common import Language
from crucible.runner.local import LocalRunner

pytestmark = pytest.mark.skipif(
    not all(shutil.which(c) for c in ("javac", "java", "g++", "gcc")), reason="needs javac, g++ and gcc"
)

SOLUTIONS = {
    # A bool return (mirror-badge-codes, tunnel-log): printed as JSON true/false in every language.
    ("mirror-badge-codes", Language.JAVA): """\
class Solution {
    public boolean isMirrorCode(String code) {
        int l = 0, r = code.length() - 1;
        while (l < r) {
            if (code.charAt(l) == '-') l++;
            else if (code.charAt(r) == '-') r--;
            else if (Character.toLowerCase(code.charAt(l)) != Character.toLowerCase(code.charAt(r))) return false;
            else { l++; r--; }
        }
        return true;
    }
}
""",
    ("mirror-badge-codes", Language.CPP): """\
class Solution {
public:
    bool isMirrorCode(string& code) {
        int l = 0, r = (int) code.size() - 1;
        while (l < r) {
            if (code[l] == '-') l++;
            else if (code[r] == '-') r--;
            else if (tolower(code[l]) != tolower(code[r])) return false;
            else { l++; r--; }
        }
        return true;
    }
};
""",
    ("mirror-badge-codes", Language.C): """\
bool isMirrorCode(char* code) {
    int l = 0, r = (int) strlen(code) - 1;
    while (l < r) {
        if (code[l] == '-') l++;
        else if (code[r] == '-') r--;
        else if (tolower((unsigned char) code[l]) != tolower((unsigned char) code[r])) return false;
        else { l++; r--; }
    }
    return true;
}
""",
    ("battery-budget", Language.JAVA): """\
class Solution {
    public int longestWithinBudget(int[] usage, int budget) {
        int best = 0, total = 0, left = 0;
        for (int right = 0; right < usage.length; right++) {
            total += usage[right];
            while (total > budget) total -= usage[left++];
            best = Math.max(best, right - left + 1);
        }
        return best;
    }
}
""",
    ("room-bookings", Language.JAVA): """\
import java.util.*;

class Solution {
    public int[][] mergeBookings(int[][] bookings) {
        Arrays.sort(bookings, (x, y) -> x[0] != y[0] ? x[0] - y[0] : x[1] - y[1]);
        List<int[]> out = new ArrayList<>();
        for (int[] b : bookings) {
            if (!out.isEmpty() && b[0] <= out.get(out.size() - 1)[1]) {
                out.get(out.size() - 1)[1] = Math.max(out.get(out.size() - 1)[1], b[1]);
            } else out.add(new int[] {b[0], b[1]});
        }
        return out.toArray(new int[0][]);
    }
}
""",
    ("undo-editor", Language.JAVA): """\
import java.util.*;

class Solution {
    public String finalText(String[] commands) {
        Deque<String> pieces = new ArrayDeque<>();
        for (String c : commands) {
            if (c.equals("undo")) { if (!pieces.isEmpty()) pieces.removeLast(); }
            else pieces.addLast(c.substring(5));
        }
        return String.join("", pieces);
    }
}
""",
    ("merge-ticket-queues", Language.CPP): """\
class Solution {
public:
    vector<int> mergeQueues(vector<int>& a, vector<int>& b) {
        vector<int> out;
        merge(a.begin(), a.end(), b.begin(), b.end(), back_inserter(out));
        return out;
    }
};
""",
    ("delivery-grid", Language.CPP): """\
class Solution {
public:
    int shortestRoute(vector<string>& grid) {
        int R = grid.size(), C = grid[0].size();
        if (grid[0][0] == '#' || grid[R - 1][C - 1] == '#') return -1;
        vector<vector<int>> d(R, vector<int>(C, -1));
        queue<pair<int, int>> q;
        d[0][0] = 0; q.push({0, 0});
        int dr[] = {1, -1, 0, 0}, dc[] = {0, 0, 1, -1};
        while (!q.empty()) {
            auto [r, c] = q.front(); q.pop();
            if (r == R - 1 && c == C - 1) return d[r][c];
            for (int k = 0; k < 4; k++) {
                int nr = r + dr[k], nc = c + dc[k];
                if (nr >= 0 && nr < R && nc >= 0 && nc < C && grid[nr][nc] == '.' && d[nr][nc] < 0) {
                    d[nr][nc] = d[r][c] + 1; q.push({nr, nc});
                }
            }
        }
        return -1;
    }
};
""",
    ("undo-editor", Language.CPP): """\
class Solution {
public:
    string finalText(vector<string>& commands) {
        vector<string> pieces;
        for (auto& c : commands) {
            if (c == "undo") { if (!pieces.empty()) pieces.pop_back(); }
            else pieces.push_back(c.substr(5));
        }
        string out;
        for (auto& p : pieces) out += p;
        return out;
    }
};
""",
    ("battery-budget", Language.C): """\
int longestWithinBudget(int* usage, int usageSize, int budget) {
    int best = 0, total = 0, left = 0;
    for (int right = 0; right < usageSize; right++) {
        total += usage[right];
        while (total > budget) total -= usage[left++];
        if (right - left + 1 > best) best = right - left + 1;
    }
    return best;
}
""",
    ("room-bookings", Language.C): """\
static int cmp(const void* x, const void* y) {
    const int* a = *(const int**) x; const int* b = *(const int**) y;
    return a[0] != b[0] ? a[0] - b[0] : a[1] - b[1];
}

int** mergeBookings(int** bookings, int bookingsSize, int* bookingsColSize, int* returnSize,
                    int** returnColumnSizes) {
    qsort(bookings, bookingsSize, sizeof(int*), cmp);
    int** out = malloc(sizeof(int*) * (bookingsSize + 1));
    *returnColumnSizes = malloc(sizeof(int) * (bookingsSize + 1));
    int n = 0;
    for (int k = 0; k < bookingsSize; k++) {
        if (n && bookings[k][0] <= out[n - 1][1]) {
            if (bookings[k][1] > out[n - 1][1]) out[n - 1][1] = bookings[k][1];
        } else {
            out[n] = malloc(sizeof(int) * 2);
            out[n][0] = bookings[k][0]; out[n][1] = bookings[k][1];
            (*returnColumnSizes)[n++] = 2;
        }
    }
    *returnSize = n;
    return out;
}
""",
    ("undo-editor", Language.C): """\
char* finalText(char** commands, int commandsSize) {
    int* ends = malloc(sizeof(int) * (commandsSize + 1));
    char* text = malloc(1);
    int n = 0, len = 0, cap = 1;
    for (int k = 0; k < commandsSize; k++) {
        if (strcmp(commands[k], "undo") == 0) {
            if (n) len = --n ? ends[n - 1] : 0;
        } else {
            int add = strlen(commands[k]) - 5;
            while (len + add + 1 > cap) { cap *= 2; text = realloc(text, cap); }
            memcpy(text + len, commands[k] + 5, add);
            len += add;
            ends[n++] = len;
        }
    }
    text[len] = 0;
    return text;
}
""",
}


@pytest.fixture(scope="module")
def bank() -> ProblemBank:
    return ProblemBank.load()


async def submit(local_settings, bank: ProblemBank, slug: str, language: Language, code: str):
    spec = bank.get(slug)
    return await LocalRunner(local_settings).run_tests(
        "s", request(spec, "submit", code, t=0, language=language)
    )


@pytest.mark.parametrize(("slug", "language"), list(SOLUTIONS))
async def test_a_correct_solution_passes_every_hidden_test(local_settings, bank, slug, language) -> None:
    result = await submit(local_settings, bank, slug, language, SOLUTIONS[slug, language])
    assert result.compile_error is None, result.compile_error
    assert result.passed == result.total > 0, [
        (c.id, c.error, c.actual_repr) for c in result.cases if not c.passed
    ]


@pytest.mark.parametrize("language", [Language.JAVA, Language.CPP, Language.C])
async def test_the_untouched_starter_fails_without_breaking_the_run(local_settings, bank, language) -> None:
    code = starter(bank.get("battery-budget").function, language, "")
    result = await submit(local_settings, bank, "battery-budget", language, code)
    assert result.passed < result.total


async def test_a_compile_error_names_the_line_in_their_file(local_settings, bank) -> None:
    code = "class Solution {\n    public int longestWithinBudget(int[] usage, int budget) {\n        return x;\n    }\n}\n"
    result = await submit(local_settings, bank, "battery-budget", Language.JAVA, code)
    assert result.passed == 0 and result.cases == []
    assert "Solution.java:3" in result.compile_error and "/" not in result.compile_error.split(":")[0]


async def test_a_cpp_compile_error_points_at_their_file_not_our_driver(local_settings, bank) -> None:
    code = (
        "class Solution {\npublic:\n    int longestWithinBudget(vector<int>& u, int b) { return best; }\n};\n"
    )
    result = await submit(local_settings, bank, "battery-budget", Language.CPP, code)
    assert result.compile_error.startswith("solution.cpp:3:") and "main.cpp" not in result.compile_error


async def test_an_infinite_loop_times_out_that_case_and_the_rest_still_run(local_settings, bank) -> None:
    code = """\
int longestWithinBudget(int* usage, int usageSize, int budget) {
    if (usageSize == 6) for (;;) {}
    return 0;
}
"""
    result = await submit(local_settings, bank, "battery-budget", Language.C, code)
    looped = [c for c in result.cases if c.error and "timed out" in c.error]
    assert result.timed_out and looped
    assert len(result.cases) == result.total and any(c.error is None for c in result.cases)


async def test_a_crash_is_reported_on_its_case(local_settings, bank) -> None:
    code = """\
int longestWithinBudget(int* usage, int usageSize, int budget) {
    volatile int* nowhere = NULL;
    return *nowhere;
}
"""
    result = await submit(local_settings, bank, "battery-budget", Language.C, code)
    assert len(result.cases) == result.total and result.passed == 0
    assert any("Segmentation fault" in (c.error or "") or "crashed" in (c.error or "") for c in result.cases)


async def test_a_java_exception_names_its_line_and_printed_output_is_stdout(local_settings, bank) -> None:
    code = """\
class Solution {
    public int longestWithinBudget(int[] usage, int budget) {
        System.out.println("checking " + usage.length);
        return usage[usage.length];
    }
}
"""
    result = await submit(local_settings, bank, "battery-budget", Language.JAVA, code)
    assert result.passed == 0 and len(result.cases) == result.total
    assert "ArrayIndexOutOfBoundsException" in result.cases[0].error and "(line 4)" in result.cases[0].error
    assert "checking" in result.stdout and "crucible-result" not in result.stdout


async def test_the_hosts_jvm_options_never_reach_the_candidates_java(
    local_settings, bank, monkeypatch
) -> None:
    """With JAVA_TOOL_OPTIONS set, the JVM's banner used to come first and push javac's error out of the message."""
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Dhost.secret=proxy.internal")
    code = starter(bank.get("battery-budget").function, Language.JAVA, "")
    result = await submit(local_settings, bank, "battery-budget", Language.JAVA, code)
    assert result.compile_error is not None and "missing return statement" in result.compile_error
    assert "Picked up" not in result.compile_error and "proxy.internal" not in result.compile_error
