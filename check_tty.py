import os

print("Checking for controlling terminal...")
try:
    fd = os.open("/dev/tty", os.O_RDWR)
    print("Success: /dev/tty opened.")
    os.close(fd)
except OSError as e:
    print(f"Failure: Could not open /dev/tty: {e}")

try:
    print(f"ctermid: {os.ctermid()}")
except Exception as e:
    print(f"ctermid error: {e}")

