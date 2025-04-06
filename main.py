import os
import re
import uvicorn
import markdown
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler

from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="정보처리기사 학습 웹사이트", docs_url=None, redoc_url=None)  # API 문서 경로 비활성화

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/img", StaticFiles(directory="."), name="img")

# 템플릿 설정
templates = Jinja2Templates(directory="static")

# 기본 디렉토리 설정
BASE_DIR = Path(__file__).resolve().parent

def get_directory_structure():
    """폴더 구조를 읽어서 계층적 사전 구조로 반환"""
    structure = {}
    for root, dirs, files in os.walk(BASE_DIR):
        if any(x in root for x in ['.git', '__pycache__', '.vscode', 'static']):
            continue
        rel_path = os.path.relpath(root, BASE_DIR)
        if rel_path == ".":
            continue
        path_parts = rel_path.split(os.sep)
        if "img" in path_parts:
            continue
        current = structure
        for part in path_parts:
            if part not in current:
                current[part] = {"__files": []}
            current = current[part]
        for file in files:
            if file.endswith(".md"):
                current["__files"].append(file)
    def sort_key(item):
        name = item[0]
        match = re.match(r"(\d+)_", name)
        return int(match.group(1)) if match else float('inf')
    sorted_structure = dict(sorted(structure.items(), key=sort_key))
    return sorted_structure

def read_markdown_file(file_path):
    """마크다운 파일을 읽어서 HTML로 변환"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            content = re.sub(
                r'!\[(.*?)\]\(\./img/(.*?)\)',
                r'![\1](/img/1_요구사항_확인/img/\2)',
                content
            )
            content = re.sub(
                r'\[(.*?)\]\(\./(.*?)\.md(#.*?)?\)',
                r'[\1](/view/\2\3)',
                content
            )
            html = markdown.markdown(
                content,
                extensions=[
                    'markdown.extensions.tables',
                    'markdown.extensions.fenced_code',
                    'markdown.extensions.codehilite',
                    'markdown.extensions.toc'
                ]
            )
            return html
    except FileNotFoundError:
        return None

# API 문서 접근 제한 미들웨어
@app.middleware("http")
async def restrict_docs_access(request: Request, call_next):
    restricted_paths = ["/docs", "/redoc", "/openapi.json"]
    client_host = request.client.host
    if request.url.path in restricted_paths and client_host not in ["127.0.0.1", "localhost"]:
        return templates.TemplateResponse(
            "unauthorized.html",
            {"request": request},
            status_code=403
        )
    return await call_next(request)

# 404 응답 처리 미들웨어 - 정의되지 않은 경로만 unauthorized.html 반환
@app.middleware("http")
async def catch_all_404s(request: Request, call_next):
    response = await call_next(request)

    # 정의된 경로를 제외한 404만 unauthorized.html 반환
    defined_paths = ("/", "/view", "/img", "/static")
    if (
        response.status_code == 404
        and not any(request.url.path.startswith(p) for p in defined_paths)
    ):
        return templates.TemplateResponse(
            "unauthorized.html",
            {"request": request},
            status_code=404
        )
    return response

# 404 예외 핸들러 추가
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        # 404 상태 코드에 대해 unauthorized.html 반환
        return templates.TemplateResponse(
            "unauthorized.html",
            {"request": request},
            status_code=404
        )
    # 다른 상태 코드는 기본 처리
    return await http_exception_handler(request, exc)

# 요청 검증 오류 핸들러 추가 (선택 사항)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return templates.TemplateResponse(
        "unauthorized.html",
        {"request": request},
        status_code=400
    )

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """홈페이지"""
    index_content = """
    <h1>정보처리기사 학습 웹사이트</h1>
    <p>왼쪽의 목차에서 원하는 항목을 선택하세요.</p>
    <p>정보처리기사 시험 공부에 도움이 되는 자료들을 정리해 놓았습니다.</p>
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "정보처리기사 학습 웹사이트",
            "content": index_content,
            "structure": get_directory_structure()
        }
    )

@app.get("/view/{path:path}", response_class=HTMLResponse)
async def view_markdown(request: Request, path: str):
    """마크다운 파일 보기"""
    file_path = BASE_DIR / f"{path}.md"
    content = read_markdown_file(file_path)
    if content is None:
        return templates.TemplateResponse(
            "unauthorized.html",
            {"request": request},
            status_code=404
        )
    title_match = re.search(r'<h1>(.*?)</h1>', content)
    title = title_match.group(1) if title_match else path
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": title,
            "content": content,
            "structure": get_directory_structure(),
            "current_path": path
        }
    )

@app.get("/img/{path:path}")
async def get_image(request: Request, path: str):
    """이미지 파일 제공"""
    file_path = BASE_DIR / path
    if not file_path.exists():
        return templates.TemplateResponse(
            "unauthorized.html",
            {"request": request},
            status_code=404
        )
    return FileResponse(file_path)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)