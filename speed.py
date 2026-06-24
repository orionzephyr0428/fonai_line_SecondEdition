import json
import os
from urllib import request
import time
import statistics
import numpy as np
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = os.getenv("DEFAULT_BASE_URL")
IDNO = os.getenv("IDNO")
BRDT = os.getenv("BRDT")

def callCrawler(base_url, idno, brdt):
    url = base_url
    body = json.dumps({"idno": idno, "brDt": brdt}).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))

data = {}

for i in range(30):
    start = time.perf_counter()
    payload = callCrawler(DEFAULT_BASE_URL, IDNO, BRDT)
    end = time.perf_counter()
    stamp = end - start
    payload["stamp"] = stamp
    data[i] = payload


times = [item["stamp"] for item in data.values()]
p95_time = np.percentile(times, 95)

print(f"Average : {statistics.mean(times):.3f} sec")
print(f"Median  : {statistics.median(times):.3f} sec")
print(f"Min     : {min(times):.3f} sec")
print(f"Max     : {max(times):.3f} sec")
print(f"P95     : {p95_time:.3f} sec")