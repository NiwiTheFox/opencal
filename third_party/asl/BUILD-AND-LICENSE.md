# Bundled Macro Assembler AS

AS 1.42 Beta build 313, flamewing/asl-releases, source commit 592c5fa57b874266bfb625aedaa5197fcd09cec1, release snapshot-v1.4.2.20261014-run38518630251. Binaries copied unchanged from the official Windows x86_64 release. Source files grant GPL-2.0-only OR GPL-3.0-only; OpenCal selects GPL-3.0-only. Original COPYING (GPL2), per-file notices and GPL3 text are retained. The exact corresponding source tree, including CMake and include files, is provided in the adjacent source ZIP. No external download is needed to obtain that source.

Build: extract the source ZIP; install CMake >=3.19 and Visual Studio 2022 C++ tools on a build machine; run `cmake -S . -B build -A x64 -G "Visual Studio 17 2022"`, then `cmake --build build --config Release`. OpenCal users need no compiler. The release binaries were tested; a local MSVC rebuild is not claimed. See the source's .github/workflows/ci-windows-msvc.yml for upstream build settings.

Original authors and contributors are credited in the retained source. OpenCal runs only asw.exe and p2bin.exe through its bounded source-fragment wrapper. It does not bundle dasl.exe as a C166 decoder. Decoder code is independent of AS and has separate attribution.
