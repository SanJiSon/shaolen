#!/usr/bin/env python3
"""
Повышает версию проекта и записывает её в файл VERSION.
Версия хранится только в репозитории (VERSION + CHANGELOG), из Telegram не читается.

Использование:
  python scripts/bump_version.py           # patch: 1.1.0 → 1.1.1
  python scripts/bump_version.py patch    # то же
  python scripts/bump_version.py minor    # 1.1.0 → 1.2.0
  python scripts/bump_version.py major    # 1.1.0 → 2.0.0
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_PATH = os.path.join(ROOT, "VERSION")


def read_version_lines() -> list[str]:
    """Читает все строки VERSION (первая — текущая версия, далее история с +)."""
    if not os.path.isfile(VERSION_PATH):
        return []
    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in (f.read() or "").splitlines() if ln.strip()]


def parse_version(s: str) -> tuple[int, int, int] | None:
    s = s.strip().lstrip("v").rstrip("+").strip()
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump(current: str, kind: str) -> str | None:
    parts = parse_version(current)
    if not parts:
        return None
    major, minor, patch = parts
    if kind in ("patch", "p", ""):
        return f"{major}.{minor}.{patch + 1}"
    if kind in ("minor", "min", "m"):
        return f"{major}.{minor + 1}.0"
    if kind in ("major", "maj", "M"):
        return f"{major + 1}.0.0"
    return None


def main():
    kind = (sys.argv[1] or "patch").strip().lower() if len(sys.argv) > 1 else "patch"
    lines = read_version_lines()
    if not lines:
        print("Файл VERSION не найден или пуст. Создайте его, например: 1.0.0")
        sys.exit(1)
    first_line = lines[0]
    current = first_line.rstrip("+").strip().lstrip("v").strip()
    new_version = bump(current, kind)
    if not new_version:
        print("Не удалось повысить версию. Ожидается семантическая версия (X.Y.Z), текущее значение:", first_line)
        sys.exit(1)
    # Новая версия — первой строкой (без +); предыдущая — следующей строкой с +
    prev_marked = (current + "+") if not first_line.rstrip().endswith("+") else first_line
    new_lines = [new_version, prev_marked] + lines[1:]
    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")
    print("VERSION:", current, "→", new_version, "(новая строка сверху, предыдущая с +)")
    print("Добавьте блок для v" + new_version + " в CHANGELOG.md с комментарием <!-- TELEGRAM_POST ... -->.")


if __name__ == "__main__":
    main()
