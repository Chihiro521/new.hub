"""Minimal FastAPI server to reproduce crawl4ai issue in uvicorn context."""
import asyncio
import json
import sys
sys.path.insert(0, ".")

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/test-crawl")
async def test_crawl():
    from app.services.collector.webpage_extractor import _get_crawler, _build_run_config

    async def stream():
        url = "https://www.thepaper.cn/newsDetail_forward_32636503"

        # Step 1
        yield f"data: {json.dumps({'step': 'init', 'msg': 'getting crawler...'})}\n\n"
        try:
            crawler = await _get_crawler()
            yield f"data: {json.dumps({'step': 'init', 'msg': 'OK'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'init', 'msg': f'FAIL: {e}'})}\n\n"
            return

        # Step 2
        yield f"data: {json.dumps({'step': 'crawl', 'msg': 'crawling...'})}\n\n"
        try:
            cfg = _build_run_config()
            result = await asyncio.wait_for(crawler.arun(url=url, config=cfg), timeout=25)
            html_len = len(result.html or "")
            md_len = len(getattr(result.markdown, "raw_markdown", "") or "")
            yield f"data: {json.dumps({'step': 'crawl', 'msg': f'OK html={html_len} md={md_len}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'crawl', 'msg': f'FAIL: {type(e).__name__}: {e}'})}\n\n"

        yield f"data: {json.dumps({'step': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9999)
