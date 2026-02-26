raw = "``` [sadfdsf] ```"

raw = raw.strip()

if raw.startswith("```"):
    raw = raw.strip("```").strip()
print(raw)