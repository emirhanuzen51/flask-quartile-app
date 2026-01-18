import sys
from app import get_quartile_from_sjr

# Redirect stdout to a file
log_file = open("verify_result_log.txt", "w", encoding="utf-8")
sys.stdout = log_file

test_cases = [
    ("2169-3536", "IEEE Access"),
    ("1059-0560", "International Medical Case Reports Journal"), 
    ("0000-0000", "Invalid ISSN")
]

print("Starting Verification...\n")

for issn, name in test_cases:
    print(f"--- Testing {name} ({issn}) ---")
    try:
        q, cats, years, url = get_quartile_from_sjr(issn)
        print(f"Result for {name}:")
        print(f"  Quartile: {q}")
        print(f"  Years Found: {len(years)}")
        print(f"  URL: {url}")
        if cats:
            print(f"  Sample Category: {cats[0]}")
    except Exception as e:
        print(f"ERROR testing {name}: {e}")
    print("\n")

print("Verification Finished.")
log_file.close()
