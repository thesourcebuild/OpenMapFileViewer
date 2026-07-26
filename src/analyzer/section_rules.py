from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class RulesConfig:
    section_rules: dict[str, Any]
    region_kind_rules: dict[str, dict[str, tuple[str, ...]]]
    module_class_rules: dict[str, tuple[str, ...]]


SECTION_RULES = {
    "keywords": {
        "code": {"code", "text", "thumb", "arm", "function"},
        "rodata": {"rodata", "readonly", "const", "ro", "ro-data"},
        "data": {"rwdata", "data", "rw", "rw-data"},
        "bss": {"zidata", "bss", "zi", "zero", "zero-initialized"},
        "debug": {"debug", "debugdata"},
    },
    "prefixes": [
        ("code", (".text", ".init", ".fini", ".isr_vector", ".vectors", ".itcm")),
        ("rodata", (".rodata", ".const", ".ARM.extab", ".ARM.exidx", ".eh_frame", ".gcc_except_table")),
        ("data", (".data", ".ramfunc", ".fastcode", ".dtcm")),
        ("bss", (".bss", "COMMON", ".noinit", ".heap", ".stack", ".dma_buffer")),
        ("debug", (".debug", ".stab", ".line", ".group", ".comment", ".note", ".symtab", ".strtab", ".ARM.attributes", ".xtensa.info", ".gnu.attributes", ".gnu.hash", ".dynsym", ".dynstr", ".rel", ".rela")),
    ],
    "suffixes": [
        ("code", (".text", ".text_end", ".vectors", ".force_slow")),
        ("rodata", (".rodata", ".literal", ".appdesc")),
        ("data", (".data", "_reserved", ".force_fast")),
        ("bss", (".bss", ".noload")),
    ],
}

REGION_KIND_RULES = {
    "flash": {
        "keywords": ("flash", "rom", "qspi", "nor", "nand", "emmc", "spi", "boot", "linear", "program"),
        "attributes": ("x", "r"),
    },
    "ram": {
        "keywords": ("ram", "sram", "ddr", "ocm", "tcm", "dram", "bram", "ps7_ram", "ps7_ddr", "noncache"),
        "attributes": ("w",),
    },
}

MODULE_CLASS_RULES = {
    "Networking": ("lwip", "tcp", "udp", "ip4", "eth", "mqtt", "dhcp", "dns", "sntp", "smtp", "tftp", "socket", "arp", "netbios"),
    "Drivers / BSP": (
        # Xilinx
        "xil", "xemac", "xadc", "qspi", "sdps", "ttc", "scugic",
        # Generic/Common
        "uart", "iic", "gpio", "bsp", "driver", "phy",
        # STMicroelectronics HAL
        "stm32", "hal",
        # NXP/Freescale
        "fsl_", "lpc_", "kinetis", "mcux",
        # Microchip/Atmel
        "atmel_", "sam_", "pic_", "avr_",
        # Silicon Labs
        "em_", "sl_",
        # Renesas
        "r_", "rz_",
        # Infineon
        "cy_", "xmc_",
    ),
    "File system": ("fatfs", "ff.", "ff_", "xilffs", "diskio", "filesystem", "file"),
    "RTOS": (
        # FreeRTOS / AWS
        "freertos", "free_rtos", "task", "queue", "semphr", "event_group", "stream_buffer",
        # ARM CMSIS
        "cmsis", "arm_",
        # Zephyr
        "zephyr",
        # RT-Thread
        "rtthread", "rt_thread",
        # ThreadX / Azure RTOS
        "threadx", "azure_rtos", "tx_", "nx_", "gx_", "ux_",
        # μC/OS (Micrium)
        "ucos", "micrium", "os_cfg", "os_task",
        # NuttX
        "nuttx",
        # VxWorks
        "vxworks", "vx_",
        # Mbed OS
        "mbed",
        # TI-RTOS / SysBIOS
        "ti_rtos", "sysbios", "bios",
        # ChibiOS
        "chibios", "ch_",
        # Contiki / Contiki-NG
        "contiki",
        # RTEMS
        "rtems",
        # Keil RTX
        "rtx", "cmsis_rtos",
        # Piko-SDK (Raspberry Pi)
        "pico_sdk", "pico_",
        # ESP-IDF (FreeRTOS variant)
        "esp_rtos", "esp_task",
        # Harmony
        "harmony",
    ),
    "DSP": ("dsp", "fir", "iir", "fft", "filter", "arm_cfir", "arm_fir", "arm_iir", "arm_fft", "arm_math"),
    "Runtime / C library": (
        # Standard C libraries
        "libc", "glibc", "musl", "newlib", "uclibc", "ulibc",
        # Embedded/Lightweight C libraries
        "picolibc", "avr-libc", "klibc", "dietlibc", "bionic",
        # ARM embedded
        "arm_none_eabi",
        # Math library
        "libm",
        # C++ standard library
        "libstdc", "libcxx",
        # Compiler runtime support
        "libgcc", "compiler-rt",
        # C runtime initialization
        "crt", "crtbegin", "crtend",
        # Memory management and utilities
        "malloc", "printf", "memcpy", "strlen", "strcpy",
    ),
    "Application": ("app", "cli", "handler", "manager", "database", "fota", "ota"),
    "Libraries / middleware": (".a(", ".lib("),
}


DEFAULT_RULES = RulesConfig(
    section_rules=SECTION_RULES,
    region_kind_rules=REGION_KIND_RULES,
    module_class_rules=MODULE_CLASS_RULES,
)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.lower(),)
    return tuple(str(item).lower() for item in value)


def _append_unique(existing: tuple[str, ...], extra: tuple[str, ...]) -> tuple[str, ...]:
    values = list(existing)
    seen = set(values)
    for item in extra:
        if item not in seen:
            values.append(item)
            seen.add(item)
    return tuple(values)


def _normalize_section_rules(raw: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    keywords = raw.get("keywords")
    if isinstance(keywords, Mapping):
        normalized["keywords"] = {
            str(category): set(_as_tuple(values))
            for category, values in keywords.items()
        }

    for rule_name in ("prefixes", "suffixes"):
        values = raw.get(rule_name)
        if isinstance(values, Mapping):
            normalized[rule_name] = [
                (str(category), _as_tuple(patterns))
                for category, patterns in values.items()
            ]
        elif values is not None:
            normalized[rule_name] = [
                (str(category), _as_tuple(patterns))
                for category, patterns in values
            ]

    return normalized


def _normalize_region_kind_rules(raw: Mapping[str, Any]) -> dict[str, dict[str, tuple[str, ...]]]:
    normalized: dict[str, dict[str, tuple[str, ...]]] = {}
    for kind, rules in raw.items():
        if not isinstance(rules, Mapping):
            continue
        normalized[str(kind)] = {
            str(rule_name): _as_tuple(values)
            for rule_name, values in rules.items()
        }
    return normalized


def _normalize_module_class_rules(raw: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    return {str(category): _as_tuple(values) for category, values in raw.items()}


def _merge_section_rules(defaults: dict[str, Any], custom: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    normalized = _normalize_section_rules(custom)

    if "keywords" in normalized:
        merged_keywords = dict(merged.get("keywords", {}))
        for category, keywords in normalized["keywords"].items():
            merged_keywords[category] = set(merged_keywords.get(category, set())) | set(keywords)
        merged["keywords"] = merged_keywords

    for rule_name in ("prefixes", "suffixes"):
        if rule_name not in normalized:
            continue
        ordered = list(merged.get(rule_name, []))
        positions = {category: index for index, (category, _) in enumerate(ordered)}
        for category, patterns in normalized[rule_name]:
            if category in positions:
                _, existing_patterns = ordered[positions[category]]
                ordered[positions[category]] = (
                    category,
                    _append_unique(tuple(existing_patterns), patterns),
                )
            else:
                positions[category] = len(ordered)
                ordered.append((category, patterns))
        merged[rule_name] = ordered

    return merged


def merge_rules(custom: Mapping[str, Any] | None, defaults: RulesConfig = DEFAULT_RULES) -> RulesConfig:
    if not custom:
        return defaults

    section_rules = defaults.section_rules
    region_kind_rules = deepcopy(defaults.region_kind_rules)
    module_class_rules = dict(defaults.module_class_rules)

    custom_sections = custom.get("section_rules")
    if isinstance(custom_sections, Mapping):
        section_rules = _merge_section_rules(section_rules, custom_sections)

    custom_regions = custom.get("region_kind_rules")
    if isinstance(custom_regions, Mapping):
        for kind, kind_rules in _normalize_region_kind_rules(custom_regions).items():
            merged_kind_rules = dict(region_kind_rules.get(kind, {}))
            for rule_name, values in kind_rules.items():
                merged_kind_rules[rule_name] = _append_unique(
                    tuple(merged_kind_rules.get(rule_name, ())),
                    values,
                )
            region_kind_rules[kind] = merged_kind_rules

    custom_modules = custom.get("module_class_rules")
    if isinstance(custom_modules, Mapping):
        for category, values in _normalize_module_class_rules(custom_modules).items():
            module_class_rules[category] = _append_unique(
                tuple(module_class_rules.get(category, ())),
                values,
            )

    return RulesConfig(
        section_rules=section_rules,
        region_kind_rules=region_kind_rules,
        module_class_rules=module_class_rules,
    )


def load_rules(path: Path | str) -> RulesConfig:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load custom rules files. "
            "Install it with: pip install PyYAML>=6.0"
        ) from exc

    rules_path = Path(path)
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise ValueError(f"custom rules file must contain a YAML mapping: {rules_path}")
    return merge_rules(data)
