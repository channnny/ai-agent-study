"""POC: 고려대(0000069) end-to-end 실행."""
import sys
from agent.crawler import crawl
from agent.mapper import map_raw
from agent.validator import validate
from agent.writer import write

UNV_CD = sys.argv[1] if len(sys.argv) > 1 else "0000069"

print(f"=== POC: unvCd={UNV_CD} ===\n")

print("[1/4] Crawler")
crawl_res = crawl(UNV_CD)
print(f"  → {crawl_res['table_count']} tables, screenshot: {crawl_res['screenshot']}\n")

print("[2/4] Mapper")
mapped = map_raw(UNV_CD)
print(f"  → {len(mapped['records'])} records\n")

print("[3/4] Validator")
report = validate(UNV_CD)
print(f"  → verdict: {report['verdict']}, off_ratio: {report['summary']['numeric_off_ratio']}\n")

print("[4/4] Writer")
out = write(UNV_CD)
print(f"  → {out}\n")

print("=== DONE ===")
