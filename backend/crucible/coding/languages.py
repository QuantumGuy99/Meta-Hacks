"""Java, C++ and C for coding problems (PLAN §10.3): starter code, and the program the runner builds.

Problems are written once, in Python types. For the other languages this module turns the `FunctionSig` into a
LeetCode-style signature (camelCase names; C passes sizes alongside arrays) and a driver that reads every case
from stdin as whitespace-separated integers, calls the candidate's function and prints the result as JSON after
`RESULT_MARK`, so the harness compares it exactly like a Python result. Strings travel as character codes, so
no language has to parse quotes or spaces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from crucible.contracts.coding import FunctionSig
from crucible.contracts.common import Language
from crucible.runner.base import Program

RESULT_MARK = "\x1ecrucible-result\x1e"  # the harness keeps every other stdout line as the candidate's output
SUPPORTED_TYPES = frozenset({"int", "str", "list[int]", "list[str]", "list[list[int]]"})


class UnsupportedSignature(Exception):
    """The problem uses a type this module can't translate; it can only be solved in Python."""


def supports(sig: FunctionSig) -> bool:
    return all(t in SUPPORTED_TYPES for t in [*(p.type for p in sig.params), sig.returns])


def starter(sig: FunctionSig, language: Language, python_starter: str) -> str:
    """The editor's starting code: the problem's own for Python, a generated empty function otherwise."""
    if language == Language.PYTHON:
        return python_starter
    _check(sig)
    return _STARTERS[language](sig)


def signature(sig: FunctionSig, language: Language) -> str:
    """The function's header as the candidate sees it in their language."""
    if language == Language.PYTHON or not supports(sig):
        params = ", ".join(f"{p.name}: {p.type}" for p in sig.params)
        return f"def {sig.name}({params}) -> {sig.returns}"
    if language == Language.JAVA:
        return f"{_JAVA_TYPES[sig.returns]} {camel(sig.name)}({_java_params(sig)})"
    if language == Language.CPP:
        return f"{_CPP_TYPES[sig.returns]} {camel(sig.name)}({_cpp_params(sig)})"
    return f"{_C_RETURNS[sig.returns]} {camel(sig.name)}({_c_params(sig)})"


def statement(md: str, sig: FunctionSig, language: Language) -> str:
    """The problem statement with the function's and parameters' names as the language spells them."""
    if language == Language.PYTHON or not supports(sig):
        return md
    for name in {sig.name, *(p.name for p in sig.params)}:
        if "_" in name:
            md = re.sub(rf"\b{re.escape(name)}\b", camel(name), md)
    return md


def program(sig: FunctionSig, language: Language, code: str, cases_args: list[list]) -> Program:
    """The candidate's code plus our driver, how to build and run them, and each case's stdin."""
    _check(sig)
    build = _BUILDS[language]
    return Program(
        files={build.solution_file: code, build.main_file: _DRIVERS[language](sig)},
        compile=build.compile,
        run=build.run,
        inputs=[case_input(sig, args) for args in cases_args],
    )


def case_input(sig: FunctionSig, args: list) -> str:
    tokens: list[int] = []
    for param, value in zip(sig.params, args, strict=True):
        _encode(param.type, value, tokens)
    return " ".join(map(str, tokens)) + "\n"


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


# --- building and running -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Build:
    solution_file: str
    main_file: str
    compile: list[list[str]]
    run: list[str]


_BUILDS: dict[Language, _Build] = {
    Language.JAVA: _Build(
        "Solution.java",
        "Main.java",
        [["javac", "-encoding", "UTF-8", "-nowarn", "Main.java", "Solution.java"]],
        # A deep stack for recursive DFS; serial GC and C1 only, because start-up dominates these tiny runs.
        ["java", "-Xss64m", "-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", "-cp", ".", "Main"],
    ),
    Language.CPP: _Build(
        "solution.cpp", "main.cpp", [["g++", "-std=c++17", "-O2", "-o", "prog", "main.cpp"]], ["./prog"]
    ),
    Language.C: _Build(
        "solution.c", "main.c", [["gcc", "-std=c11", "-O2", "-o", "prog", "main.c", "-lm"]], ["./prog"]
    ),
}


def _check(sig: FunctionSig) -> None:
    if not supports(sig):
        raise UnsupportedSignature(f"{sig.name} uses a type only Python supports")


def _encode(type_: str, value: object, tokens: list[int]) -> None:
    if type_ == "int":
        tokens.append(int(value))
    elif type_ == "str":
        text = str(value)
        tokens.extend([len(text), *map(ord, text)])
    else:
        inner = type_.removeprefix("list[").removesuffix("]")
        items = list(value)
        tokens.append(len(items))
        for item in items:
            _encode(inner, item, tokens)


# --- starters -----------------------------------------------------------------------------------------------

_JAVA_TYPES = {"int": "int", "str": "String", "list[int]": "int[]", "list[str]": "String[]",
               "list[list[int]]": "int[][]"}  # fmt: skip
_CPP_TYPES = {"int": "int", "str": "string", "list[int]": "vector<int>", "list[str]": "vector<string>",
              "list[list[int]]": "vector<vector<int>>"}  # fmt: skip


def _java_params(sig: FunctionSig) -> str:
    return ", ".join(f"{_JAVA_TYPES[p.type]} {camel(p.name)}" for p in sig.params)


def _cpp_params(sig: FunctionSig) -> str:
    return ", ".join(
        f"{_CPP_TYPES[p.type]}{'' if p.type == 'int' else '&'} {camel(p.name)}" for p in sig.params
    )


def _c_params(sig: FunctionSig) -> str:
    """LeetCode's C convention: sizes after each array, result sizes as out-parameters."""
    out: list[str] = []
    for p in sig.params:
        n = camel(p.name)
        out += {
            "int": [f"int {n}"],
            "str": [f"char* {n}"],
            "list[int]": [f"int* {n}", f"int {n}Size"],
            "list[str]": [f"char** {n}", f"int {n}Size"],
            "list[list[int]]": [f"int** {n}", f"int {n}Size", f"int* {n}ColSize"],
        }[p.type]
    out += {
        "list[int]": ["int* returnSize"],
        "list[list[int]]": ["int* returnSize", "int** returnColumnSizes"],
    }.get(sig.returns, [])
    return ", ".join(out)


_C_RETURNS = {"int": "int", "str": "char*", "list[int]": "int*", "list[list[int]]": "int**"}
_C_NOTES = {
    "str": "/**\n * Note: the returned string must be malloced, assume the caller calls free().\n */\n",
    "list[int]": "/**\n * Note: the returned array must be malloced, assume the caller calls free().\n */\n",
    "list[list[int]]": (
        "/**\n * Return an array of arrays of size *returnSize.\n"
        " * The sizes of the arrays are returned as *returnColumnSizes array.\n"
        " * Note: both returned array and *columnSizes array must be malloced, assume caller calls free().\n */\n"
    ),
}


def _java_starter(sig: FunctionSig) -> str:
    head = f"public {_JAVA_TYPES[sig.returns]} {camel(sig.name)}({_java_params(sig)})"
    return f"import java.util.*;\n\nclass Solution {{\n    {head} {{\n        \n    }}\n}}\n"


def _cpp_starter(sig: FunctionSig) -> str:
    head = f"{_CPP_TYPES[sig.returns]} {camel(sig.name)}({_cpp_params(sig)})"
    return f"class Solution {{\npublic:\n    {head} {{\n        \n    }}\n}};\n"


def _c_starter(sig: FunctionSig) -> str:
    head = f"{_C_RETURNS[sig.returns]} {camel(sig.name)}({_c_params(sig)})"
    return f"{_C_NOTES.get(sig.returns, '')}{head} {{\n    \n}}\n"


_STARTERS = {Language.JAVA: _java_starter, Language.CPP: _cpp_starter, Language.C: _c_starter}


# --- drivers ------------------------------------------------------------------------------------------------
# Each reads a case count, then per case the arguments, calls the function (timed), and prints
# MARK <ms> <json> or MARK <ms> !<error>. Output is flushed per case so the harness can time each one.

_MARK = '"' + RESULT_MARK.replace("\x1e", "\\036") + '"'  # octal escapes: C rejects \\u001e


def _java_driver(sig: FunctionSig) -> str:
    reads = "\n".join(
        f"            {_JAVA_TYPES[p.type]} a{i} = {_JAVA_READ[p.type]};" for i, p in enumerate(sig.params)
    )
    args = ", ".join(f"a{i}" for i in range(len(sig.params)))
    return (
        _JAVA_DRIVER.replace("@READS@", reads)
        .replace("@CALL@", f"{_JAVA_TYPES[sig.returns]} r = new Solution().{camel(sig.name)}({args});")
        .replace("@MARK@", _MARK)
    )


_JAVA_READ = {
    "int": "in.i()",
    "str": "in.s()",
    "list[int]": "in.ints()",
    "list[str]": "in.strs()",
    "list[list[int]]": "in.grid()",
}

_JAVA_DRIVER = """import java.io.*;

public class Main {
    static final class In {
        private final DataInputStream d = new DataInputStream(new BufferedInputStream(System.in, 1 << 16));
        int i() throws IOException {
            int c = d.read();
            while (c == ' ' || c == '\\n') c = d.read();
            boolean neg = c == '-';
            if (neg) c = d.read();
            int v = 0;
            while (c >= '0' && c <= '9') { v = v * 10 + (c - '0'); c = d.read(); }
            return neg ? -v : v;
        }
        String s() throws IOException {
            int n = i();
            StringBuilder b = new StringBuilder(n);
            for (int k = 0; k < n; k++) b.append((char) i());
            return b.toString();
        }
        int[] ints() throws IOException { int[] a = new int[i()]; for (int k = 0; k < a.length; k++) a[k] = i(); return a; }
        String[] strs() throws IOException { String[] a = new String[i()]; for (int k = 0; k < a.length; k++) a[k] = s(); return a; }
        int[][] grid() throws IOException { int[][] a = new int[i()][]; for (int k = 0; k < a.length; k++) a[k] = ints(); return a; }
    }

    static String json(Object v) {
        if (v == null) return "null";
        if (v instanceof Integer) return v.toString();
        if (v instanceof String) {
            StringBuilder b = new StringBuilder("\\"");
            for (char c : ((String) v).toCharArray()) {
                if (c == '"' || c == '\\\\') b.append('\\\\').append(c);
                else if (c < 0x20) b.append(String.format("\\\\u%04x", (int) c));
                else b.append(c);
            }
            return b.append('"').toString();
        }
        StringBuilder b = new StringBuilder("[");
        int n = java.lang.reflect.Array.getLength(v);
        for (int k = 0; k < n; k++) b.append(k > 0 ? "," : "").append(json(java.lang.reflect.Array.get(v, k)));
        return b.append(']').toString();
    }

    public static void main(String[] argv) throws IOException {
        In in = new In();
        PrintStream out = System.out;
        int cases = in.i();
        for (int t = 0; t < cases; t++) {
@READS@
            long t0 = System.nanoTime();
            String line;
            try {
                @CALL@
                line = json(r);
            } catch (StackOverflowError e) {
                line = "!StackOverflowError: recursion too deep";
            } catch (Throwable e) {
                StackTraceElement at = null;
                for (StackTraceElement f : e.getStackTrace()) if ("Solution.java".equals(f.getFileName())) { at = f; break; }
                line = "!" + e.getClass().getSimpleName() + (e.getMessage() == null ? "" : ": " + e.getMessage())
                    + (at == null ? "" : " (line " + at.getLineNumber() + ")");
            }
            long ms = (System.nanoTime() - t0) / 1_000_000;
            out.print("\\n" + @MARK@ + ms + " " + line.replace('\\n', ' ') + "\\n");
            out.flush();
        }
    }
}
"""


def _cpp_driver(sig: FunctionSig) -> str:
    reads = "\n".join(
        f"        {_CPP_TYPES[p.type]} a{i} = {_CPP_READ[p.type]}();" for i, p in enumerate(sig.params)
    )
    args = ", ".join(f"a{i}" for i in range(len(sig.params)))
    call = f"auto r = Solution().{camel(sig.name)}({args});"
    return _CPP_DRIVER.replace("@READS@", reads).replace("@CALL@", call).replace("@MARK@", _MARK)


_CPP_READ = {"int": "ri", "str": "rs", "list[int]": "rints", "list[str]": "rstrs", "list[list[int]]": "rgrid"}

_CPP_DRIVER = """#include <algorithm>
#include <array>
#include <bitset>
#include <climits>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <exception>
#include <functional>
#include <iostream>
#include <list>
#include <map>
#include <numeric>
#include <queue>
#include <set>
#include <sstream>
#include <stack>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
#include <chrono>
using namespace std;

#include "solution.cpp"

static int ri() { int v = 0; if (scanf("%d", &v) != 1) exit(0); return v; }
static string rs() { int n = ri(); string s; s.reserve(n); for (int k = 0; k < n; k++) s += (char) ri(); return s; }
static vector<int> rints() { vector<int> a(ri()); for (auto& x : a) x = ri(); return a; }
static vector<string> rstrs() { vector<string> a(ri()); for (auto& x : a) x = rs(); return a; }
static vector<vector<int>> rgrid() { vector<vector<int>> a(ri()); for (auto& x : a) x = rints(); return a; }

static string json(int v) { return to_string(v); }
static string json(const string& v) {
    string b = "\\"";
    for (unsigned char c : v) {
        if (c == '"' || c == '\\\\') { b += '\\\\'; b += (char) c; }
        else if (c < 0x20) { char u[8]; snprintf(u, sizeof u, "\\\\u%04x", c); b += u; }
        else b += (char) c;
    }
    return b + "\\"";
}
template <class T> static string json(const vector<T>& v) {
    string b = "[";
    for (size_t k = 0; k < v.size(); k++) { if (k) b += ","; b += json(v[k]); }
    return b + "]";
}

int main() {
    int cases = ri();
    for (int t = 0; t < cases; t++) {
@READS@
        auto t0 = chrono::steady_clock::now();
        string line;
        try {
            @CALL@
            line = json(r);
        } catch (const exception& e) {
            line = string("!exception: ") + e.what();
        } catch (...) {
            line = "!unknown exception";
        }
        long long ms = chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now() - t0).count();
        for (auto& c : line) if (c == '\\n') c = ' ';
        fflush(stdout);
        cout << "\\n" << @MARK@ << ms << " " << line << "\\n" << flush;
    }
    return 0;
}
"""


def _c_driver(sig: FunctionSig) -> str:
    reads, args = [], []
    for i, p in enumerate(sig.params):
        if p.type == "int":
            reads.append(f"        int a{i} = ri();")
            args.append(f"a{i}")
        elif p.type == "str":
            reads.append(f"        char* a{i} = rs();")
            args.append(f"a{i}")
        elif p.type == "list[int]":
            reads.append(f"        int n{i}; int* a{i} = rints(&n{i});")
            args += [f"a{i}", f"n{i}"]
        elif p.type == "list[str]":
            reads.append(f"        int n{i}; char** a{i} = rstrs(&n{i});")
            args += [f"a{i}", f"n{i}"]
        else:
            reads.append(f"        int n{i}; int* c{i}; int** a{i} = rgrid(&n{i}, &c{i});")
            args += [f"a{i}", f"n{i}", f"c{i}"]
    call, emit = {
        "int": ("int r = {f}({a});", 'printf("%d", r);'),
        "str": ("char* r = {f}({a});", "pstr(r);"),
        "list[int]": ("int rn = 0; int* r = {f}({a}, &rn);", "pints(r, rn);"),
        "list[list[int]]": (
            "int rn = 0; int* rc = NULL; int** r = {f}({a}, &rn, &rc);",
            "putchar('['); for (int k = 0; k < rn; k++) { if (k) putchar(','); pints(r[k], rc ? rc[k] : 0); } "
            "putchar(']');",
        ),
    }[sig.returns]
    call = call.replace("{f}", camel(sig.name)).replace("{a}", ", ".join(args))
    return (
        _C_DRIVER.replace("@READS@", "\n".join(reads))
        .replace("@CALL@", call)
        .replace("@EMIT@", emit)
        .replace("@MARK@", _MARK)
    )


_C_DRIVER = """#include <ctype.h>
#include <limits.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "solution.c"

static int ri(void) { int v = 0; if (scanf("%d", &v) != 1) exit(0); return v; }
static char* rs(void) { int n = ri(); char* s = malloc(n + 1); for (int k = 0; k < n; k++) s[k] = (char) ri(); s[n] = 0; return s; }
static int* rints(int* n) { *n = ri(); int* a = malloc(sizeof(int) * (*n + 1)); for (int k = 0; k < *n; k++) a[k] = ri(); return a; }
static char** rstrs(int* n) { *n = ri(); char** a = malloc(sizeof(char*) * (*n + 1)); for (int k = 0; k < *n; k++) a[k] = rs(); return a; }
static int** rgrid(int* n, int** cols) {
    *n = ri(); int** a = malloc(sizeof(int*) * (*n + 1)); *cols = malloc(sizeof(int) * (*n + 1));
    for (int k = 0; k < *n; k++) a[k] = rints(&(*cols)[k]);
    return a;
}
static void pints(const int* a, int n) { putchar('['); for (int k = 0; k < n; k++) printf(k ? ",%d" : "%d", a[k]); putchar(']'); }
static void pstr(const char* s) {
    if (!s) { printf("null"); return; }
    putchar('"');
    for (const unsigned char* c = (const unsigned char*) s; *c; c++) {
        if (*c == '"' || *c == '\\\\') { putchar('\\\\'); putchar(*c); }
        else if (*c < 0x20) printf("\\\\u%04x", *c);
        else putchar(*c);
    }
    putchar('"');
}

int main(void) {
    int cases = ri();
    for (int t = 0; t < cases; t++) {
@READS@
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        @CALL@
        clock_gettime(CLOCK_MONOTONIC, &t1);
        long ms = (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000;
        printf("\\n%s%ld ", @MARK@, ms);
        @EMIT@
        putchar('\\n');
        fflush(stdout);
    }
    return 0;
}
"""

_DRIVERS = {Language.JAVA: _java_driver, Language.CPP: _cpp_driver, Language.C: _c_driver}
