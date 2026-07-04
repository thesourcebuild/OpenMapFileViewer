# OpenMapFileAnalyzer

A standalone Python utility for firmware memory analysis. It parses linker map files from major toolchains—including GCC/Clang, IAR, and Keil—and generates a comprehensive, single-file HTML report detailing memory regions, section composition, and symbol statistics.

## Table of Contents

- [OpenMapFileAnalyzer](#openmapfileanalyzer)
  - [Table of Contents](#table-of-contents)
  - [Report sections](#report-sections)
  - [Screenshots](#screenshots)
  - [Notes](#notes)
  - [Project setup](#project-setup)
  - [Usage](#usage)
    - [Using the sample files](#using-the-sample-files)
  - [Standalone Executable](#standalone-executable)
  - [Contributions](#contributions)
  - [License](#license)
  - [Author](#author)

## Report sections

The HTML report keeps the full dashboard layout:

- Overview cards: ROM image, RAM use, Code, RO data, RW data, ZI/BSS, Debug/other, Objects
- Boot/non-volatile capacity and runtime RAM capacity
- Memory regions table
- ROM by category chart
- RAM by category chart
- Category composition chart
- Module analysis tabs: Top ROM, Top Code, Top RAM, Libraries
- Largest code modules chart
- Section breakdown
- Archive/library breakdown
- Source-file estimate
- Largest symbols/functions when symbol-size data is present
- **Linker script info** — when a linker script is supplied (`--linker-file`), shows parsed memory regions, output sections, input section placements, heap/stack sizes, and the raw linker source in a tabbed viewer

## Screenshots

<table>
  <tr>
    <td align="center"><img src="images/Flash_ROM_capacity.png" alt="ROM capacity" width="400"><br><em>ROM / Boot capacity</em></td>
    <td align="center"><img src="images/RAM_capacity.png" alt="RAM capacity" width="400"><br><em>RAM capacity</em></td>
  </tr>
  <tr>
    <td align="center"><img src="images/ROM_by_category.png" alt="ROM by category" width="400"><br><em>ROM by category</em></td>
    <td align="center"><img src="images/RAM_by_category.png" alt="RAM by category" width="400"><br><em>RAM by category</em></td>
  </tr>
  <tr>
    <td align="center"><img src="images/Category_composition.png" alt="Category composition" width="400"><br><em>Category composition</em></td>
    <td align="center"><img src="images/Physical_address_space_map.png" alt="Address space map" width="400"><br><em>Physical address space map</em></td>
  </tr>
  <tr>
    <td align="center"><img src="images/ROM_vs_RAM_bubble_chart.png" alt="ROM vs RAM bubble chart" width="400"><br><em>ROM vs RAM bubble chart</em></td>
    <td align="center"><img src="images/Memory_treemap.png" alt="Memory treemap" width="400"><br><em>Memory treemap</em></td>
  </tr>
  <tr>
    <td align="center"><img src="images/Linker_section_breakdown.png" alt="Linker section breakdown" width="400"><br><em>Linker section breakdown</em></td>
    <td align="center"><img src="images/Largest_code_modules.png" alt="Largest code modules" width="400"><br><em>Largest code modules</em></td>
  </tr>
</table>

## Notes

Map files are not standardized. The parser uses best-effort format profiles and heuristics. Verify critical values against the linker output when introducing a new toolchain or custom linker script.

When the linker map does not expose the capacity you want to use for the dashboard, pass it explicitly with `--rom-capacity` and `--ram-capacity`. Values accept raw bytes, hex, or `KiB`/`MiB`/`GiB` style suffixes.

## Project setup

It is recommended to run the project inside a virtual environment:

```bash
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Install in editable mode
pip install -e .
```

## Usage

After installing with `pip install -e .`, run the analyzer as:

```bash
openmapfileanalyzer firmware.map -o firmware_report.html
openmapfileanalyzer firmware.map --linker-file lscript.ld
openmapfileanalyzer firmware.elf -o firmware_report.html

openmapfileanalyzer firmware.map --markdown
openmapfileanalyzer firmware.map --json firmware_report.json
openmapfileanalyzer firmware.map --csv

openmapfileanalyzer firmware.map --rom-capacity 2MiB --ram-capacity 512KiB
openmapfileanalyzer firmware.map --rom-capacity 0x200000 --ram-capacity 0x80000
```

Or run directly from source:

```bash
python src/openmapfileanalyzer.py firmware.map -o firmware_report.html
```

Parser profile selection is optional:

```bash
openmapfileanalyzer firmware.map --map-format auto
openmapfileanalyzer firmware.map --map-format gnu
openmapfileanalyzer firmware.map --map-format keil
openmapfileanalyzer firmware.map --map-format arm
openmapfileanalyzer firmware.map --map-format iar
openmapfileanalyzer firmware.map --map-format ti
openmapfileanalyzer firmware.map --map-format msvc
openmapfileanalyzer firmware.map --map-format generic
```

**Binary ELF Files**: You can pass binary ELF files (`.elf`, `.axf`, `.o`) directly instead of text map files. The analyzer leverages `pyelftools` to parse the `.symtab` section and extract `STT_FILE`, `STT_FUNC`, and `STT_OBJECT` symbol sizes natively without relying on map text layout.

**Linker Scripts**: When you pass `--linker-file`, the analyzer reads memory regions from the linker file instead of relying only on the map output. Supported linker-file extensions are:

- `.ld` for GNU ld / GCC / Clang linker scripts (e.g. `lscript.ld`)
- `.sct` for Keil scatter files
- `.icf` for IAR linker configuration files

**Stack Usage**: When you pass `--su-dir`, the tool will recursively search for `.su` and `.ci` files in that directory to calculate per-function static stack usage and estimated max call-depth.

When you pass `--csv`, the tool writes a combined CSV export (replacing the input file's extension with `.csv`) with both the section breakdown and the module breakdown.

### Using the sample files

The `samples/` directory contains pre-generated linker map files for various toolchains. You can use them to explore the report without your own firmware:

| Toolchain | Target | Command |
|-----------|--------|---------|
| Keil | STM32F103RB | `openmapfileanalyzer "samples/keil/openlibcli_stm32f103rbtx.map" --linker-file "samples/keil/openlibcli_stm32f103rbtx.sct"` |
| STM32CubeIDE | STM32F103RB | `openmapfileanalyzer "samples/gcc/cubeide/openlibcli_stm32f103rbtx.map" --linker-file "samples/gcc/cubeide/STM32F103RBTX_FLASH.ld"` |
| IAR | STM32F103RB | `openmapfileanalyzer "samples/iar/openlibcli_stm32f103rbtx.map" --linker-file "samples/iar/stm32f103xb_flash.icf"` |
| ESP32 (IDF) | ESP32 | `openmapfileanalyzer "samples/gcc/esp32/openlibcli_esp32.map"` |
| Pico SDK | RP2350 | `openmapfileanalyzer "samples/gcc/pico/openlibcli_rp2350.map"` |

Sample chip configuration YAML files are also available in `samples/chip-configs/`:

```
openmapfileanalyzer <map_file> --chip-config samples/chip-configs/stm32f103.yaml
openmapfileanalyzer <map_file> --chip-config samples/chip-configs/esp32.yaml
openmapfileanalyzer <map_file> --chip-config samples/chip-configs/zynq.yaml
```

Chip config samples demonstrate three supported YAML schemas (see [Docs/chip_config_yaml.md](Docs/chip_config_yaml.md) for details).

## Standalone Executable

If you wish to distribute the analyzer as a standalone executable without relying on a Python environment, you can use PyInstaller:

1. You can run the setup scripts from the `scripts/installer` directory to automatically install dependencies and compile the `.exe`:
   - Windows: `scripts\installer\create_setup.bat`
   - Linux/macOS: `./scripts/installer/create_setup.sh`

2. Alternatively, if you want to run it manually:

   ```bash
   pip install .[build]
   pyinstaller scripts/installer/openmapfileanalyzer.spec --distpath out/pyinstaller/dist --workpath out/pyinstaller/build
   ```

3. The executable will be generated in `out/pyinstaller/dist/openmapfileanalyzer.exe` (or `openmapfileanalyzer` on Linux/macOS).

## Contributions

Contributions of all sizes are warmly welcome!. Please feel free to:

- Report issues using [the issue guide](Docs/create_a_issue.md)
- Submit pull requests
- Improve documentation
- Suggest new features
- Start a discussion

Let's make the library better for everyone.

---

## License

MIT License — see ['LICENSE'](LICENSE) file.

---

## Author

Muhammad Hassaan Shah

- GitHub: [@thesourcebuild](https://github.com/thesourcebuild)
- Project: [github.com/thesourcebuild/OpenMapFileVisualizer](https://github.com/thesourcebuild/OpenMapFileVisualizer)
