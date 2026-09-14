#!/usr/bin/env python3
"""Download a public NSFC final report from kd.nsfc.cn and build a PDF."""

import argparse
import base64
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    from PIL import Image
    from pypdf import PdfReader
except ImportError as error:
    raise SystemExit(
        "Missing dependency. Use the Codex bundled Python runtime or install "
        "cryptography, Pillow, and pypdf."
    ) from error


BASE_URL = "https://kd.nsfc.cn"
SEARCH_API = f"{BASE_URL}/api/baseQuery/completionQueryResultsData"
REPORT_API = f"{BASE_URL}/api/baseQuery/completeProjectReport"
DES_KEY = b"IFROMC86"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class Client:
    def __init__(self, insecure=False):
        self.context = ssl._create_unverified_context() if insecure else ssl.create_default_context()

    def open(self, request, attempts=10, timeout=60):
        last_error = None
        for attempt in range(attempts):
            try:
                return urllib.request.urlopen(request, context=self.context, timeout=timeout)
            except urllib.error.HTTPError as error:
                if error.code not in {429, 502, 503, 504}:
                    raise
                last_error = error
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
            if attempt < attempts - 1:
                time.sleep(min(2**attempt, 20))
        raise last_error

    def post_json(self, url, payload):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self.headers("application/json"),
        )
        with self.open(request) as response:
            return response.read()

    def post_form(self, url, payload):
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(payload).encode("ascii"),
            headers=self.headers("application/x-www-form-urlencoded"),
        )
        with self.open(request) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def headers(content_type=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Authorization": "Bearer null",
            "Referer": BASE_URL + "/",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers


def decrypt_search_response(value):
    encrypted = base64.b64decode(value)
    decryptor = Cipher(TripleDES(DES_KEY * 3), modes.ECB()).decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    padding = padded[-1]
    if padding < 1 or padding > 8 or padded[-padding:] != bytes([padding]) * padding:
        raise ValueError("Invalid encrypted response padding")
    return json.loads(padded[:-padding].decode("utf-8"))


def search_projects(client, query):
    payload = {
        "complete": True,
        "fuzzyKeyword": query,
        "isFuzzySearch": True,
        "conclusionYear": "",
        "dependUnit": "",
        "keywords": "",
        "pageNum": 0,
        "pageSize": 20,
        "projectType": "",
        "projectTypeName": "",
        "code": "",
        "ratifyYear": "",
        "order": "enddate",
        "ordering": "desc",
        "codeScreening": "",
        "dependUnitScreening": "",
        "keywordsScreening": "",
        "projectTypeNameScreening": "",
    }
    result = decrypt_search_response(client.post_json(SEARCH_API, payload))
    if result.get("code") != 200:
        raise RuntimeError(f"Search failed: {result.get('message') or result.get('code')}")
    return result.get("data", {}).get("resultsData", [])


def normalize_result(row):
    return {
        "id": row[0],
        "title": row[1],
        "grant_number": row[2],
        "project_type": row[3],
        "organization": row[4],
        "principal_investigator": row[5],
        "has_report": str(row[13]).lower() == "true",
    }


def select_project(rows, grant_number=None, title=None):
    projects = [normalize_result(row) for row in rows]
    if grant_number:
        exact = [p for p in projects if p["grant_number"].casefold() == grant_number.casefold()]
    else:
        exact = [p for p in projects if p["title"].strip() == title.strip()]
    candidates = exact or projects
    if len(candidates) != 1:
        print("MATCH_COUNT=" + str(len(candidates)))
        for project in candidates:
            print("CANDIDATE=" + json.dumps(project, ensure_ascii=False))
        raise SystemExit(2)
    return candidates[0]


def report_url(client, project_id, index):
    result = client.post_form(REPORT_API, {"id": project_id, "index": index})
    data = result.get("data") or {}
    if result.get("code") != 200 or not data.get("url"):
        raise RuntimeError(f"No report URL returned for page {index}")
    path = data["url"]
    if not path.startswith("/report/"):
        raise RuntimeError(f"Unexpected report path for page {index}: {path}")
    return BASE_URL + path


def page_exists(client, project_id, index):
    url = report_url(client, project_id, index)
    request = urllib.request.Request(url, method="HEAD", headers=client.headers())
    try:
        with client.open(request, attempts=6, timeout=30) as response:
            return response.status == 200 and response.headers.get_content_type().startswith("image/")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def find_page_count(client, project_id, max_pages):
    if not page_exists(client, project_id, 1):
        raise RuntimeError("The first report page is unavailable")
    low, high = 1, 2
    while high <= max_pages and page_exists(client, project_id, high):
        low, high = high, high * 2
    high = min(high, max_pages + 1)
    if high == max_pages + 1 and page_exists(client, project_id, max_pages):
        raise RuntimeError(f"Report exceeds --max-pages={max_pages}")
    while low + 1 < high:
        middle = (low + high) // 2
        if page_exists(client, project_id, middle):
            low = middle
        else:
            high = middle
    return low


def download_page(client, project_id, index, destination):
    if destination.exists() and destination.stat().st_size > 1000:
        try:
            with Image.open(destination) as image:
                image.verify()
            return "cached"
        except Exception:
            destination.unlink()
    request = urllib.request.Request(report_url(client, project_id, index), headers=client.headers())
    with client.open(request) as response:
        if not response.headers.get_content_type().startswith("image/"):
            raise RuntimeError(f"Page {index} did not return an image")
        content = response.read()
    destination.write_bytes(content)
    with Image.open(destination) as image:
        image.verify()
    return "downloaded"


def build_pdf(page_paths, output_pdf):
    images = []
    try:
        for path in page_paths:
            with Image.open(path) as source:
                image = source.convert("RGB")
                image.load()
                images.append(image)
        images[0].save(output_pdf, "PDF", save_all=True, append_images=images[1:], resolution=150.0)
    finally:
        for image in images:
            image.close()
    actual_pages = len(PdfReader(output_pdf).pages)
    if actual_pages != len(page_paths):
        raise RuntimeError(f"PDF page mismatch: expected {len(page_paths)}, got {actual_pages}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    query = parser.add_mutually_exclusive_group(required=True)
    query.add_argument("--grant-number", help="NSFC grant number, for example U1806228")
    query.add_argument("--title", help="Exact project title")
    parser.add_argument("--output-dir", type=Path, default=Path("output/pdf"))
    parser.add_argument("--cache-dir", type=Path, default=Path("tmp/pdfs/nsfc-report-pages"))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=400)
    parser.add_argument("--lookup-only", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    return parser.parse_args()


def main():
    args = parse_args()
    client = Client(insecure=args.insecure)
    query = args.grant_number or args.title
    project = select_project(search_projects(client, query), args.grant_number, args.title)
    print("PROJECT=" + json.dumps(project, ensure_ascii=False))
    if args.lookup_only:
        return
    if not project["has_report"]:
        raise SystemExit("The matched project has no public final report")

    page_count = find_page_count(client, project["id"], args.max_pages)
    cache_dir = args.cache_dir / project["grant_number"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as executor:
        futures = {}
        for index in range(1, page_count + 1):
            destination = cache_dir / f"page-{index:04d}.png"
            future = executor.submit(download_page, client, project["id"], index, destination)
            futures[future] = index
        for future in as_completed(futures):
            index = futures[future]
            try:
                status = future.result()
                print(f"PAGE={index}/{page_count} STATUS={status}", flush=True)
            except Exception as error:
                failures.append((index, str(error)))
                print(f"PAGE={index}/{page_count} STATUS=failed ERROR={error}", file=sys.stderr, flush=True)
    if failures:
        raise RuntimeError(f"Failed pages: {failures}")

    page_paths = [cache_dir / f"page-{index:04d}.png" for index in range(1, page_count + 1)]
    safe_grant = re.sub(r"[^A-Za-z0-9_-]+", "_", project["grant_number"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = args.output_dir / f"国家自然科学基金结题报告_{safe_grant}.pdf"
    build_pdf(page_paths, output_pdf)
    print(f"PAGE_COUNT={page_count}")
    print(f"OUTPUT_PDF={output_pdf.resolve()}")


if __name__ == "__main__":
    main()
