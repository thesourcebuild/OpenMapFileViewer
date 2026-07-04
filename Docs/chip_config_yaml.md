# Chip Config YAML Files

The `--chip-config PATH` option lets you define chip memory regions explicitly, overriding any regions detected from the map file or linker script. This gives precise control over memory classification (flash vs RAM) without relying on heuristic region-name guessing.

## Detection

The loader auto-detects the schema from the top-level YAML structure:

| Schema | Detection | Example |
|---|---|---|
| **A** (Linker-style) | Has `memory_regions` key | STM32, generic MCUs |
| **B** (ESP-IDF-style) | Values contain `primary_address` | ESP32, ESP32-S3, etc. |
| **C** (CMSIS/generic) | Has `regions` key | Zynq, generic MCUs |

## Schema A — Linker-style (`memory_regions`)

```yaml
memory_regions:
  - name: FLASH
    origin: 0x08000000
    length: 0x20000
    kind: flash
    attrs: rx
  - name: SRAM
    origin: 0x20000000
    length: 0x5000
    kind: ram
    attrs: rw
```

Field      | Required | Description
-----------|----------|------------
`name`     | yes      | Region name (shown in UI)
`origin`   | yes      | Start address (hex `0x...` or decimal)
`length`   | yes      | Size in bytes (hex, decimal, or expression like `128K`, `2MiB`, `17 * 0x2000`)
`kind`     | no       | Memory class: `flash`, `ram`, or any string. If omitted, inferred from name.
`attrs`    | no       | Attributes string (e.g., `rx`, `rw`)

## Schema B — ESP-IDF-style (flat dict)

```yaml
DRAM:
  primary_address: 0x3FFAE000
  length: 17 * 0x2000 + 4 * 0x8000 + 4 * 0x4000
  kind: ram
IRAM:
  primary_address: 0x40070000
  length: 0x50000
FLASH_CODE:
  primary_address: 0x400C2000
  length: 0xB3E000
  name: Flash Code
  kind: flash
SPI_DRAM:
  primary_address: 0x3F800000
  length: 0x400000
  name: SPI DRAM
RTC_FAST:
  primary_address: 0x3FF80000
  length: 0x2000
  secondary_address: 0x400C0000
  name: RTC FAST
  kind: ram
```

Field                | Required | Description
---------------------|----------|------------
YAML key             | yes      | Memory type identifier (e.g., `DRAM`, `IRAM`, `FLASH_CODE`)
`primary_address`    | yes      | Start address (hex `0x...`, decimal, or expression)
`length`             | yes      | Size (hex, decimal, byte suffix, or arithmetic expression)
`name`               | no       | Display name (defaults to YAML key)
`kind`               | no       | Memory class. If omitted, inferred from `name`:
|                    |          | - `DRAM`, `IRAM`, `SRAM`, `RAM`, `RTC` → `ram`
|                    |          | - `CACHE`, `FLASH`, `ROM` → `flash`
|                    |          | - Otherwise → empty (falls through to heuristic)
`secondary_address`  | no       | Alternative bus address for alias region (e.g., DIRAM, RTC FAST)
`attrs`              | no       | Attributes string

## Schema C — CMSIS/generic (`regions`)

```yaml
regions:
  - name: ps7_ddr_0
    base: 0x00100000
    size: 0x1FE00000
    type: ram
    attrs: rw
  - name: ps7_ram_0
    base: 0x00000000
    size: 0x30000
    type: ram
  - name: FLASH
    base: 0x08000000
    size: 128K
    type: flash
```

Field       | Required | Description
------------|----------|------------
`name`      | yes      | Region name
`origin`    | yes*     | Start address (alias: `base`)
`length`    | yes*     | Size in bytes (alias: `size`)
`kind`      | no       | Memory class (alias: `type`). Inferred from name if absent.
`attrs`     | no       | Attributes string

\* Either `origin`/`base` and `length`/`size` must be present.

## `kind` Inference

When `kind` (or `type`) is not explicitly provided, it is inferred from the region `name`:

| Name contains | Inferred kind |
|---|---|
| `DRAM`, `IRAM`, `SRAM`, `RAM`, `RTC` | `ram` |
| `CACHE`, `FLASH`, `ROM` | `flash` |
| anything else | `""` (empty — falls back to heuristic `region_kind()`) |

Explicit `kind` always overrides inference.

## Value Expressions

All address and size fields support:

| Format | Example | Result |
|---|---|---|
| Hex | `0x20000` | 131072 |
| Decimal | `131072` | 131072 |
| Byte suffix | `128K`, `2MiB`, `64K` | 131072, 2097152, 65536 |
| Arithmetic | `17 * 0x2000 + 4 * 0x8000 + 4 * 0x4000` | 335872 |

Arithmetic evaluation is safe (recursive-descent parser, not Python `eval()`).
Supported operators: `+`, `-`, `*`, `/` (floor), `//` (floor), `%`, `(`, `)`.

## Sample Files

| File | Schema | Target |
|---|---|---|
| `samples/chip-configs/stm32f103.yaml` | A | STM32F103 (Keil) |
| `samples/chip-configs/esp32.yaml` | B | ESP32 |
| `samples/chip-configs/zynq.yaml` | C | Zynq-7000 (Vivado) |

## Usage

```bash
python src/openmapfileanalyzer.py firmware.map --chip-config my_chip.yaml -o report.html
```

When `--chip-config` is active, the YAML-defined regions completely replace any regions parsed from the map file or linker script. The `--rom-capacity` and `--ram-capacity` CLI flags still take precedence if set.

## Using with ESP-IDF `esp_idf_size` YAML files

Schema B is compatible with ESP-IDF's `chip_info/*.yaml` format. You can use the files bundled with `esp_idf_size` directly:

```bash
python src/openmapfileanalyzer.py build/your_project.map --chip-config "$(python -c "import esp_idf_size, os; print(os.path.join(os.path.dirname(esp_idf_size.__file__), 'chip_info', 'esp32.yaml'))")"
```

The tool will automatically detect the ESP-IDF format and apply it, with `kind` inferred from memory type names.
