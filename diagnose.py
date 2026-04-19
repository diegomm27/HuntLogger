"""
Run this BEFORE launching Hunt: Showdown and leave it running through a match.
It polls attributes.xml every 200ms and logs every time the content changes,
showing whether MissionBag data is present. This helps us find the exact write window.
"""
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.parser import compute_xml_hash

PATH = Path(r"C:/Program Files/Steam/steamapps/common/Hunt Showdown 1896/USER/Profiles/default/attributes.xml")
POLL_MS = 200

last_hash = None
print(f"Watching {PATH}")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        try:
            text = PATH.read_text(encoding="utf-8", errors="replace")
        except OSError:
            time.sleep(POLL_MS / 1000)
            continue

        h = compute_xml_hash(text)
        if h != last_hash:
            last_hash = h
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            has_mission = any("MissionBag" in line or "MissionAccolade" in line for line in text.splitlines()[:500])
            key_count = text.count('<Attr ')
            mission_count = text.count('MissionBag') + text.count('MissionAccolade')
            print(f"[{ts}] FILE CHANGED  keys={key_count}  mission_keys={mission_count}  has_match_data={has_mission}")
            if has_mission:
                print("  *** MATCH DATA FOUND! ***")
                # Print first few MissionBag keys
                for line in text.splitlines():
                    if "MissionBag" in line or "MissionAccolade" in line:
                        print(f"  {line.strip()}")
                        break

        time.sleep(POLL_MS / 1000)
except KeyboardInterrupt:
    print("\nStopped.")
