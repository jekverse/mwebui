#!/usr/bin/env python3

import os
import re
import stat
import sys

HOME = os.path.expanduser("~")
TARGET_FILE = os.path.join(HOME, ".modal.toml")

# Pola blok token
PATTERN = re.compile(
    r'^\[([A-Za-z0-9_\-]+)\]\s*[\r\n]+token_id\s*=\s*"([^"]+)"\s*[\r\n]+token_secret\s*=\s*"([^"]+)"\s*$',
    re.MULTILINE
)

def main():
    print("Paste blok token Anda, lalu tekan ENTER dua kali untuk menyimpan:")
    print("(Format: [profile]\\ntoken_id = \"ak-...\"\\ntoken_secret = \"as-...\")\n")

    # Baca 1 blok input
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break

        if line.strip() == "" and lines:
            break  # final empty line = selesai input

        lines.append(line)

    block = "\n".join(lines).strip()

    if not block:
        print("❌ Tidak ada input. Keluar.")
        sys.exit(1)

    match = PATTERN.match(block)
    if not match:
        print("❌ Format token tidak valid.")
        print("Gunakan format:")
        print("[profile]")
        print('token_id = "ak-..."')
        print('token_secret = "as-..."')
        sys.exit(1)

    profile, token_id, token_secret = match.group(1), match.group(2), match.group(3)

    normalized = (
        f"[{profile}]\n"
        f'token_id = "{token_id}"\n'
        f'token_secret = "{token_secret}"\n'
    )

    # Pastikan file ada
    if not os.path.exists(TARGET_FILE):
        open(TARGET_FILE, "w").close()

    # Append langsung
    with open(TARGET_FILE, "a", encoding="utf-8") as f:
        if f.tell() != 0:
            f.write("\n")  # separator
        f.write(normalized)

    # Atur permission 600 (Debian OK)
    try:
        os.chmod(TARGET_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except:
        pass

    print(f"\n✅ Token berhasil ditambahkan ke {TARGET_FILE}")
    print("Permission diatur ke 600 (rw-------)")

if __name__ == "__main__":
    main()
