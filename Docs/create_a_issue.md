# Creating a Good Issue

Found a bug or have a feature request? Here's how to write a useful issue.

## Before posting

- Check if a similar issue already exists in the tracker.
- Test with the latest version.
- For map parsing issues, try `--map-format gnu`, `--map-format keil`, etc. to narrow down the parser.

## Bug report template

```
### Description
What went wrong?

### Steps to reproduce
1. Command: `python src/openmapfileanalyzer.py ...`
2. Output / error message:

### Expected behavior
What should have happened.

### Environment
- OS: Windows 11 / Ubuntu 24.04 / ...
- Python version: `python --version`
- Analyzer version: (from `src/version.py` or the `version` file)
- Toolchain: GCC 12 / Keil MDK 5.38 / IAR 9.x / ...

### Attachments (optional)
- A minimal `.map` file that triggers the issue (sanitize any sensitive info).
- The linker script if relevant (`--linker-file`).
```

## Feature request template

```
### Problem
What's missing or inconvenient?

### Proposed solution
How would you like it to work?

### Alternatives considered
Any other approaches you've thought about.
```

## A good issue includes

- The **exact command** you ran
- The **full error/output** (or a screenshot)
- A **small sample file** if the parser gets the wrong numbers
- Your **toolchain version** and **map format**

Well-written issues get fixed faster.
