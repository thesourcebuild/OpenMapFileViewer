from datetime import datetime
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

from .models import Analysis, Contribution


def parse_elf(path: Path, min_size: int = 0) -> Analysis:
    analysis = Analysis(
        input_file=str(path),
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    analysis.format_hints.append("format=elf")

    try:
        with open(path, "rb") as f:
            elf = ELFFile(f)

            # Build section mapping to map section index to section name
            # and simultaneously add them as `<section total>` contributions
            # so overall memory capacity matches map files perfectly
            section_names = {}
            section_sizes = {}
            for i, section in enumerate(elf.iter_sections()):
                section_names[i] = section.name
                size = section["sh_size"]
                section_sizes[section.name] = size
                if size > 0:
                    analysis.contributions.append(
                        Contribution(
                            section=section.name,
                            address=section["sh_addr"] if section["sh_addr"] != 0 else None,
                            size=size,
                            source="<section total>",
                            symbol="",
                        )
                    )

            symtab = elf.get_section_by_name(".symtab")
            if not symtab or not isinstance(symtab, SymbolTableSection):
                analysis.warnings.append("No symbol table (.symtab) found in ELF file.")
                return analysis

            current_file = "<unknown>"
            symbol_sizes_per_section = __import__("collections").defaultdict(int)

            for symbol in symtab.iter_symbols():
                sym_info = symbol["st_info"]
                sym_type = sym_info["type"]

                if sym_type == "STT_FILE":
                    current_file = symbol.name
                    continue

                if sym_type not in ("STT_FUNC", "STT_OBJECT"):
                    continue

                size = symbol["st_size"]
                if size < min_size or size == 0:
                    continue

                shndx = symbol["st_shndx"]
                if isinstance(shndx, str):
                    continue

                section_name = section_names.get(shndx, f"Section_{shndx}")

                if section_name.startswith(".debug"):
                    continue

                symbol_sizes_per_section[section_name] += size

                contrib = Contribution(
                    section=section_name,
                    address=symbol["st_value"],
                    size=size,
                    source=current_file,
                    symbol=symbol.name,
                )
                analysis.contributions.append(contrib)

            # Add missing sizes as <unattributed> leaf rows so that module charts
            # (which rely on leaf rows) sum up to the exact capacity.
            for sec_name, sh_size in section_sizes.items():
                if sec_name.startswith(".debug"):
                    continue
                diff = sh_size - symbol_sizes_per_section.get(sec_name, 0)
                if diff > 0:
                    analysis.contributions.append(
                        Contribution(
                            section=sec_name,
                            address=None,
                            size=diff,
                            source="<unattributed>",
                            symbol="",
                        )
                    )
    except Exception as e:
        analysis.warnings.append(f"Failed to parse ELF file: {e}")

    return analysis
